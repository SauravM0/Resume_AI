"""Adapt Phase 1 job analysis into deterministic Phase 2 ranking features."""

from __future__ import annotations

import re

from backend.app.cache.codecs import deserialize_job_ranking_features, serialize_model
from backend.app.cache.keys import build_cache_key, stable_code_hash, stable_model_hash
from backend.app.cache.storage import get_or_compute
from pydantic import Field, model_validator

from .job_models import NormalizedJobAnalysis, SkillPriority
from .models import NonEmptyStr, ScoreValue, StrictModel
from .normalization import (
    infer_domains_from_text,
    normalize_action_verbs,
    normalize_domain,
    normalize_role_taxonomy,
    normalize_seniority_taxonomy,
    normalize_skill_list,
    normalize_title_taxonomy,
)
from .phase2_config import DEFAULT_PHASE2_CONFIG

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9.+#/-]+")
_RESPONSIBILITY_HINTS = (
    "architecture",
    "delivery",
    "leadership",
    "mentoring",
    "ownership",
    "platform",
    "reliability",
    "scalability",
    "security",
    "stakeholder",
)
_WORK_STYLE_HINTS = (
    "collaborative",
    "autonomous",
    "cross-functional",
    "ownership",
    "pragmatic",
    "fast-paced",
    "remote",
)
JOB_FEATURES_CACHE_NAMESPACE = "job_ranking_features"
JOB_FEATURES_CACHE_TTL_SECONDS = 12 * 60 * 60


class WeightedFeatureBucket(StrictModel):
    """Weighted feature bucket used by scoring to distinguish priorities explicitly."""

    values: list[NonEmptyStr] = Field(default_factory=list)
    weight: float = Field(ge=0.0, le=100.0)
    confidence: ScoreValue = 0.5
    derived_from: list[NonEmptyStr] = Field(default_factory=list)


class JobRankingFeatures(StrictModel):
    """Ranking-ready Phase 2 job feature object derived from Phase 1 analysis."""

    canonical_must_have_skills: WeightedFeatureBucket
    canonical_nice_to_have_skills: WeightedFeatureBucket
    canonical_all_skills: list[NonEmptyStr] = Field(default_factory=list)
    role_family: NonEmptyStr | None = None
    role_type: NonEmptyStr | None = None
    seniority_target: NonEmptyStr | None = None
    domain_targets: list[NonEmptyStr] = Field(default_factory=list)
    action_verb_signals: list[NonEmptyStr] = Field(default_factory=list)
    years_experience_expectation: int | None = Field(default=None, ge=0, le=50)
    responsibility_themes: list[NonEmptyStr] = Field(default_factory=list)
    culture_work_style_signals: list[NonEmptyStr] = Field(default_factory=list)
    keyword_priority_buckets: dict[str, list[NonEmptyStr]] = Field(default_factory=dict)
    role_priority_weight: float = Field(ge=0.0, le=100.0)
    seniority_priority_weight: float = Field(ge=0.0, le=100.0)
    domain_priority_weight: float = Field(ge=0.0, le=100.0)
    parser_confidence: ScoreValue = 0.5
    fallback_applied: bool = False
    fallback_notes: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bucket_consistency(self) -> "JobRankingFeatures":
        """Keep the combined skill list aligned with the bucket contents."""

        combined = [
            *self.canonical_must_have_skills.values,
            *self.canonical_nice_to_have_skills.values,
        ]
        if not self.canonical_all_skills:
            object.__setattr__(self, "canonical_all_skills", _dedupe(combined))
        return self


def adapt_job_analysis_to_ranking_features(
    job_analysis: NormalizedJobAnalysis,
) -> JobRankingFeatures:
    """Convert normalized Phase 1 output into ranking-ready weighted features."""

    cache_key = build_cache_key(
        JOB_FEATURES_CACHE_NAMESPACE,
        {
            "job_analysis_hash": stable_model_hash(job_analysis),
            "phase2_config_hash": stable_model_hash(DEFAULT_PHASE2_CONFIG),
            "adapter_code_hash": stable_code_hash(
                adapt_job_analysis_to_ranking_features,
                normalize_skill_list,
                normalize_action_verbs,
            ),
        },
    )
    cached, _ = get_or_compute(
        namespace=JOB_FEATURES_CACHE_NAMESPACE,
        key=cache_key,
        compute=lambda: _compute_job_ranking_features(job_analysis),
        serialize=serialize_model,
        deserialize=deserialize_job_ranking_features,
        ttl_seconds=JOB_FEATURES_CACHE_TTL_SECONDS,
    )
    return cached


