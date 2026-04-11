"""Structured explainability builders for Phase 2 scoring and selection."""

from __future__ import annotations

import logging

from .evidence_models import CanonicalEvidenceUnit
from .job_feature_adapter import JobRankingFeatures
from .phase2_models import Phase2Diagnostics, RankingExplanation
from .provenance import build_provenance_payload, selection_provenance_payload
from .scoring_engine import HybridScoreResult

logger = logging.getLogger(__name__)


def build_ranking_explanation(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
    job_features: JobRankingFeatures,
) -> RankingExplanation:
    """Build a structured explanation object for one scored evidence unit."""

    matched_keywords = [
        *score_result.matched_required_skills,
        *[
            skill
            for skill in score_result.matched_preferred_skills
            if skill not in score_result.matched_required_skills
        ],
    ]
    matched_requirements = [
        requirement
        for requirement in [
            *job_features.keyword_priority_buckets.get("must_have", []),
            *job_features.keyword_priority_buckets.get("nice_to_have", []),
        ]
        if requirement in matched_keywords
    ]
    warning_signals = _warning_signals(evidence_unit, score_result)
    fragments = [*score_result.explanation_fragments]
    if warning_signals:
        fragments.append("warnings: " + ", ".join(warning_signals))

    summary = (
        "; ".join(fragments[:3]).capitalize() + "."
        if fragments
        else "Selected on available deterministic score signals."
    )
    explanation = RankingExplanation(
        summary=summary,
        matched_keywords=matched_keywords,
        matched_required_skills=score_result.matched_required_skills,
        matched_preferred_skills=score_result.matched_preferred_skills,
        matched_job_requirements=matched_requirements,
        matched_domains=_matched_domains(evidence_unit, score_result),
        matched_relevant_for=_matched_relevant_for(evidence_unit, score_result),
        matched_prioritized_skills=score_result.matched_required_skills,
        mismatch_signals=score_result.mismatch_signals,
        warning_signals=warning_signals,
        explanation_fragments=fragments,
        confidence_notes=score_result.confidence_notes,
        signal_labels=[
            name
            for name, component in score_result.component_scores.items()
            if component.value > 0 and name not in {"must_have_skill_overlap", "nice_to_have_skill_overlap"}
        ],
    )
    logger.debug(
        "phase2 ranking explanation built",
        extra={
            "evidence_unit_id": evidence_unit.evidence_unit_id,
            "summary": explanation.summary,
            "warnings": warning_signals,
        },
    )
    return explanation


def build_selection_reasoning(
    *,
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
    included: bool,
    rank: int | None = None,
    competing_item_ids: list[str] | None = None,
) -> RankingExplanation:
    """Build structured reasoning for why an item was included or excluded."""

    status_fragment = (
        f"included at rank {rank}" if included and rank is not None else "included"
        if included
        else "excluded"
    )
    fragments = [status_fragment, *score_result.explanation_fragments[:2]]
    if not included and competing_item_ids:
        fragments.append("outscored by: " + ", ".join(competing_item_ids[:3]))

    return RankingExplanation(
        summary="; ".join(fragments).capitalize() + ".",
        matched_keywords=[
            *score_result.matched_required_skills,
            *[
                skill
                for skill in score_result.matched_preferred_skills
                if skill not in score_result.matched_required_skills
            ],
        ],
        matched_required_skills=score_result.matched_required_skills,
        matched_preferred_skills=score_result.matched_preferred_skills,
        matched_job_requirements=[],
        matched_domains=_matched_domains(evidence_unit, score_result),
        matched_relevant_for=_matched_relevant_for(evidence_unit, score_result),
        matched_prioritized_skills=score_result.matched_required_skills,
        mismatch_signals=score_result.mismatch_signals,
        warning_signals=_warning_signals(evidence_unit, score_result),
        explanation_fragments=fragments,
        confidence_notes=score_result.confidence_notes,
        signal_labels=[
            name
            for name, component in score_result.component_scores.items()
            if component.value > 0 and name not in {"must_have_skill_overlap", "nice_to_have_skill_overlap"}
        ],
    )


def build_phase2_diagnostics(
    *,
    scored_items: list[tuple[CanonicalEvidenceUnit, HybridScoreResult]],
    selected_item_ids: set[str],
    warnings: list[str] | None = None,
) -> Phase2Diagnostics:
    """Build a diagnostics payload for development inspection and future UI use."""

    warnings = list(warnings or [])
    sorted_items = sorted(scored_items, key=lambda item: item[1].total_score, reverse=True)
    selected = [item for item in sorted_items if item[0].evidence_unit_id in selected_item_ids]
    near_miss = [
        evidence_unit.evidence_unit_id
        for evidence_unit, _ in sorted_items
        if evidence_unit.evidence_unit_id not in selected_item_ids
    ][:3]

    top_requirements = []
    weak_coverage = []
    for _, score_result in selected:
        top_requirements.extend(score_result.matched_required_skills)
        if score_result.component_scores["must_have_skill_overlap"].value == 0:
            weak_coverage.append("missing required skill coverage")
        if "low_information" in score_result.mismatch_signals:
            weak_coverage.append("selected low-information evidence")

    diagnostics = Phase2Diagnostics(
        warnings=_dedupe(warnings),
        top_matched_requirements=_dedupe(top_requirements)[:5],
        weak_coverage_areas=_dedupe(weak_coverage),
        near_miss_item_ids=near_miss,
    )
    logger.debug(
        "phase2 diagnostics built",
        extra={
            "top_matched_requirements": diagnostics.top_matched_requirements,
            "weak_coverage_areas": diagnostics.weak_coverage_areas,
            "near_miss_item_ids": diagnostics.near_miss_item_ids,
        },
    )
    return diagnostics


def scored_item_payload(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
    job_features: JobRankingFeatures,
) -> tuple[dict[str, object], RankingExplanation]:
    """Return API-safe provenance plus explanation for a scored evidence unit."""

    provenance = build_provenance_payload(evidence_unit)
    explanation = build_ranking_explanation(evidence_unit, score_result, job_features)
    return provenance, explanation


def selected_item_payload(scored_provenance: dict[str, object]) -> dict[str, object]:
    """Return trimmed provenance intended for selected-item payloads."""

    return selection_provenance_payload(scored_provenance)


def _warning_signals(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
) -> list[str]:
    warnings: list[str] = []
    if score_result.component_scores["recency"].value <= 4.0 and (
        score_result.component_scores["must_have_skill_overlap"].value > 0
        or score_result.component_scores["nice_to_have_skill_overlap"].value > 0
    ):
        warnings.append("high_overlap_but_old")
    if score_result.component_scores["must_have_skill_overlap"].value > 0 and score_result.component_scores["impact_strength"].value < 4.0:
        warnings.append("keyword_match_but_weak_impact")
    if score_result.component_scores["domain_relevance"].value > 0 and score_result.component_scores["evidence_strength"].value < 3.5:
        warnings.append("relevant_but_low_evidence_strength")
    if evidence_unit.duplicate_of is not None:
        warnings.append("duplicate_or_near_duplicate")
    return _dedupe(warnings)


def _matched_domains(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
) -> list[str]:
    if score_result.component_scores["domain_relevance"].value <= 0:
        return []
    return evidence_unit.normalized_domains[:2]


def _matched_relevant_for(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
) -> list[str]:
    if score_result.component_scores["title_responsibility_relevance"].value <= 0:
        return []
    return [*evidence_unit.inferred_role_types, *evidence_unit.seniority_signals][:2]


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output
