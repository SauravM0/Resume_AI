"""Hybrid Phase 2 scoring engine with deterministic and semantic relevance support."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pydantic import Field

from .evidence_models import CanonicalEvidenceUnit, WeakEvidenceTag
from .job_feature_adapter import JobRankingFeatures
from .models import EvidenceStrength, StrictModel, VerifiedStatus
from .normalization import normalize_seniority_taxonomy
from .scoring_config import (
    DEFAULT_HYBRID_SCORING_CONFIG,
    HybridScoringConfig,
    SemanticFallbackBehavior,
)
from .semantic_scoring import (
    NullSemanticScorer,
    SemanticScorer,
    SemanticScoringResult,
)

_SENIORITY_ORDER = (
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "director",
    "executive",
)


class ScoreComponent(StrictModel):
    """Explainable sub-score for one scoring dimension."""

    value: float = Field(ge=-100.0, le=100.0)
    weight: float = Field(ge=0.0, le=100.0)
    rationale: str


class HybridScoreResult(StrictModel):
    """Full explainable score output for a canonical evidence unit."""

    evidence_unit_id: str
    total_score: float = Field(ge=0.0, le=100.0)
    component_scores: dict[str, ScoreComponent]
    matched_required_skills: list[str] = Field(default_factory=list)
    matched_preferred_skills: list[str] = Field(default_factory=list)
    mismatch_signals: list[str] = Field(default_factory=list)
    explanation_fragments: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)
    semantic_score: SemanticScoringResult = Field(default_factory=SemanticScoringResult)


@dataclass(slots=True)
class HybridScoringEngine:
    """Deterministic-first scoring engine with structured semantic extension points."""

    config: HybridScoringConfig = field(default_factory=lambda: DEFAULT_HYBRID_SCORING_CONFIG)
    semantic_scorer: SemanticScorer = field(default_factory=NullSemanticScorer)

    def score_evidence_unit(
        self,
        evidence_unit: CanonicalEvidenceUnit,
        job_features: JobRankingFeatures,
        *,
        today: date | None = None,
    ) -> HybridScoreResult:
        weights = self.config.weights
        thresholds = self.config.thresholds

        matched_required = _intersect(
            evidence_unit.normalized_skills + evidence_unit.normalized_tools,
            job_features.canonical_must_have_skills.values,
        )
        matched_preferred = _intersect(
            evidence_unit.normalized_skills + evidence_unit.normalized_tools,
            job_features.canonical_nice_to_have_skills.values,
        )

        must_have_score = _weighted_overlap(
            matched_required,
            job_features.canonical_must_have_skills.values,
            weights.must_have_skill_overlap,
        )
        nice_to_have_score = _weighted_overlap(
            matched_preferred,
            job_features.canonical_nice_to_have_skills.values,
            weights.nice_to_have_skill_overlap,
        )

        role_family_score, role_family_fragment = _role_family_score(
            evidence_unit,
            job_features,
            weights.role_family_relevance,
        )
        seniority_score, seniority_fragment, seniority_mismatch = _seniority_score(
            evidence_unit,
            job_features,
            weights.seniority_relevance,
        )
        domain_score = _weighted_overlap(
            _intersect(evidence_unit.normalized_domains, job_features.domain_targets),
            job_features.keyword_priority_buckets.get("domain_scoring", job_features.domain_targets),
            weights.domain_relevance,
        )
        impact_score = _impact_score(evidence_unit, weights.impact_strength, thresholds.strong_impact_signal_threshold)
        recency_score = _recency_score(evidence_unit, weights.recency, thresholds, today=today)
        evidence_strength_score = _evidence_strength_score(
            evidence_unit.evidence_strength,
            evidence_unit.verified_status,
            weights.evidence_strength,
        )
        quantified_bonus = _quantified_outcome_bonus(
            evidence_unit,
            weights.quantified_outcome_bonus,
        )
        title_score = _title_responsibility_score(
            evidence_unit,
            job_features,
            weights.title_responsibility_relevance,
        )
        semantic_result = self._semantic_score(evidence_unit, job_features)
        semantic_score = round(semantic_result.score * weights.semantic_similarity, 2)

        penalties, mismatch_signals = _penalty_bundle(
            evidence_unit,
            thresholds,
            seniority_mismatch=seniority_mismatch,
            matched_required=matched_required,
            matched_preferred=matched_preferred,
            role_family_score=role_family_score,
            domain_score=domain_score,
            title_score=title_score,
            impact_score=impact_score,
            stale_evidence=_normalize_weighted_component(
                recency_score,
                weights.recency,
            ) <= 0.35,
        )

        component_scores = {
            "must_have_skill_overlap": ScoreComponent(
                value=must_have_score,
                weight=weights.must_have_skill_overlap,
                rationale=f"matched {len(matched_required)} required skills",
            ),
            "nice_to_have_skill_overlap": ScoreComponent(
                value=nice_to_have_score,
                weight=weights.nice_to_have_skill_overlap,
                rationale=f"matched {len(matched_preferred)} preferred skills",
            ),
            "role_family_relevance": ScoreComponent(
                value=role_family_score,
                weight=weights.role_family_relevance,
                rationale=role_family_fragment,
            ),
            "seniority_relevance": ScoreComponent(
                value=seniority_score,
                weight=weights.seniority_relevance,
                rationale=seniority_fragment,
            ),
            "domain_relevance": ScoreComponent(
                value=domain_score,
                weight=weights.domain_relevance,
                rationale=f"matched {len(_intersect(evidence_unit.normalized_domains, job_features.domain_targets))} domain targets",
            ),
            "impact_strength": ScoreComponent(
                value=impact_score,
                weight=weights.impact_strength,
                rationale=f"{len(evidence_unit.impact_signals)} impact signals present",
            ),
            "recency": ScoreComponent(
                value=recency_score,
                weight=weights.recency,
                rationale="recency based on evidence dates",
            ),
            "evidence_strength": ScoreComponent(
                value=evidence_strength_score,
                weight=weights.evidence_strength,
                rationale=f"evidence strength {evidence_unit.evidence_strength.value} / {evidence_unit.verified_status.value}",
            ),
            "quantified_outcome_bonus": ScoreComponent(
                value=quantified_bonus,
                weight=weights.quantified_outcome_bonus,
                rationale="metrics or quantified outcomes detected",
            ),
            "title_responsibility_relevance": ScoreComponent(
                value=title_score,
                weight=weights.title_responsibility_relevance,
                rationale="title and responsibility theme overlap",
            ),
            "semantic_similarity": ScoreComponent(
                value=semantic_score,
                weight=weights.semantic_similarity,
                rationale=semantic_result.confidence_note or "semantic scorer applied",
            ),
            "penalties": ScoreComponent(
                value=-penalties,
                weight=0.0,
                rationale="duplicate and weak-evidence penalties",
            ),
        }

        explanation_fragments = [
            f"required skills: {', '.join(matched_required)}" if matched_required else "no required skills matched",
            f"preferred skills: {', '.join(matched_preferred)}" if matched_preferred else "no preferred skills matched",
            role_family_fragment,
            seniority_fragment,
        ]
        if domain_score > 0:
            explanation_fragments.append("domain overlap present")
        if quantified_bonus > 0:
            explanation_fragments.append("quantified outcomes present")
        if penalties > 0:
            explanation_fragments.append("penalties applied for weak or duplicate evidence")

        confidence_notes = []
        if semantic_result.confidence_note:
            confidence_notes.append(semantic_result.confidence_note)
        if evidence_unit.duplicate_of is not None:
            confidence_notes.append(f"duplicate of {evidence_unit.duplicate_of}")
        if evidence_unit.weak_evidence_tags:
            confidence_notes.append(
                "weak evidence tags: " + ", ".join(tag.value for tag in evidence_unit.weak_evidence_tags)
            )

        total = round(
            max(
                0.0,
                min(
                    100.0,
                    must_have_score
                    + nice_to_have_score
                    + role_family_score
                    + seniority_score
                    + domain_score
                    + impact_score
                    + recency_score
                    + evidence_strength_score
                    + quantified_bonus
                    + title_score
                    + semantic_score
                    - penalties,
                ),
            ),
            2,
        )

        return HybridScoreResult(
            evidence_unit_id=evidence_unit.evidence_unit_id,
            total_score=total,
            component_scores=component_scores,
            matched_required_skills=matched_required,
            matched_preferred_skills=matched_preferred,
            mismatch_signals=mismatch_signals,
            explanation_fragments=explanation_fragments,
            confidence_notes=confidence_notes,
            semantic_score=semantic_result,
        )

    def _semantic_score(
        self,
        evidence_unit: CanonicalEvidenceUnit,
        job_features: JobRankingFeatures,
    ) -> SemanticScoringResult:
        semantic_config = self.config.semantic
        if not semantic_config.enabled or self.config.weights.semantic_similarity <= 0:
            return SemanticScoringResult(
                score=0.0,
                matched_concepts=[],
                confidence_note="semantic scoring disabled by configuration",
            )
        try:
            return self.semantic_scorer.score(evidence_unit, job_features)
        except Exception as exc:
            if semantic_config.fallback_behavior == SemanticFallbackBehavior.RAISE:
                raise
            if semantic_config.fallback_behavior == SemanticFallbackBehavior.DISABLED:
                return SemanticScoringResult(
                    score=0.0,
                    matched_concepts=[],
                    confidence_note="semantic scoring disabled after provider failure",
                )
            return SemanticScoringResult(
                score=0.0,
                matched_concepts=[],
                confidence_note=f"semantic scorer unavailable; fallback applied: {exc.__class__.__name__}",
            )


def _weighted_overlap(matches: list[str], targets: list[str], weight: float) -> float:
    if not targets or not matches:
        return 0.0
    return round((len(matches) / len(_dedupe(targets))) * weight, 2)


def _role_family_score(
    evidence_unit: CanonicalEvidenceUnit,
    job_features: JobRankingFeatures,
    weight: float,
) -> tuple[float, str]:
    if not job_features.role_family:
        return 0.0, "role family unavailable"
    evidence_roles = set(evidence_unit.inferred_role_types)
    if job_features.role_type and job_features.role_type in evidence_roles:
        return weight, "direct role type match"
    if job_features.role_family == "engineering" and evidence_roles.intersection(
        {"frontend", "backend", "fullstack", "devops", "data", "ml", "individual_contributor", "leadership"}
    ):
        return round(weight * 0.75, 2), "engineering family alignment"
    return 0.0, "role family mismatch"


def _seniority_score(
    evidence_unit: CanonicalEvidenceUnit,
    job_features: JobRankingFeatures,
    weight: float,
) -> tuple[float, str, bool]:
    if not job_features.seniority_target or not evidence_unit.seniority_signals:
        return 0.0, "seniority unavailable", False

    evidence_level = evidence_unit.seniority_signals[0]
    evidence_index = _seniority_index(evidence_level)
    target_index = _seniority_index(job_features.seniority_target)
    if evidence_index is None or target_index is None:
        return 0.0, "seniority unavailable", False
    if evidence_index >= target_index:
        return weight, "seniority aligned", False
    if evidence_index == target_index - 1:
        return round(weight * 0.5, 2), "slightly below target seniority", True
    return 0.0, "below target seniority", True


def _impact_score(
    evidence_unit: CanonicalEvidenceUnit,
    weight: float,
    strong_threshold: int,
) -> float:
    signals = len(evidence_unit.impact_signals)
    if signals == 0:
        return 0.0
    if signals >= strong_threshold:
        return weight
    return round(weight * 0.6, 2)


def _recency_score(
    evidence_unit: CanonicalEvidenceUnit,
    weight: float,
    thresholds,
    *,
    today: date | None = None,
) -> float:
    reference = _parse_partial_date(evidence_unit.recency.end_date) or _parse_partial_date(
        evidence_unit.recency.start_date
    )
    if reference is None:
        return 0.0

    current = today or datetime.now(UTC).date()
    months_ago = _months_between(reference, current)
    if months_ago <= thresholds.recency_recent_months:
        return weight
    if months_ago <= thresholds.recency_moderate_months:
        return round(weight * 0.75, 2)
    if months_ago <= thresholds.recency_stale_months:
        return round(weight * 0.4, 2)
    return round(weight * 0.1, 2)


def _evidence_strength_score(
    evidence_strength: EvidenceStrength,
    verified_status: VerifiedStatus,
    weight: float,
) -> float:
    strength_factor = {
        EvidenceStrength.WEAK: 0.2,
        EvidenceStrength.MODERATE: 0.5,
        EvidenceStrength.STRONG: 0.8,
        EvidenceStrength.VERIFIED: 1.0,
    }[evidence_strength]
    verification_bonus = {
        VerifiedStatus.UNVERIFIED: 0.0,
        VerifiedStatus.SELF_REPORTED: 0.05,
        VerifiedStatus.CORROBORATED: 0.15,
        VerifiedStatus.VERIFIED: 0.2,
    }[verified_status]
    return round(min(1.0, strength_factor + verification_bonus) * weight, 2)


def _quantified_outcome_bonus(
    evidence_unit: CanonicalEvidenceUnit,
    weight: float,
) -> float:
    if evidence_unit.metrics_present or "metrics_present" in evidence_unit.impact_signals:
        return weight
    raw = evidence_unit.raw_text
    if any(char.isdigit() for char in raw) or "%" in raw:
        return round(weight * 0.7, 2)
    return 0.0


def _title_responsibility_score(
    evidence_unit: CanonicalEvidenceUnit,
    job_features: JobRankingFeatures,
    weight: float,
) -> float:
    matched = _intersect(
        [evidence_unit.provenance.source_entity_title or "", *evidence_unit.inferred_role_types],
        [*job_features.responsibility_themes, *( [job_features.role_type] if job_features.role_type else [] )],
    )
    if matched:
        return weight
    return 0.0


def _penalty_bundle(
    evidence_unit: CanonicalEvidenceUnit,
    thresholds,
    *,
    seniority_mismatch: bool,
    matched_required: list[str],
    matched_preferred: list[str],
    role_family_score: float,
    domain_score: float,
    title_score: float,
    impact_score: float,
    stale_evidence: bool,
) -> tuple[float, list[str]]:
    penalty = 0.0
    mismatch_signals: list[str] = []
    if seniority_mismatch:
        mismatch_signals.append("seniority_mismatch")
    if evidence_unit.duplicate_of is not None:
        if WeakEvidenceTag.DUPLICATE in evidence_unit.weak_evidence_tags:
            penalty += thresholds.duplicate_penalty
            mismatch_signals.append("duplicate_evidence")
        else:
            penalty += thresholds.near_duplicate_penalty
            mismatch_signals.append("near_duplicate_evidence")
    if WeakEvidenceTag.LOW_INFORMATION in evidence_unit.weak_evidence_tags:
        penalty += thresholds.low_information_penalty
        mismatch_signals.append("low_information")
    if WeakEvidenceTag.VAGUE in evidence_unit.weak_evidence_tags:
        penalty += thresholds.vague_penalty
        mismatch_signals.append("vague_evidence")
    if WeakEvidenceTag.UNSUPPORTED_SKILL_MENTION in evidence_unit.weak_evidence_tags:
        penalty += thresholds.unsupported_skill_penalty
        mismatch_signals.append("unsupported_skill_mention")
    weak_alignment = (
        not matched_required
        and not matched_preferred
        and role_family_score <= 0
        and domain_score <= 0
        and title_score <= 0
    )
    if weak_alignment and impact_score <= 0:
        penalty += thresholds.weak_alignment_penalty
        mismatch_signals.append("weak_strategic_alignment")
    if weak_alignment and stale_evidence:
        penalty += thresholds.stale_irrelevant_penalty
        mismatch_signals.append("stale_irrelevant_history")
    return round(penalty, 2), mismatch_signals


def _intersect(values: list[str], targets: list[str]) -> list[str]:
    normalized_targets = {_comparison_key(value): value for value in targets if value}
    matched: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _comparison_key(value)
        if key in normalized_targets and key not in seen:
            matched.append(normalized_targets[key])
            seen.add(key)
    return matched


def _normalize_weighted_component(value: float, weight: float) -> float:
    if weight <= 0:
        return 0.0
    return max(0.0, min(1.0, value / weight))


def _comparison_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _dedupe(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _comparison_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _seniority_index(value: str) -> int | None:
    canonical = normalize_seniority_taxonomy(value).canonical
    if canonical not in _SENIORITY_ORDER:
        return None
    return _SENIORITY_ORDER.index(canonical)


def _parse_partial_date(value: str | None) -> date | None:
    if value is None:
        return None
    parts = value.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) >= 2 else 1
        day = int(parts[2]) if len(parts) >= 3 else 1
    except (TypeError, ValueError):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _months_between(older: date, newer: date) -> int:
    months = (newer.year - older.year) * 12 + (newer.month - older.month)
    if newer.day < older.day:
        months -= 1
    return max(0, months)
