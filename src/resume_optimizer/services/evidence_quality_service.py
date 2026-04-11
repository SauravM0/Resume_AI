"""Deterministic intrinsic quality scoring for Phase 2 evidence units."""

from __future__ import annotations

from datetime import UTC, date, datetime
import re

from ..evidence_models import (
    DeliveryScope,
    EvidenceQuality,
    EvidenceQualityBand,
    EvidenceUnit,
    LeadershipSignal,
    OwnershipLevel,
    RewriteSafetyLevel,
    WeakEvidenceTag,
)
from ..normalization import normalize_evidence_text

_PASSIVE_OR_VAGUE_PATTERNS = re.compile(
    r"\b(helped|assisted|participated|worked on|involved in|responsible for)\b",
    re.IGNORECASE,
)
_OUTCOME_TERMS = re.compile(
    r"\b(increased|reduced|improved|boosted|lifted|cut|saved|accelerated|decreased|grew)\b",
    re.IGNORECASE,
)
_SCOPE_TERMS = re.compile(
    r"\b(team|teams|org|organization|company|customers|users|platform|system|service|workflow|feature)\b",
    re.IGNORECASE,
)
_READABILITY_SPLIT = re.compile(r"[.!?;,:()]")


class EvidenceQualityService:
    """Score evidence quality independent of job-specific ranking."""

    def score(self, evidence_unit: EvidenceUnit, *, today: date | None = None) -> EvidenceUnit:
        resolved_today = today or datetime.now(UTC).date()
        bundle = normalize_evidence_text(
            evidence_unit.raw_text,
            title=evidence_unit.provenance.source_parent_title,
        )

        quality = evidence_unit.quality.model_copy(
            update=_quality_updates(evidence_unit, bundle, today=resolved_today)
        )
        return evidence_unit.model_copy(update={"quality": quality})


DEFAULT_EVIDENCE_QUALITY_SERVICE = EvidenceQualityService()


def _quality_updates(
    evidence_unit: EvidenceUnit,
    bundle,
    *,
    today: date,
) -> dict[str, object]:
    specificity = _specificity_score(evidence_unit)
    metric_presence = _metric_presence_score(evidence_unit)
    outcome_clarity = _outcome_clarity_score(evidence_unit)
    ownership_clarity = _ownership_clarity_score(evidence_unit)
    tool_specificity = _tool_specificity_score(evidence_unit)
    scope_clarity = _scope_clarity_score(evidence_unit)
    recency = _recency_score(evidence_unit, today=today)
    readability = _readability_score(evidence_unit)
    rewrite_safety = _rewrite_safety_score(evidence_unit)
    strategic_usefulness = _strategic_usefulness_score(evidence_unit)
    clarity = _clarity_score(evidence_unit, readability, outcome_clarity)

    weights = {
        "specificity": 0.16,
        "metric_presence": 0.14,
        "outcome_clarity": 0.14,
        "ownership_clarity": 0.10,
        "tool_specificity": 0.08,
        "scope_clarity": 0.08,
        "recency": 0.10,
        "readability": 0.08,
        "rewrite_safety": 0.04,
        "strategic_usefulness": 0.08,
    }
    overall = round(
        (
            specificity * weights["specificity"]
            + metric_presence * weights["metric_presence"]
            + outcome_clarity * weights["outcome_clarity"]
            + ownership_clarity * weights["ownership_clarity"]
            + tool_specificity * weights["tool_specificity"]
            + scope_clarity * weights["scope_clarity"]
            + recency * weights["recency"]
            + readability * weights["readability"]
            + rewrite_safety * weights["rewrite_safety"]
            + strategic_usefulness * weights["strategic_usefulness"]
        ),
        4,
    )
    band = _quality_band(overall)
    omit_risk = band == EvidenceQualityBand.POOR or (
        band == EvidenceQualityBand.WEAK and evidence_unit.coverage.source_metric_count == 0 and not evidence_unit.normalized_tools
    )

    weak_tags = list(evidence_unit.quality.weak_evidence_tags)
    if overall < 0.45 and WeakEvidenceTag.LOW_INFORMATION not in weak_tags:
        weak_tags.append(WeakEvidenceTag.LOW_INFORMATION)

    return {
        "clarity_score": clarity,
        "specificity_score": specificity,
        "metric_presence_score": metric_presence,
        "outcome_clarity_score": outcome_clarity,
        "ownership_clarity_score": ownership_clarity,
        "tool_specificity_score": tool_specificity,
        "scope_clarity_score": scope_clarity,
        "recency_score": recency,
        "readability_score": readability,
        "rewrite_safety_score": rewrite_safety,
        "strategic_usefulness_score": strategic_usefulness,
        "overall_quality_score": overall,
        "quality_band": band,
        "omit_risk": omit_risk,
        "weak_evidence_tags": weak_tags,
    }


def _specificity_score(evidence_unit: EvidenceUnit) -> float:
    token_count = len(re.findall(r"[A-Za-z0-9.+#/-]+", evidence_unit.raw_text))
    concrete_signal_count = sum(
        [
            1 if evidence_unit.coverage.source_metric_count > 0 else 0,
            1 if evidence_unit.normalized_tools else 0,
            1 if evidence_unit.normalized_domains else 0,
            1 if any(char.isdigit() for char in evidence_unit.raw_text) else 0,
        ]
    )
    if token_count >= 14 and concrete_signal_count >= 2:
        return 0.9
    if token_count >= 10 and concrete_signal_count >= 1:
        return 0.75
    if token_count >= 7:
        return 0.55
    return 0.3


