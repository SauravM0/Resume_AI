"""Deterministic confidence scoring for Phase 1 merge decisions."""

from __future__ import annotations

from typing import Any

from .phase1_merge_normalization import clamp_score, fold_key, repeated_signal_count
from .phase1_models import RequirementConfidenceItemType
from .phase1_deterministic_models import DeterministicJobDescriptionExtraction


def confidence_for_item(
    items: list[dict[str, Any]],
    item_type: RequirementConfidenceItemType | None,
    value: Any,
) -> float:
    """Read one item-level confidence from a raw or repaired payload list."""

    if item_type is None:
        return 0.0
    folded = fold_key(str(value))
    for item in items:
        if item.get("item_type") != item_type.value:
            continue
        if fold_key(str(item.get("item_value", ""))) == folded:
            return clamp_score(item.get("confidence"))
    return 0.0


def score_job_title_confidence(
    *,
    title: str | None,
    deterministic_title: str | None,
    deterministic_confidence: float,
    llm_confidence: float,
    deterministic: DeterministicJobDescriptionExtraction,
    jd_quality_score: float,
) -> float:
    """Score confidence for the merged job title."""

    if not title:
        return 0.0
    return score_merged_item_confidence(
        final_value=title,
        deterministic_value=deterministic_title,
        deterministic_confidence=deterministic_confidence,
        llm_confidence=llm_confidence,
        repeated_count=repeated_signal_count(title, deterministic),
        explicit=True,
        inferred=False,
        conflict=bool(deterministic_title and fold_key(title) != fold_key(deterministic_title)),
        jd_quality_score=jd_quality_score,
    )


def score_role_axis_confidence(
    *,
    final_value: str,
    deterministic_value: str,
    deterministic_confidence: float,
    llm_confidence: float,
    jd_quality_score: float,
    deterministic: DeterministicJobDescriptionExtraction,
) -> float:
    """Score confidence for role family and organizational mode values."""

    return score_merged_item_confidence(
        final_value=final_value,
        deterministic_value=deterministic_value,
        deterministic_confidence=deterministic_confidence,
        llm_confidence=llm_confidence,
        repeated_count=repeated_signal_count(final_value.replace("_", " "), deterministic),
        explicit=False,
        inferred=True,
        conflict=fold_key(final_value) != fold_key(deterministic_value),
        jd_quality_score=jd_quality_score,
    )


def score_requirement_confidence(
    *,
    value: str,
    deterministic: DeterministicJobDescriptionExtraction,
    llm_confidence: float,
    explicit_grounded: bool,
    jd_quality_score: float,
    inferred: bool = False,
) -> float:
    """Score a requirement or recruiter-intent item for downstream weighting."""

    repeated_count = repeated_signal_count(value, deterministic)
    deterministic_signal = 0.62 if explicit_grounded else 0.28
    return score_merged_item_confidence(
        final_value=value,
        deterministic_value=value if explicit_grounded else None,
        deterministic_confidence=deterministic_signal,
        llm_confidence=llm_confidence,
        repeated_count=repeated_count,
        explicit=explicit_grounded,
        inferred=inferred or not explicit_grounded,
        conflict=False,
        jd_quality_score=jd_quality_score,
    )


def score_overall_parser_confidence(
    *,
    deterministic_parser_confidence: float,
    llm_parser_confidence: float | None,
    jd_quality_score: float,
    ambiguity_count: int,
    conflict_count: int,
    inferred_item_count: int,
) -> float:
    """Score the final parser confidence conservatively and explainably."""

    base = (deterministic_parser_confidence * 0.55) + (
        (llm_parser_confidence if llm_parser_confidence is not None else deterministic_parser_confidence)
        * 0.45
    )
    quality_adjusted = base * (0.65 + (0.35 * jd_quality_score))
    penalty = min(ambiguity_count, 4) * 0.05
    penalty += min(conflict_count, 4) * 0.06
    penalty += min(inferred_item_count, 6) * 0.015
    adjusted = clamp_score(quality_adjusted - penalty + 0.12)
    if llm_parser_confidence is not None:
        return min(adjusted, clamp_score(llm_parser_confidence))
    return adjusted


def score_merged_item_confidence(
    *,
    final_value: str,
    deterministic_value: str | None,
    deterministic_confidence: float,
    llm_confidence: float,
    repeated_count: int,
    explicit: bool,
    inferred: bool,
    conflict: bool,
    jd_quality_score: float,
) -> float:
    """Blend deterministic and LLM evidence into one bounded confidence score."""

    if not final_value:
        return 0.0
    score = max(deterministic_confidence, llm_confidence)
    if deterministic_confidence and llm_confidence:
        score = (deterministic_confidence * 0.62) + (llm_confidence * 0.38)
    score += min(max(repeated_count - 1, 0), 3) * 0.05
    if explicit:
        score += 0.08
    if inferred:
        score -= 0.1
    if conflict:
        score -= 0.14
    if deterministic_value and fold_key(final_value) == fold_key(deterministic_value):
        score += 0.04
    score *= 0.7 + (0.3 * jd_quality_score)
    return clamp_score(score)