def _compute_job_ranking_features(
    job_analysis: NormalizedJobAnalysis,
) -> JobRankingFeatures:
    """Compute deterministic job-ranking features without cache concerns."""

    notes: list[str] = []
    fallback_applied = False

    normalized_priority_map: dict[str, SkillPriority] = {}
    for requirement in job_analysis.prioritized_skills:
        for term in normalize_skill_list([requirement.skill_name]):
            normalized_priority_map[term.canonical] = requirement.priority

    technical_skills = [term.canonical for term in normalize_skill_list(job_analysis.technical_skills)]
    must_have_from_text = _extract_skill_terms_from_text(job_analysis.must_have_requirements)
    nice_to_have_from_text = _extract_skill_terms_from_text(job_analysis.nice_to_have_requirements)

    must_have_skills = [
        skill
        for skill in technical_skills
        if normalized_priority_map.get(skill) == SkillPriority.CORE
    ]
    must_have_skills.extend(must_have_from_text)
    must_have_skills = _dedupe(must_have_skills)

    nice_to_have_skills = [
        skill
        for skill in technical_skills
        if normalized_priority_map.get(skill) == SkillPriority.NICE_TO_HAVE
    ]
    nice_to_have_skills.extend(nice_to_have_from_text)
    nice_to_have_skills.extend(
        skill
        for skill, priority in normalized_priority_map.items()
        if priority == SkillPriority.IMPORTANT and skill not in must_have_skills
    )
    nice_to_have_skills = [skill for skill in _dedupe(nice_to_have_skills) if skill not in must_have_skills]

    if not must_have_skills and technical_skills:
        fallback_applied = True
        notes.append("missing explicit required skills; promoted leading technical skills into must-have bucket")
        must_have_skills = technical_skills[: min(3, len(technical_skills))]
        nice_to_have_skills = [skill for skill in technical_skills if skill not in must_have_skills]

    if not technical_skills and (must_have_from_text or nice_to_have_from_text):
        fallback_applied = True
        notes.append("derived skills from requirement text because parser skill list was sparse")

    role_type = job_analysis.role_type.value if job_analysis.role_type is not None else None
    if role_type is None:
        inferred_role_type = _infer_role_type_from_text(job_analysis)
        if inferred_role_type is not None:
            role_type = inferred_role_type
            fallback_applied = True
            notes.append("inferred role type from job text because parser role_type was missing")

    seniority_target = (
        job_analysis.seniority_level.value if job_analysis.seniority_level is not None else None
    )
    if seniority_target is None:
        inferred_seniority = _infer_seniority_from_text(job_analysis)
        if inferred_seniority is not None:
            seniority_target = inferred_seniority
            fallback_applied = True
            notes.append("inferred seniority from skill and requirement context")

    role_family = _role_family_for_role_type(role_type)
    title_hint = normalize_title_taxonomy(
        f"{seniority_target or ''} {role_type or ''}".strip() or "software engineer"
    )
    if role_family is None:
        role_family = title_hint.role_family

    domain_targets = _dedupe(
        [
            *(
                [normalize_domain(job_analysis.industry_domain).canonical]
                if job_analysis.industry_domain is not None
                else []
            ),
            *[term.canonical for term in infer_domains_from_text(_domain_source_text(job_analysis))],
        ]
    )
    if not domain_targets:
        fallback_applied = True
        notes.append("domain targets unavailable; using empty domain bucket")

    action_verb_signals = [term.canonical for term in normalize_action_verbs(job_analysis.key_action_verbs)]
    if not action_verb_signals:
        action_verb_signals = _extract_action_verbs_from_text(job_analysis.must_have_requirements)
        if action_verb_signals:
            fallback_applied = True
            notes.append("derived action verbs from requirement text")

    responsibility_themes = _extract_responsibility_themes(job_analysis)
    culture_signals = _extract_culture_signals(job_analysis)

    parser_confidence = _estimate_parser_confidence(
        technical_skills=technical_skills,
        must_have_skills=must_have_skills,
        role_type=role_type,
        seniority_target=seniority_target,
        domain_targets=domain_targets,
        fallback_applied=fallback_applied,
    )

    return JobRankingFeatures(
        canonical_must_have_skills=WeightedFeatureBucket(
            values=must_have_skills,
            weight=DEFAULT_PHASE2_CONFIG.weights.keyword * 0.7,
            confidence=_bucket_confidence(must_have_skills, parser_confidence, fallback_applied),
            derived_from=_job_text_fields(job_analysis),
        ),
        canonical_nice_to_have_skills=WeightedFeatureBucket(
            values=nice_to_have_skills,
            weight=DEFAULT_PHASE2_CONFIG.weights.keyword * 0.3,
            confidence=_bucket_confidence(nice_to_have_skills, parser_confidence * 0.9, fallback_applied),
            derived_from=_job_text_fields(job_analysis),
        ),
        canonical_all_skills=_dedupe([*technical_skills, *must_have_skills, *nice_to_have_skills]),
        role_family=role_family,
        role_type=role_type,
        seniority_target=seniority_target,
        domain_targets=domain_targets,
        action_verb_signals=action_verb_signals,
        years_experience_expectation=job_analysis.years_experience_required,
        responsibility_themes=responsibility_themes,
        culture_work_style_signals=culture_signals,
        keyword_priority_buckets={
            "must_have": must_have_skills,
            "nice_to_have": nice_to_have_skills,
            "technical": technical_skills,
            "relevant_for": _dedupe(
                [
                    *job_analysis.soft_skills,
                    *action_verb_signals,
                    *job_analysis.company_culture_signals,
                    *( [role_type] if role_type else [] ),
                ]
            ),
            "domain_scoring": domain_targets,
            "responsibility": responsibility_themes,
            "culture": culture_signals,
        },
        role_priority_weight=DEFAULT_PHASE2_CONFIG.weights.relevant_for * 0.6,
        seniority_priority_weight=DEFAULT_PHASE2_CONFIG.weights.seniority,
        domain_priority_weight=DEFAULT_PHASE2_CONFIG.weights.domain,
        parser_confidence=parser_confidence,
        fallback_applied=fallback_applied,
        fallback_notes=notes,
    )


