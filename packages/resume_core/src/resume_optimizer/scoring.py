"""Deterministic scoring helpers for Phase 2 evidence ranking."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from pydantic import Field

from .job_feature_adapter import JobRankingFeatures, adapt_job_analysis_to_ranking_features
from .job_models import NormalizedJobAnalysis
from .models import StrictModel
from .normalization import normalize_seniority_taxonomy
from .phase2_config import DEFAULT_PHASE2_CONFIG
from .ranking_models import CandidateEvidenceItem

KEYWORD_WEIGHT = DEFAULT_PHASE2_CONFIG.weights.keyword
RELEVANT_FOR_WEIGHT = DEFAULT_PHASE2_CONFIG.weights.relevant_for
DOMAIN_WEIGHT = DEFAULT_PHASE2_CONFIG.weights.domain
SENIORITY_WEIGHT = DEFAULT_PHASE2_CONFIG.weights.seniority
IMPACT_WEIGHT = DEFAULT_PHASE2_CONFIG.weights.impact
RECENCY_WEIGHT = DEFAULT_PHASE2_CONFIG.weights.recency

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
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

class EvidenceScoreResult(StrictModel):
    """Scoring output for a single evidence item."""

    total_score: float = Field(ge=0.0, le=100.0)
    keyword_score: float = Field(ge=0.0, le=KEYWORD_WEIGHT)
    relevant_for_score: float = Field(ge=0.0, le=RELEVANT_FOR_WEIGHT)
    domain_score: float = Field(ge=0.0, le=DOMAIN_WEIGHT)
    seniority_score: float = Field(ge=0.0, le=SENIORITY_WEIGHT)
    impact_score: float = Field(ge=0.0, le=IMPACT_WEIGHT)
    recency_score: float = Field(ge=0.0, le=RECENCY_WEIGHT)
    matched_keywords: list[str] = Field(default_factory=list)
    matched_relevant_for: list[str] = Field(default_factory=list)
    matched_domains: list[str] = Field(default_factory=list)


def score_keyword_overlap(
    evidence_keywords: list[str],
    job_analysis: NormalizedJobAnalysis | JobRankingFeatures,
) -> tuple[float, list[str]]:
    """Return the weighted keyword overlap score and matched keywords."""

    features = _ensure_job_features(job_analysis)
    return _score_overlap(
        evidence_keywords,
        features.canonical_all_skills,
        KEYWORD_WEIGHT,
    )


def score_relevant_for_overlap(
    evidence_relevant_for: list[str],
    job_analysis: NormalizedJobAnalysis | JobRankingFeatures,
) -> tuple[float, list[str]]:
    """Return the weighted thematic overlap score and matched tags."""

    job_targets = _job_relevant_for_targets(_ensure_job_features(job_analysis))
    return _score_overlap(evidence_relevant_for, job_targets, RELEVANT_FOR_WEIGHT)


def score_domain_overlap(
    evidence_domains: list[str],
    job_analysis: NormalizedJobAnalysis | JobRankingFeatures,
) -> tuple[float, list[str]]:
    """Return the weighted domain overlap score and matched domains."""

    features = _ensure_job_features(job_analysis)
    return _score_overlap(
        evidence_domains,
        features.keyword_priority_buckets.get("domain_scoring", features.domain_targets),
        DOMAIN_WEIGHT,
    )


def score_seniority_alignment(
    evidence_level: str | None,
    job_analysis: NormalizedJobAnalysis | JobRankingFeatures,
) -> float:
    """Return a small score for evidence seniority alignment."""

    features = _ensure_job_features(job_analysis)
    if evidence_level is None or features.seniority_target is None:
        return 0.0

    evidence_index = _seniority_index(evidence_level)
    target_index = _seniority_index(features.seniority_target)
    if evidence_index is None or target_index is None:
        return 0.0
    if evidence_index >= target_index:
        return SENIORITY_WEIGHT
    if evidence_index == target_index - 1:
        return round(SENIORITY_WEIGHT * 0.5, 2)
    return 0.0


def score_impact_preference(impact: float | None) -> float:
    """Return a small score preference for higher-impact evidence."""

    if impact is None:
        return 0.0
    return round(max(0.0, min(1.0, impact)) * IMPACT_WEIGHT, 2)


def score_recency_preference(
    *,
    start: str | None,
    end: str | None,
    today: date | None = None,
) -> float:
    """Return a small score preference for more recent evidence."""

    reference_date = _parse_partial_date(end) or _parse_partial_date(start)
    if reference_date is None:
        return 0.0

    current = today or datetime.now(UTC).date()
    months_ago = _months_between(reference_date, current)

    if months_ago <= 12:
        return RECENCY_WEIGHT
    if months_ago <= 36:
        return round(RECENCY_WEIGHT * 0.75, 2)
    if months_ago <= 60:
        return round(RECENCY_WEIGHT * 0.5, 2)
    if months_ago <= 96:
        return round(RECENCY_WEIGHT * 0.25, 2)
    return 0.0


def score_evidence_item(
    evidence_item: CandidateEvidenceItem,
    job_analysis: NormalizedJobAnalysis | JobRankingFeatures,
    *,
    today: date | None = None,
) -> EvidenceScoreResult:
    """Return a bounded aggregate score and match details for one evidence item."""

    features = _ensure_job_features(job_analysis)

    keyword_score, matched_keywords = score_keyword_overlap(
        evidence_item.keywords,
        features,
    )
    relevant_for_score, matched_relevant_for = score_relevant_for_overlap(
        evidence_item.relevant_for,
        features,
    )
    domain_score, matched_domains = score_domain_overlap(
        evidence_item.domain_tags,
        features,
    )
    seniority_score = score_seniority_alignment(evidence_item.level, features)
    impact_score = score_impact_preference(evidence_item.impact)
    recency_score = score_recency_preference(
        start=evidence_item.start,
        end=evidence_item.end,
        today=today,
    )

    total_score = round(
        keyword_score
        + relevant_for_score
        + domain_score
        + seniority_score
        + impact_score
        + recency_score,
        2,
    )

    return EvidenceScoreResult(
        total_score=max(0.0, min(100.0, total_score)),
        keyword_score=keyword_score,
        relevant_for_score=relevant_for_score,
        domain_score=domain_score,
        seniority_score=seniority_score,
        impact_score=impact_score,
        recency_score=recency_score,
        matched_keywords=matched_keywords,
        matched_relevant_for=matched_relevant_for,
        matched_domains=matched_domains,
    )


def _score_overlap(
    evidence_values: list[str],
    job_values: list[str],
    weight: float,
) -> tuple[float, list[str]]:
    normalized_job = {_comparison_key(value): value for value in job_values}
    if not normalized_job:
        return 0.0, []

    matched: list[str] = []
    seen: set[str] = set()
    for value in evidence_values:
        key = _comparison_key(value)
        if key and key in normalized_job and key not in seen:
            matched.append(normalized_job[key])
            seen.add(key)

    if not matched:
        return 0.0, []

    score = round((len(matched) / len(normalized_job)) * weight, 2)
    return score, matched


def _job_relevant_for_targets(features: JobRankingFeatures) -> list[str]:
    values = list(features.keyword_priority_buckets.get("relevant_for", []))
    return _normalize_unique(values)


def _normalize_unique(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = _normalize_text(value)
        if not cleaned:
            continue
        key = _comparison_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)

    return normalized


def _ensure_job_features(
    job_analysis: NormalizedJobAnalysis | JobRankingFeatures,
) -> JobRankingFeatures:
    if isinstance(job_analysis, JobRankingFeatures):
        return job_analysis
    return adapt_job_analysis_to_ranking_features(job_analysis)


def _comparison_key(value: str) -> str:
    return " ".join(_tokenize(value))


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _seniority_index(value: str) -> int | None:
    key = _comparison_key(normalize_seniority_taxonomy(value).canonical)
    if key not in _SENIORITY_ORDER:
        return None
    return _SENIORITY_ORDER.index(key)


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