def _metric_presence_score(evidence_unit: EvidenceUnit) -> float:
    if evidence_unit.coverage.source_metric_count >= 2:
        return 1.0
    if evidence_unit.coverage.source_metric_count == 1:
        return 0.82
    if any(char.isdigit() for char in evidence_unit.raw_text):
        return 0.55
    return 0.15


def _outcome_clarity_score(evidence_unit: EvidenceUnit) -> float:
    has_outcome_term = bool(_OUTCOME_TERMS.search(evidence_unit.raw_text))
    if has_outcome_term and evidence_unit.coverage.source_metric_count > 0:
        return 0.92
    if has_outcome_term:
        return 0.72
    if evidence_unit.signals.business_outcome_hints:
        return 0.62
    return 0.25


def _ownership_clarity_score(evidence_unit: EvidenceUnit) -> float:
    if evidence_unit.signals.ownership_level == OwnershipLevel.OWNER:
        return 0.92
    if evidence_unit.signals.ownership_level == OwnershipLevel.DRIVER:
        return 0.72
    if _PASSIVE_OR_VAGUE_PATTERNS.search(evidence_unit.raw_text):
        return 0.22
    return 0.4


def _tool_specificity_score(evidence_unit: EvidenceUnit) -> float:
    if len(evidence_unit.normalized_tools) >= 3:
        return 0.88
    if len(evidence_unit.normalized_tools) == 2:
        return 0.72
    if len(evidence_unit.normalized_tools) == 1:
        return 0.55
    return 0.2


def _scope_clarity_score(evidence_unit: EvidenceUnit) -> float:
    if evidence_unit.signals.delivery_scope in {
        DeliveryScope.PLATFORM,
        DeliveryScope.PRODUCT,
        DeliveryScope.ORGANIZATION,
        DeliveryScope.COMPANY,
    }:
        return 0.84
    if evidence_unit.signals.delivery_scope in {DeliveryScope.SYSTEM, DeliveryScope.FEATURE}:
        return 0.68
    if _SCOPE_TERMS.search(evidence_unit.raw_text):
        return 0.55
    return 0.25


def _recency_score(evidence_unit: EvidenceUnit, *, today: date) -> float:
    if evidence_unit.recency.source_recency_score is not None:
        return round(float(evidence_unit.recency.source_recency_score), 4)
    if evidence_unit.recency.is_current:
        return 0.95
    end_date = evidence_unit.recency.end_date or evidence_unit.recency.start_date
    if end_date is None:
        return 0.45
    try:
        year = int(end_date.split("-")[0])
    except (TypeError, ValueError, IndexError):
        return 0.45
    year_delta = max(0, today.year - year)
    if year_delta <= 1:
        return 0.82
    if year_delta <= 3:
        return 0.62
    if year_delta <= 5:
        return 0.45
    return 0.28


def _readability_score(evidence_unit: EvidenceUnit) -> float:
    text = evidence_unit.raw_text.strip()
    token_count = len(re.findall(r"[A-Za-z0-9.+#/-]+", text))
    clause_count = max(1, len([part for part in _READABILITY_SPLIT.split(text) if part.strip()]))
    passive_penalty = 0.2 if _PASSIVE_OR_VAGUE_PATTERNS.search(text) else 0.0
    if 10 <= token_count <= 28 and clause_count <= 2:
        base = 0.86
    elif 7 <= token_count <= 36:
        base = 0.68
    else:
        base = 0.5
    return max(0.15, round(base - passive_penalty, 4))


def _rewrite_safety_score(evidence_unit: EvidenceUnit) -> float:
    level = evidence_unit.rewrite_safety.level
    if level == RewriteSafetyLevel.SAFE:
        return 0.9
    if level == RewriteSafetyLevel.CAUTION:
        return 0.6
    return 0.25


def _strategic_usefulness_score(evidence_unit: EvidenceUnit) -> float:
    explicit_leadership = any(
        signal in evidence_unit.signals.leadership_signals
        for signal in {
            LeadershipSignal.PEOPLE_MANAGEMENT,
            LeadershipSignal.TECHNICAL_LEADERSHIP,
            LeadershipSignal.CROSS_FUNCTIONAL_LEADERSHIP,
        }
    )
    strong_outcome = bool(evidence_unit.signals.business_outcome_hints)
    scoped_delivery = evidence_unit.signals.delivery_scope in {
        DeliveryScope.SYSTEM,
        DeliveryScope.PLATFORM,
        DeliveryScope.PRODUCT,
        DeliveryScope.ORGANIZATION,
        DeliveryScope.COMPANY,
    }
    score = 0.2
    if explicit_leadership:
        score += 0.24
    if strong_outcome:
        score += 0.22
    if scoped_delivery:
        score += 0.18
    if evidence_unit.coverage.source_metric_count > 0:
        score += 0.16
    if evidence_unit.enrichment.architecture_system_design_score and evidence_unit.enrichment.architecture_system_design_score >= 0.65:
        score += 0.12
    return min(1.0, round(score, 4))


def _clarity_score(
    evidence_unit: EvidenceUnit,
    readability_score: float,
    outcome_clarity_score: float,
) -> float:
    base = (readability_score * 0.65) + (outcome_clarity_score * 0.35)
    if _PASSIVE_OR_VAGUE_PATTERNS.search(evidence_unit.raw_text):
        base -= 0.15
    return max(0.1, round(base, 4))


def _quality_band(overall_score: float) -> EvidenceQualityBand:
    if overall_score >= 0.8:
        return EvidenceQualityBand.STRONG
    if overall_score >= 0.6:
        return EvidenceQualityBand.MEDIUM
    if overall_score >= 0.4:
        return EvidenceQualityBand.WEAK
    return EvidenceQualityBand.POOR