def _extract_skill_terms_from_text(values: list[str]) -> list[str]:
    terms: list[str] = []
    for value in values:
        terms.extend(
            term.canonical
            for term in normalize_skill_list(_candidate_terms(value))
            if term.status.value != "passthrough"
        )
    return _dedupe(terms)


def _extract_action_verbs_from_text(values: list[str]) -> list[str]:
    terms: list[str] = []
    for value in values:
        tokens = [token for token in _TOKEN_PATTERN.findall(value)]
        terms.extend(
            term.canonical
            for term in normalize_action_verbs(tokens)
            if term.status.value != "passthrough"
        )
    return _dedupe(terms)


def _extract_responsibility_themes(job_analysis: NormalizedJobAnalysis) -> list[str]:
    text_blob = " ".join(_job_text_fields(job_analysis)).casefold()
    themes = [hint for hint in _RESPONSIBILITY_HINTS if hint in text_blob]
    themes.extend(job_analysis.soft_skills)
    return _dedupe(themes)


def _extract_culture_signals(job_analysis: NormalizedJobAnalysis) -> list[str]:
    values = list(job_analysis.company_culture_signals)
    text_blob = " ".join(_job_text_fields(job_analysis)).casefold()
    for hint in _WORK_STYLE_HINTS:
        if hint in text_blob:
            values.append(hint)
    return _dedupe(values)


def _infer_role_type_from_text(job_analysis: NormalizedJobAnalysis) -> str | None:
    for candidate in _candidate_terms(" ".join(_job_text_fields(job_analysis))):
        normalized = normalize_role_taxonomy(candidate)
        if normalized.status.value != "passthrough":
            return normalized.canonical
    return None


def _infer_seniority_from_text(job_analysis: NormalizedJobAnalysis) -> str | None:
    for candidate in _candidate_terms(" ".join(_job_text_fields(job_analysis))):
        normalized = normalize_seniority_taxonomy(candidate)
        if normalized.status.value != "passthrough":
            return normalized.canonical
    return None


def _role_family_for_role_type(role_type: str | None) -> str | None:
    if role_type in {"frontend", "backend", "fullstack", "devops", "data", "ml", "individual_contributor", "leadership"}:
        return "engineering"
    if role_type == "management":
        return "management"
    if role_type in {"product", "design"}:
        return role_type
    return None


def _estimate_parser_confidence(
    *,
    technical_skills: list[str],
    must_have_skills: list[str],
    role_type: str | None,
    seniority_target: str | None,
    domain_targets: list[str],
    fallback_applied: bool,
) -> float:
    score = 0.2
    if technical_skills:
        score += 0.25
    if must_have_skills:
        score += 0.2
    if role_type is not None:
        score += 0.15
    if seniority_target is not None:
        score += 0.1
    if domain_targets:
        score += 0.1
    if fallback_applied:
        score -= 0.1
    return max(0.1, min(1.0, round(score, 2)))


def _bucket_confidence(values: list[str], base_confidence: float, fallback_applied: bool) -> float:
    if not values:
        return 0.1
    penalty = 0.1 if fallback_applied else 0.0
    return max(0.1, min(1.0, round(base_confidence - penalty, 2)))


def _job_text_fields(job_analysis: NormalizedJobAnalysis) -> list[str]:
    return [
        *job_analysis.technical_skills,
        *job_analysis.must_have_requirements,
        *job_analysis.nice_to_have_requirements,
        *job_analysis.soft_skills,
        *job_analysis.company_culture_signals,
        *job_analysis.key_action_verbs,
        *( [job_analysis.industry_domain] if job_analysis.industry_domain else [] ),
        *( [job_analysis.role_type.value] if job_analysis.role_type else [] ),
        *( [job_analysis.seniority_level.value] if job_analysis.seniority_level else [] ),
    ]


def _domain_source_text(job_analysis: NormalizedJobAnalysis) -> list[str]:
    return [
        *job_analysis.technical_skills,
        *job_analysis.must_have_requirements,
        *job_analysis.nice_to_have_requirements,
    ]


def _candidate_terms(value: str) -> list[str]:
    tokens = [token for token in _TOKEN_PATTERN.findall(value)]
    candidates = list(tokens)
    for ngram_size in (2, 3):
        for index in range(len(tokens) - ngram_size + 1):
            candidates.append(" ".join(tokens[index : index + ngram_size]))
    return candidates


def _dedupe(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(value.split()).strip()
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized
