"""Phase 3A selection helpers that compose resume entries from atomic evidence."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
import logging
from statistics import fmean

from .evidence_models import CanonicalEvidenceUnit
from .explainability import build_selection_reasoning
from .job_feature_adapter import JobRankingFeatures
from .models import ItemType, MasterProfile
from .ranking_explanation_models import RankingExplanation
from .resume_selection_models import (
    EvidenceScore,
    ExperienceAggregateScore,
    OmittedSelectionItem,
    ProjectSelectionReasoning,
    ProjectAggregateScore,
    ResumeSelectionDecision,
    SelectionAudit,
    SkillHighlightScore,
)
from .skill_selection import select_strategic_skills
from .scoring_engine import HybridScoreResult

_EXPERIENCE_SELECTION_FLOOR = 0.2
_EXPERIENCE_BACKFILL_FLOOR = 0.16
_PROJECT_SELECTION_FLOOR = 0.22
_PROJECT_UTILITY_BONUS = 0.08

STRATEGIC_NARRATIVE_WEIGHT = 0.15
RECENT_ROLE_BONUS = 0.1
HIGH_IMPACT_BONUS = 0.08
OWNERSHIP_LEADERSHIP_BONUS = 0.05
SECONDARY_EXPERIENCE_MIN_COVERAGE_GAIN = 0.1
SECONDARY_EXPERIENCE_MAX_STALE_RISK = 0.72

logger = logging.getLogger(__name__)


def _getattr_safe(obj: object, attr: str, default: float) -> float:
    try:
        return float(getattr(obj, attr, default))
    except (TypeError, ValueError):
        return default


def compose_resume_selection(
    *,
    evidence_scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    score_results_by_id: dict[str, HybridScoreResult],
    source_profile: MasterProfile,
    job_features: JobRankingFeatures,
    max_experiences: int,
    max_projects: int,
    max_highlighted_skills: int,
    max_highlighted_skills_per_category: int,
    max_bullet_share_per_experience: float,
    minimum_experience_spread: int,
    dominant_experience_score_gap: float,
    similar_experience_score_gap: float,
    max_bullets_per_item: int,
    min_bullets_if_available: int,
    min_strategic_fit_threshold: float = 0.3,
    stale_history_penalty_threshold: float = 0.5,
    strategic_narrative_weight: float = 0.15,
    recent_role_bonus: float = 0.1,
    high_impact_bonus: float = 0.08,
    ownership_leadership_bonus: float = 0.05,
) -> ResumeSelectionDecision:
    """Compose final resume-level selections from atomic evidence scores."""

    selected_experiences, omitted_experiences = _compose_entry_selection(
        evidence_scores=evidence_scores,
        evidence_units_by_id=evidence_units_by_id,
        score_results_by_id=score_results_by_id,
        source_profile=source_profile,
        job_features=job_features,
        item_type=ItemType.EXPERIENCE,
        limit=max_experiences,
        max_bullets_per_item=max_bullets_per_item,
        min_bullets_if_available=min_bullets_if_available,
    )
    selected_experiences, omitted_experiences = _rebalance_experience_selection(
        selected=selected_experiences,
        omitted=omitted_experiences,
        limit=max_experiences,
        max_bullet_share_per_experience=max_bullet_share_per_experience,
        minimum_experience_spread=minimum_experience_spread,
        dominant_experience_score_gap=dominant_experience_score_gap,
        similar_experience_score_gap=similar_experience_score_gap,
        min_bullets_if_available=min_bullets_if_available,
    )
    selected_projects, omitted_projects, project_selection_reasoning = (
        _compose_project_selection(
            evidence_scores=evidence_scores,
            evidence_units_by_id=evidence_units_by_id,
            score_results_by_id=score_results_by_id,
            source_profile=source_profile,
            job_features=job_features,
            limit=max_projects,
            max_bullets_per_item=max_bullets_per_item,
            min_bullets_if_available=min_bullets_if_available,
            selected_experiences=selected_experiences,
        )
    )

    selected_skills, omitted_skills = select_strategic_skills(
        source_profile=source_profile,
        job_features=job_features,
        evidence_scores=evidence_scores,
        selected_experiences=selected_experiences,
        selected_projects=selected_projects,
        max_highlighted_skills=max_highlighted_skills,
        max_per_category=max_highlighted_skills_per_category,
    )

    return ResumeSelectionDecision(
        selected_experiences=selected_experiences,
        selected_projects=selected_projects,
        omitted_projects=omitted_projects,
        project_selection_reasoning=project_selection_reasoning,
        selected_skills=selected_skills,
        omitted_items=[*omitted_experiences, *omitted_projects, *omitted_skills],
    )


def _compose_entry_selection(
    *,
    evidence_scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    score_results_by_id: dict[str, HybridScoreResult],
    source_profile: MasterProfile,
    job_features: JobRankingFeatures,
    item_type: ItemType,
    limit: int,
    max_bullets_per_item: int,
    min_bullets_if_available: int,
) -> tuple[
    list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    list[OmittedSelectionItem],
]:
    grouped_scores: OrderedDict[str, list[EvidenceScore]] = OrderedDict()
    for score in evidence_scores:
        if score.item_type != item_type:
            continue
        grouped_scores.setdefault(score.source_item_id, []).append(score)

    source_entries = (
        {entry.id: entry for entry in source_profile.experience}
        if item_type == ItemType.EXPERIENCE
        else {entry.id: entry for entry in source_profile.projects}
    )
    aggregate_scores = [
        _build_aggregate_score(
            source_item_id=source_item_id,
            scores=scores,
            evidence_units_by_id=evidence_units_by_id,
            score_results_by_id=score_results_by_id,
            title=(
                getattr(source_entries[source_item_id], "title", None)
                or getattr(source_entries[source_item_id], "name", None)
                or source_item_id
            ),
            item_type=item_type,
            all_bullet_ids=[
                bullet.id for bullet in source_entries[source_item_id].bullets
            ],
            max_bullets_per_item=max_bullets_per_item,
            min_bullets_if_available=min_bullets_if_available,
            job_features=job_features,
        )
        for source_item_id, scores in grouped_scores.items()
        if source_item_id in source_entries
    ]
    ranked_groups = sorted(
        aggregate_scores,
        key=lambda item: (
            item.strategic_fit_score,
            item.matched_must_have_count,
            item.direct_alignment_score,
            item.evidence_quality_score,
            item.matched_requirement_diversity,
            item.relevance_score,
            item.recency_score,
            item.strongest_evidence_score,
            -item.stale_risk_score,
            -item.weak_evidence_ratio,
            item.source_item_id,
        ),
        reverse=True,
    )
    selected = _select_best_aggregate_set(
        candidates=ranked_groups,
        item_type=item_type,
        limit=limit,
        job_features=job_features,
    )
    omitted = [
        OmittedSelectionItem(
            item_type=item_type,
            source_item_id=aggregate.source_item_id,
            evidence_score_ids=aggregate.evidence_score_ids,
            reason=_omission_reason(
                aggregate=aggregate,
                selected=selected,
                item_type=item_type,
            ),
            rationale=_omission_rationale(
                aggregate=aggregate,
                selected=selected,
                item_type=item_type,
            ),
            selection_audit=_build_omission_audit(
                aggregate=aggregate,
                selected=selected,
                item_type=item_type,
            ),
        )
        for aggregate in ranked_groups
        if aggregate.source_item_id not in {item.source_item_id for item in selected}
    ]
    return selected, omitted


def _select_best_aggregate_set(
    *,
    candidates: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    item_type: ItemType,
    limit: int,
    job_features: JobRankingFeatures,
) -> list[ExperienceAggregateScore] | list[ProjectAggregateScore]:
    if not candidates or limit <= 0:
        return []

    selected: list[ExperienceAggregateScore | ProjectAggregateScore] = []
    remaining = list(candidates)
    while remaining and len(selected) < limit:
        scored_candidates = sorted(
            (
                (
                    _selection_utility(
                        aggregate=aggregate,
                        selected=selected,
                        item_type=item_type,
                        job_features=job_features,
                    ),
                    aggregate,
                )
                for aggregate in remaining
            ),
            key=lambda item: (
                item[0],
                item[1].strategic_fit_score,
                item[1].direct_alignment_score,
                item[1].relevance_score,
                item[1].impact_score,
            ),
            reverse=True,
        )
        best_utility, best = scored_candidates[0]
        required_floor = (
            _EXPERIENCE_BACKFILL_FLOOR
            if item_type == ItemType.EXPERIENCE and len(selected) < 2
            else _EXPERIENCE_SELECTION_FLOOR
            if item_type == ItemType.EXPERIENCE
            else _PROJECT_SELECTION_FLOOR
        )
        coverage_gain = _coverage_gain_score(best, selected, job_features)

        should_force_for_coverage = coverage_gain >= 0.20 and (
            best.strategic_fit_score >= 0.30 or best.relevance_score >= 0.40
        )
        should_keep_secondary_experience = (
            item_type == ItemType.EXPERIENCE
            and len(selected) == 1
            and len(selected) < limit
            and coverage_gain >= SECONDARY_EXPERIENCE_MIN_COVERAGE_GAIN
            and _getattr_safe(best, "stale_risk_score", 1.0) <= SECONDARY_EXPERIENCE_MAX_STALE_RISK
            and (
                best.matched_must_have_count > 0
                or best.matched_requirement_diversity >= 2
                or best.direct_alignment_score >= 0.42
                or best.ownership_leadership_score >= 0.45
            )
        )

        should_keep = (
            best_utility >= required_floor
            or should_force_for_coverage
            or should_keep_secondary_experience
            or (
                item_type == ItemType.EXPERIENCE
                and len(selected) < limit
                and (
                    (
                        best.strategic_fit_score >= 0.3
                        and _getattr_safe(best, "stale_risk_score", 1.0) < 0.6
                    )
                    or (
                        best.relevance_score >= 0.4
                        and _getattr_safe(best, "stale_risk_score", 1.0) < 0.75
                    )
                )
                and best.relevance_score >= 0.2
                and _getattr_safe(best, "stale_risk_score", 1.0) < 0.7
            )
            or (
                item_type == ItemType.PROJECT
                and len(selected) < limit
                and (
                    (
                        best.matched_requirement_diversity > 0
                        and best.strategic_fit_score >= 0.2
                    )
                    or (
                        best.matched_must_have_count > 0
                        and best.strategic_fit_score >= 0.25
                    )
                    or (_getattr_safe(best, "project_utility_score", 0.0) >= 0.24)
                    or (best.impact_score >= 0.6 and best.relevance_score >= 0.3)
                    or (
                        _getattr_safe(best, "unique_evidence_score", 0.0) >= 0.22
                        and best.relevance_score >= 0.25
                    )
                )
                and best.relevance_score >= 0.2
            )
        )
        if not should_keep:
            break
        selected.append(
            _with_selection_utility_audit(
                aggregate=best,
                utility_score=best_utility,
                coverage_gain_score=coverage_gain,
                redundancy_penalty=_selection_redundancy_penalty(
                    best, selected[:-1] if selected else []
                ),
                item_type=item_type,
            )
        )
        remaining = [
            aggregate
            for aggregate in remaining
            if aggregate.source_item_id != best.source_item_id
        ]
    return selected


def _selection_utility(
    *,
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    selected: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    item_type: ItemType,
    job_features: JobRankingFeatures,
) -> float:
    coverage_gain = _coverage_gain_score(aggregate, selected, job_features)
    redundancy_penalty = _selection_redundancy_penalty(aggregate, selected)

    strategic_base = (
        aggregate.strategic_fit_score * 0.34
        + aggregate.direct_alignment_score * 0.18
        + aggregate.must_have_coverage_score * 0.12
        + aggregate.recency_score * 0.08
        + aggregate.impact_score * 0.08
        + aggregate.evidence_quality_score * 0.07
        + aggregate.ownership_leadership_score * 0.05
        + aggregate.strongest_evidence_score * 0.04
    )

    strategic_narrative_bonus = (
        aggregate.strategic_narrative_score * STRATEGIC_NARRATIVE_WEIGHT
    )
    recent_role_bonus = aggregate.recent_role_bonus_applied
    high_impact_bonus = aggregate.high_impact_bonus_applied
    ownership_bonus = aggregate.ownership_leadership_bonus_applied

    utility = (
        strategic_base
        + coverage_gain * 0.28
        + strategic_narrative_bonus
        + recent_role_bonus
        + high_impact_bonus
        + ownership_bonus
        - (aggregate.stale_risk_score * 0.22)
        - (aggregate.weak_evidence_ratio * 0.14)
        - (redundancy_penalty * 0.12)
    )
    return round(max(0.0, min(1.0, utility)), 4)


def _coverage_gain_score(
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    selected: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    job_features: JobRankingFeatures,
) -> float:
    current_signals = _combined_signal_buckets(selected, job_features)
    candidate_signals = _aggregate_signal_buckets(aggregate, job_features)

    new_required = candidate_signals["must_have"] - current_signals["must_have"]
    new_requirements = candidate_signals["requirements"] - current_signals["requirements"]
    new_preferred = candidate_signals["preferred"] - current_signals["preferred"]
    new_responsibility = candidate_signals["responsibility"] - current_signals["responsibility"]
    new_domain = candidate_signals["domain"] - current_signals["domain"]
    new_leadership = candidate_signals["leadership"] - current_signals["leadership"]

    required_possible = max(1, len(job_features.canonical_must_have_skills.values))
    requirement_possible = max(1, _expected_requirement_count(job_features))
    preferred_possible = max(1, len(job_features.canonical_nice_to_have_skills.values))
    responsibility_possible = max(1, len(job_features.responsibility_themes) or 1)
    domain_possible = max(1, len(job_features.domain_targets) or 1)
    score = (
        (len(new_required) / required_possible) * 0.4
        + (len(new_requirements) / requirement_possible) * 0.22
        + (len(new_preferred) / preferred_possible) * 0.1
        + (len(new_responsibility) / responsibility_possible) * 0.12
        + (len(new_domain) / domain_possible) * 0.08
        + min(1.0, float(len(new_leadership))) * 0.08
    )
    return round(min(1.0, score), 4)


def _selection_redundancy_penalty(
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    selected: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
) -> float:
    if not selected:
        return 0.0
    candidate_signals = _aggregate_overlap_signals(aggregate)
    if not candidate_signals:
        return 0.0
    best_overlap = 0.0
    for item in selected:
        selected_signals = _aggregate_overlap_signals(item)
        if not selected_signals:
            continue
        overlap = len(candidate_signals & selected_signals) / len(
            candidate_signals | selected_signals
        )
        best_overlap = max(best_overlap, overlap)
    return round(best_overlap, 4)


def _with_selection_utility_audit(
    *,
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    utility_score: float,
    coverage_gain_score: float,
    redundancy_penalty: float,
    item_type: ItemType,
) -> ExperienceAggregateScore | ProjectAggregateScore:
    selected_relevance_floor = round(
        min(
            1.0,
            max(
                0.0,
                0.45
                + (aggregate.direct_alignment_score * 0.25)
                + (aggregate.must_have_coverage_score * 0.1)
                + (coverage_gain_score * 0.1)
                - (aggregate.stale_risk_score * 0.05),
            ),
        ),
        4,
    )
    calibrated_relevance = round(
        min(
            1.0,
            max(
                aggregate.relevance_score,
                utility_score,
                utility_score + (coverage_gain_score * 0.2),
                aggregate.strategic_fit_score,
                aggregate.direct_alignment_score,
                selected_relevance_floor,
            ),
        ),
        4,
    )
    explanation = aggregate.ranking_explanation.model_copy(
        update={
            "summary": (
                f"Selected {item_type.value} for strategic resume fit: "
                f"utility {utility_score:.2f}, strategic fit {aggregate.strategic_fit_score:.2f}, "
                f"coverage gain {coverage_gain_score:.2f}, stale risk {aggregate.stale_risk_score:.2f}."
            ),
            "explanation_fragments": [
                *aggregate.ranking_explanation.explanation_fragments,
                f"selection utility: {utility_score:.2f}",
                f"coverage gain: {coverage_gain_score:.2f}",
                f"redundancy penalty: {redundancy_penalty:.2f}",
                f"stale risk: {aggregate.stale_risk_score:.2f}",
                f"selected relevance floor: {selected_relevance_floor:.2f}",
                f"calibrated selected relevance: {calibrated_relevance:.2f}",
            ],
        }
    )
    audit = aggregate.selection_audit.model_copy(
        update={
            "score_factors": {
                **aggregate.selection_audit.score_factors,
                "selection_utility": utility_score,
                "coverage_gain_score": coverage_gain_score,
                "redundancy_penalty": redundancy_penalty,
                "selected_relevance_floor": selected_relevance_floor,
                "calibrated_selected_relevance": calibrated_relevance,
                "strategic_fit_score": aggregate.strategic_fit_score,
                "stale_risk_score": aggregate.stale_risk_score,
                "weak_evidence_ratio": aggregate.weak_evidence_ratio,
            },
            "evidence_signals": [
                *aggregate.selection_audit.evidence_signals,
                "set_optimized_selection",
            ],
            "selection_reason": _aggregate_selection_reason(
                item_type=item_type,
                metrics={
                    "strategic_fit_score": aggregate.strategic_fit_score,
                    "matched_must_have_count": aggregate.matched_must_have_count,
                    "matched_requirement_diversity": aggregate.matched_requirement_diversity,
                    "evidence_quality_score": aggregate.evidence_quality_score,
                    "recency_score": aggregate.recency_score,
                    "coverage_gain_score": coverage_gain_score,
                },
            ),
            "human_summary": explanation.summary,
        }
    )
    return aggregate.model_copy(
        update={
            "relevance_score": calibrated_relevance,
            "ranking_explanation": explanation,
            "selection_audit": audit,
        }
    )


def _compose_project_selection(
    *,
    evidence_scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    score_results_by_id: dict[str, HybridScoreResult],
    source_profile: MasterProfile,
    job_features: JobRankingFeatures,
    limit: int,
    max_bullets_per_item: int,
    min_bullets_if_available: int,
    selected_experiences: list[ExperienceAggregateScore],
) -> tuple[
    list[ProjectAggregateScore], list[OmittedSelectionItem], ProjectSelectionReasoning
]:
    grouped_scores: OrderedDict[str, list[EvidenceScore]] = OrderedDict()
    for score in evidence_scores:
        if score.item_type != ItemType.PROJECT:
            continue
        grouped_scores.setdefault(score.source_item_id, []).append(score)

    project_by_id = {entry.id: entry for entry in source_profile.projects}
    selected_experience_keywords = {
        keyword.casefold()
        for experience in selected_experiences
        for keyword in experience.ranking_explanation.matched_keywords
    }
    selected_experience_requirements = {
        requirement.casefold()
        for experience in selected_experiences
        for requirement in experience.ranking_explanation.matched_job_requirements
    }

    aggregates: list[ProjectAggregateScore] = []
    for source_item_id, scores in grouped_scores.items():
        project = project_by_id.get(source_item_id)
        if project is None:
            continue
        aggregates.append(
            _build_project_aggregate_score(
                source_item_id=source_item_id,
                scores=scores,
                evidence_units_by_id=evidence_units_by_id,
                score_results_by_id=score_results_by_id,
                title=project.name,
                all_bullet_ids=[bullet.id for bullet in project.bullets],
                max_bullets_per_item=max_bullets_per_item,
                min_bullets_if_available=min_bullets_if_available,
                job_features=job_features,
                selected_experience_keywords=selected_experience_keywords,
                selected_experience_requirements=selected_experience_requirements,
            )
        )

    ranked_projects = sorted(
        aggregates,
        key=lambda item: (
            item.project_utility_score,
            item.strategic_fit_score,
            item.unique_evidence_score,
            item.matched_must_have_count,
            item.matched_requirement_diversity,
            item.evidence_quality_score,
            item.impact_score,
            item.recency_score,
            item.relevance_score,
            -item.stale_risk_score,
            item.source_item_id,
        ),
        reverse=True,
    )

    portfolio_sensitive_role = _is_project_portfolio_sensitive(job_features)
    experience_gap_detected = _experience_gap_detected(
        selected_experiences, job_features
    )
    candidate_projects: list[ProjectAggregateScore] = []
    omitted: list[OmittedSelectionItem] = []

    for aggregate in ranked_projects:
        if (
            aggregate.matched_must_have_count == 0
            and aggregate.matched_requirement_diversity == 0
            and aggregate.strategic_fit_score < 0.3
        ):
            omitted.append(
                OmittedSelectionItem(
                    item_type=ItemType.PROJECT,
                    source_item_id=aggregate.source_item_id,
                    evidence_score_ids=aggregate.evidence_score_ids,
                    reason="low_relevance",
                    rationale="Project lacks enough direct role-fit to compete for resume space.",
                    selection_audit=_simple_omission_audit(
                        matched_requirements=aggregate.selection_audit.matched_requirements,
                        omission_reason="low_relevance",
                        selection_reason="project_omitted",
                        supporting_evidence_ids=aggregate.evidence_score_ids,
                        score_factors={"aggregate_score": aggregate.relevance_score},
                        human_summary="Project did not show enough target-role relevance.",
                    ),
                )
            )
            continue

        should_promote_for_gaps = (
            aggregate.matched_must_have_count > 0
            and _project_fills_must_have_gaps(
                aggregate, selected_experiences, job_features
            )
        )
        should_promote_for_strength = (
            aggregate.impact_score >= 0.7
            and aggregate.evidence_quality_score >= 0.6
            and aggregate.relevance_score >= 0.4
        )
        should_promote_for_portfolio = (
            portfolio_sensitive_role and aggregate.strategic_fit_score >= 0.35
        )

        if (
            aggregate.unique_evidence_score <= 0.0
            and not experience_gap_detected
            and not portfolio_sensitive_role
            and not should_promote_for_gaps
            and not should_promote_for_strength
            and aggregate.project_utility_score < 0.2
            and aggregate.matched_must_have_count == 0
            and aggregate.matched_requirement_diversity <= 1
        ):
            omitted.append(
                OmittedSelectionItem(
                    item_type=ItemType.PROJECT,
                    source_item_id=aggregate.source_item_id,
                    evidence_score_ids=aggregate.evidence_score_ids,
                    reason="weak_strategic_fit",
                    rationale="Experience already covers the relevant requirements more strongly.",
                    selection_audit=_simple_omission_audit(
                        matched_requirements=aggregate.selection_audit.matched_requirements,
                        omission_reason="weak_strategic_fit",
                        selection_reason="project_omitted",
                        supporting_evidence_ids=aggregate.evidence_score_ids,
                        score_factors={
                            "aggregate_score": aggregate.relevance_score,
                            "unique_evidence_score": aggregate.unique_evidence_score,
                        },
                        human_summary="Project did not add enough incremental strategic value.",
                    ),
                )
            )
            continue
        if (
            aggregate.redundancy_score >= 0.72
            and aggregate.unique_evidence_score < 0.18
            and not experience_gap_detected
            and not should_promote_for_gaps
            and not should_promote_for_strength
            and not should_promote_for_portfolio
        ):
            omitted.append(
                OmittedSelectionItem(
                    item_type=ItemType.PROJECT,
                    source_item_id=aggregate.source_item_id,
                    evidence_score_ids=aggregate.evidence_score_ids,
                    reason="redundant_with_stronger_selected_content",
                    rationale="Project repeated already-selected experience evidence without adding enough net JD coverage.",
                    selection_audit=_simple_omission_audit(
                        matched_requirements=aggregate.selection_audit.matched_requirements,
                        omission_reason="redundant_with_stronger_selected_content",
                        selection_reason="project_omitted",
                        supporting_evidence_ids=aggregate.evidence_score_ids,
                        score_factors={
                            "aggregate_score": aggregate.relevance_score,
                            "redundancy_score": aggregate.redundancy_score,
                            "unique_evidence_score": aggregate.unique_evidence_score,
                        },
                        human_summary="Project was redundant with stronger selected experience coverage.",
                    ),
                )
            )
            continue
        candidate_projects.append(aggregate)

    selected = _select_best_aggregate_set(
        candidates=candidate_projects,
        item_type=ItemType.PROJECT,
        limit=limit,
        job_features=job_features,
    )
    selected_ids = {item.source_item_id for item in selected}
    omitted.extend(
        OmittedSelectionItem(
            item_type=ItemType.PROJECT,
            source_item_id=aggregate.source_item_id,
            evidence_score_ids=aggregate.evidence_score_ids,
            reason=_omission_reason(
                aggregate=aggregate,
                selected=selected,
                item_type=ItemType.PROJECT,
            ),
            rationale=_omission_rationale(
                aggregate=aggregate,
                selected=selected,
                item_type=ItemType.PROJECT,
            ),
            selection_audit=_build_omission_audit(
                aggregate=aggregate,
                selected=selected,
                item_type=ItemType.PROJECT,
            ),
        )
        for aggregate in candidate_projects
        if aggregate.source_item_id not in selected_ids
    )

    visible, section_reasons = _should_show_projects_section(
        selected_projects=selected,
        selected_experiences=selected_experiences,
        job_features=job_features,
        portfolio_sensitive_role=portfolio_sensitive_role,
        experience_gap_detected=experience_gap_detected,
    )

    if not visible:
        omitted.extend(
            OmittedSelectionItem(
                item_type=ItemType.PROJECT,
                source_item_id=project.source_item_id,
                evidence_score_ids=project.evidence_score_ids,
                reason=(
                    "redundant_with_stronger_selected_content"
                    if _getattr_safe(project, "unique_evidence_score", 0.0) <= 0.0
                    and not experience_gap_detected
                    and not portfolio_sensitive_role
                    else "insufficient_page_budget_priority"
                ),
                rationale=(
                    "Projects overlapped more directly with stronger selected experience and did not improve the final narrative enough to earn resume space."
                    if _getattr_safe(project, "unique_evidence_score", 0.0) <= 0.0
                    and not experience_gap_detected
                    and not portfolio_sensitive_role
                    else "Projects do not add enough incremental evidence to justify a visible section."
                ),
                selection_audit=_simple_omission_audit(
                    matched_requirements=project.selection_audit.matched_requirements,
                    omission_reason=(
                        "redundant_with_stronger_selected_content"
                        if _getattr_safe(project, "unique_evidence_score", 0.0) <= 0.0
                        and not experience_gap_detected
                        and not portfolio_sensitive_role
                        else "insufficient_page_budget_priority"
                    ),
                    selection_reason="project_omitted",
                    supporting_evidence_ids=project.evidence_score_ids,
                    score_factors=project.selection_audit.score_factors,
                    human_summary=(
                        "Project repeated stronger experience evidence and did not improve the final resume narrative enough to justify a visible section."
                        if _getattr_safe(project, "unique_evidence_score", 0.0) <= 0.0
                        and not experience_gap_detected
                        and not portfolio_sensitive_role
                        else "Project section was not justified for this target role."
                    ),
                ),
            )
            for project in selected
        )
        selected = []
    else:
        kept = selected[:limit]
        omitted.extend(
            OmittedSelectionItem(
                item_type=ItemType.PROJECT,
                source_item_id=project.source_item_id,
                evidence_score_ids=project.evidence_score_ids,
                reason="insufficient_page_budget_priority",
                rationale="Other retained projects added stronger unique support for the role.",
                selection_audit=_simple_omission_audit(
                    matched_requirements=project.selection_audit.matched_requirements,
                    omission_reason="insufficient_page_budget_priority",
                    selection_reason="project_omitted",
                    supporting_evidence_ids=project.evidence_score_ids,
                    score_factors=project.selection_audit.score_factors,
                    human_summary="Other projects received higher resume-space priority.",
                ),
            )
            for project in selected[limit:]
        )
        selected = kept

    reasoning = ProjectSelectionReasoning(
        show_projects_section=visible,
        reasons=section_reasons,
        portfolio_sensitive_role=portfolio_sensitive_role,
        experience_gap_detected=experience_gap_detected,
        selected_project_ids=[item.source_item_id for item in selected],
        omitted_project_ids=[item.source_item_id for item in omitted],
    )
    return selected, omitted, reasoning


def _rebalance_experience_selection(
    *,
    selected: list[ExperienceAggregateScore],
    omitted: list[OmittedSelectionItem],
    limit: int,
    max_bullet_share_per_experience: float,
    minimum_experience_spread: int,
    dominant_experience_score_gap: float,
    similar_experience_score_gap: float,
    min_bullets_if_available: int,
) -> tuple[list[ExperienceAggregateScore], list[OmittedSelectionItem]]:
    if not selected:
        return selected, omitted

    selected = list(selected)
    omitted = list(omitted)

    if _allow_experience_concentration(selected, dominant_experience_score_gap):
        return _trim_supporting_experience_bullets(selected), omitted

    selected = _trim_experience_bullet_concentration(
        selected=selected,
        max_bullet_share_per_experience=max_bullet_share_per_experience,
        min_bullets_if_available=min_bullets_if_available,
    )
    return _trim_supporting_experience_bullets(selected), omitted


def _allow_experience_concentration(
    selected: list[ExperienceAggregateScore],
    dominant_experience_score_gap: float,
) -> bool:
    if len(selected) <= 1:
        return True
    return (
        selected[0].relevance_score - selected[1].relevance_score
    ) >= dominant_experience_score_gap


def _trim_experience_bullet_concentration(
    *,
    selected: list[ExperienceAggregateScore],
    max_bullet_share_per_experience: float,
    min_bullets_if_available: int,
) -> list[ExperienceAggregateScore]:
    if len(selected) <= 1:
        return selected

    updated = [item.model_copy(deep=True) for item in selected]
    while True:
        total_bullets = sum(len(item.selected_bullet_ids) for item in updated)
        if total_bullets <= 0:
            return updated
        dominant = max(updated, key=lambda item: len(item.selected_bullet_ids))
        dominant_share = len(dominant.selected_bullet_ids) / total_bullets
        if dominant_share <= max_bullet_share_per_experience:
            return updated
        if len(dominant.selected_bullet_ids) <= max(1, min_bullets_if_available):
            return updated
        trimmed_bullet = dominant.selected_bullet_ids[-1]
        dominant.selected_bullet_ids = dominant.selected_bullet_ids[:-1]
        dominant.omitted_bullet_ids = [*dominant.omitted_bullet_ids, trimmed_bullet]
        dominant.ranking_explanation = dominant.ranking_explanation.model_copy(
            update={
                "explanation_fragments": [
                    *dominant.ranking_explanation.explanation_fragments,
                    "bullet concentration reduced to preserve experience diversity",
                ]
            }
        )


def _trim_supporting_experience_bullets(
    selected: list[ExperienceAggregateScore],
) -> list[ExperienceAggregateScore]:
    if len(selected) <= 1:
        return selected

    updated = [item.model_copy(deep=True) for item in selected]
    lead_utility = updated[0].selection_audit.score_factors.get(
        "selection_utility", 0.0
    )
    for item in updated[1:]:
        item_utility = item.selection_audit.score_factors.get("selection_utility", 0.0)
        utility_gap = lead_utility - item_utility
        max_support_bullets = (
            2
            if item.impact_score >= 0.4 and item.matched_requirement_diversity >= 2
            else 1
            if utility_gap >= 0.3
            else 2
        )
        if len(item.selected_bullet_ids) <= max_support_bullets:
            continue
        retained = item.selected_bullet_ids[:max_support_bullets]
        trimmed = item.selected_bullet_ids[max_support_bullets:]
        item.selected_bullet_ids = retained
        item.omitted_bullet_ids = [*item.omitted_bullet_ids, *trimmed]
        item.ranking_explanation = item.ranking_explanation.model_copy(
            update={
                "explanation_fragments": [
                    *item.ranking_explanation.explanation_fragments,
                    "supporting experience bullets trimmed to keep the final resume set focused",
                ]
            }
        )
    return updated


def _build_aggregate_score(
    *,
    source_item_id: str,
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    score_results_by_id: dict[str, HybridScoreResult],
    title: str,
    item_type: ItemType,
    all_bullet_ids: list[str],
    max_bullets_per_item: int,
    min_bullets_if_available: int,
    job_features: JobRankingFeatures,
) -> ExperienceAggregateScore | ProjectAggregateScore:
    sorted_scores = sorted(
        scores,
        key=lambda item: (
            item.relevance_score,
            _impact_signal_score(
                evidence_units_by_id[item.id],
                score_results_by_id[item.id],
            ),
            _evidence_quality_score(
                evidence_units_by_id[item.id],
                score_results_by_id[item.id],
            ),
            len(item.ranking_explanation.matched_keywords),
            item.id,
        ),
        reverse=True,
    )

    # Calculate strategic narrative fit directly
    if not scores:
        strategic_narrative_score = 0.0
    else:
        # Count unique strategic signals
        strategic_signals = {
            signal.casefold()
            for score in scores
            for signal in score.ranking_explanation.matched_keywords
        }

        # Count unique requirements covered
        requirements_covered = {
            req.casefold()
            for score in scores
            for req in score.ranking_explanation.matched_job_requirements
        }

        # Calculate alignment with job family and role type
        role_family_alignment = 0.0
        if job_features.role_family:
            role_signals = {
                signal.casefold()
                for score in scores
                for signal in score.ranking_explanation.matched_keywords
            }
            engineering_signals = {
                "backend",
                "frontend",
                "fullstack",
                "devops",
                "cloud",
                "sre",
                "platform",
            }
            data_signals = {"data", "ml", "ai", "analytics", "bi"}
            design_signals = {"design", "ui", "ux", "frontend"}
            if job_features.role_family == "engineering":
                if role_signals.intersection(engineering_signals):
                    role_family_alignment = 1.0
                elif role_signals.intersection(data_signals):
                    role_family_alignment = 0.5
            elif job_features.role_family == "data":
                if data_signals.intersection(role_signals):
                    role_family_alignment = 1.0
            elif job_features.role_family == "design":
                if design_signals.intersection(role_signals):
                    role_family_alignment = 1.0

        # Recency-weighted impact
        recency_weighted_impact = 0.0
        if scores:
            total_score = 0.0
            max_possible = 0.0
            today = date.today()
            for score in scores:
                evidence = evidence_units_by_id.get(score.id)
                if evidence and evidence.recency and evidence.recency.end_date:
                    # Parse end date
                    end_date_str = evidence.recency.end_date
                    parts = end_date_str.split("-")
                    try:
                        year = int(parts[0])
                        month = int(parts[1]) if len(parts) >= 2 else 1
                        day = int(parts[2]) if len(parts) >= 3 else 1
                        end_date = date(year, month, day)
                    except (ValueError, IndexError):
                        continue
                    months_ago = (today.year - year) * 12 + (today.month - month)
                    if months_ago < 0:
                        continue
                    # Normalize recency to 0-1 scale
                    if months_ago <= 6:
                        weight = 1.0
                    elif months_ago <= 18:
                        weight = 0.75
                    elif months_ago <= 36:
                        weight = 0.5
                    elif months_ago <= 48:
                        weight = 0.25
                    else:
                        weight = 0.1
                    impact = float(evidence.impact_score or 0)
                    total_score += weight * impact
                    max_possible += weight
            recency_weighted_impact = (
                total_score / max_possible if max_possible > 0 else 0.0
            )

        signal_coverage = len(strategic_signals) / max(
            1, len(job_features.canonical_all_skills)
        )
        requirement_coverage = len(requirements_covered) / max(
            1, _expected_requirement_count(job_features)
        )

        strategic_narrative_score = (
            role_family_alignment * 0.4
            + recency_weighted_impact * 0.3
            + signal_coverage * 0.2
            + requirement_coverage * 0.1
        )


def _build_aggregate_score(
    *,
    source_item_id: str,
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    score_results_by_id: dict[str, HybridScoreResult],
    title: str,
    item_type: ItemType,
    all_bullet_ids: list[str],
    max_bullets_per_item: int,
    min_bullets_if_available: int,
    job_features: JobRankingFeatures,
) -> ExperienceAggregateScore | ProjectAggregateScore:
    sorted_scores = sorted(
        scores,
        key=lambda item: (
            item.relevance_score,
            _impact_signal_score(
                evidence_units_by_id[item.id],
                score_results_by_id[item.id],
            ),
            _evidence_quality_score(
                evidence_units_by_id[item.id],
                score_results_by_id[item.id],
            ),
            len(item.ranking_explanation.matched_keywords),
            item.id,
        ),
        reverse=True,
    )
    selected_bullet_ids = _select_source_bullet_ids(
        scores=sorted_scores,
        all_bullet_ids=all_bullet_ids,
        max_bullets_per_item=max_bullets_per_item,
        min_bullets_if_available=min_bullets_if_available,
    )

    aggregate_metrics = _aggregate_metrics(
        scores=sorted_scores,
        evidence_units_by_id=evidence_units_by_id,
        score_results_by_id=score_results_by_id,
        job_features=job_features,
    )

    # Calculate strategic narrative fit using available metrics and signals
    strategic_narrative_score = 0.0
    if scores:
        # Count unique strategic signals from the scores
        strategic_signals = {
            signal.casefold()
            for score in scores
            for signal in score.ranking_explanation.matched_keywords
        }
        # Count unique requirements covered
        requirements_covered = {
            req.casefold()
            for score in scores
            for req in score.ranking_explanation.matched_job_requirements
        }

        # Role family alignment from score results
        role_family_alignment = 0.0
        if job_features.role_family:
            role_signals = {
                signal.casefold()
                for score in scores
                for signal in score.ranking_explanation.matched_keywords
            }
            engineering_signals = {
                "backend",
                "frontend",
                "fullstack",
                "devops",
                "cloud",
                "sre",
                "platform",
            }
            data_signals = {"data", "ml", "ai", "analytics", "bi"}
            design_signals = {"design", "ui", "ux", "frontend"}
            if job_features.role_family == "engineering":
                if role_signals.intersection(engineering_signals):
                    role_family_alignment = 1.0
                elif role_signals.intersection(data_signals):
                    role_family_alignment = 0.5
            elif job_features.role_family == "data":
                if data_signals.intersection(role_signals):
                    role_family_alignment = 1.0
            elif job_features.role_family == "design":
                if design_signals.intersection(role_signals):
                    role_family_alignment = 1.0

        # Use recency and impact scores from aggregate_metrics
        recency_score = float(aggregate_metrics.get("recency_score", 0.0))
        impact_score = float(aggregate_metrics.get("impact_score", 0.0))
        recency_weighted_impact = recency_score * impact_score

        signal_coverage = len(strategic_signals) / max(
            1, len(job_features.canonical_all_skills)
        )
        requirement_coverage = len(requirements_covered) / max(
            1, _expected_requirement_count(job_features)
        )

        strategic_narrative_score = (
            role_family_alignment * 0.4
            + recency_weighted_impact * 0.3
            + signal_coverage * 0.2
            + requirement_coverage * 0.1
        )

    # Enhance metrics with strategic dimensions
    recency = float(aggregate_metrics.get("recency_score", 0.0))
    strategic_fit = float(aggregate_metrics.get("strategic_fit_score", 0.0))
    recent_role_bonus_val = 0.0
    if recency >= 0.7 and strategic_fit >= 0.6:
        recent_role_bonus_val = min(1.0, (recency - 0.5) * 2) * RECENT_ROLE_BONUS

    # High impact bonus: count evidence with strong impact signals
    high_impact_bonus_val = 0.0
    if scores:
        strong_impact_count = 0
        for score in scores:
            # Use the impact component score from the hybrid score result
            score_result = score_results_by_id[score.id]
            impact_component = score_result.component_scores.get("impact_strength")
            if impact_component and float(impact_component.value) >= 0.7:
                strong_impact_count += 1
        impact_ratio = strong_impact_count / max(1, len(scores))
        high_impact_bonus_val = round(impact_ratio * 0.15, 4)

    # Ownership/leadership bonus
    ownership_leadership_bonus_val = 0.0
    if scores:
        ownership_signals = {
            signal.casefold()
            for score in scores
            for signal in score.ranking_explanation.matched_keywords
            if any(
                keyword in signal
                for keyword in ["lead", "own", "architect", "drive", "spearhead"]
            )
        }
        leadership_signals = {
            signal.casefold()
            for score in scores
            for signal in score.ranking_explanation.matched_keywords
            if any(
                keyword in signal for keyword in ["mentor", "guide", "coach", "lead"]
            )
        }
        ownership_score = min(1.0, len(ownership_signals) / 3)
        leadership_score = min(1.0, len(leadership_signals) / 2)
        ownership_leadership_bonus_val = round(
            (ownership_score * 0.08 + leadership_score * 0.07), 4
        )

    aggregate_metrics.update(
        {
            "strategic_narrative_score": round(min(1.0, strategic_narrative_score), 4),
            "recent_role_bonus_applied": round(recent_role_bonus_val, 4),
            "high_impact_bonus_applied": high_impact_bonus_val,
            "ownership_leadership_bonus_applied": ownership_leadership_bonus_val,
        }
    )

    omitted_bullet_ids = [
        bullet_id
        for bullet_id in all_bullet_ids
        if bullet_id not in set(selected_bullet_ids)
    ]

    lead_score = sorted_scores[0]
    lead_evidence = evidence_units_by_id[lead_score.id]
    lead_result = score_results_by_id[lead_score.id]
    explanation = build_selection_reasoning(
        evidence_unit=lead_evidence,
        score_result=lead_result,
        included=True,
        rank=None,
        competing_item_ids=None,
    ).model_copy(
        update={
            "summary": _aggregate_summary(
                item_type=item_type, metrics=aggregate_metrics
            ),
            "matched_keywords": aggregate_metrics["matched_keywords"][:5],
            "matched_required_skills": aggregate_metrics["matched_required"][:5],
            "matched_preferred_skills": aggregate_metrics["matched_preferred"][::5],
            "matched_job_requirements": aggregate_metrics["matched_requirements"][:6],
            "explanation_fragments": [
                f"{len(sorted_scores)} atomic evidence units supported this selection",
                f"must-have coverage: {aggregate_metrics['matched_must_have_count']}",
                f"preferred coverage: {aggregate_metrics['matched_preferred_count']}",
                f"requirement diversity: {aggregate_metrics['matched_requirement_diversity']}",
                f"evidence quality: {aggregate_metrics['evidence_quality_score']:.2f}",
                f"recency: {aggregate_metrics['recency_score']:.2f}",
                f"strategic narrative fit: {aggregate_metrics['strategic_narrative_score']:.2f}",
                f"{len(selected_bullet_ids)} bullets selected for final resume",
            ],
        }
    )

    payload = dict(
        source_item_id=source_item_id,
        title=title,
        relevance_score=aggregate_metrics["aggregate_score"],
        strongest_evidence_score=aggregate_metrics["strongest_evidence_score"],
        average_relevant_evidence_score=aggregate_metrics[
            "average_relevant_evidence_score"
        ],
        matched_must_have_count=aggregate_metrics["matched_must_have_count"],
        matched_preferred_count=aggregate_metrics["matched_preferred_count"],
        matched_requirement_diversity=aggregate_metrics[
            "matched_requirement_diversity"
        ],
        recency_score=aggregate_metrics["recency_score"],
        evidence_quality_score=aggregate_metrics["evidence_quality_score"],
        ownership_leadership_score=aggregate_metrics["ownership_leadership_score"],
        impact_score=aggregate_metrics["impact_score"],
        strategic_fit_score=aggregate_metrics["strategic_fit_score"],
        direct_alignment_score=aggregate_metrics["direct_alignment_score"],
        role_fit_score=aggregate_metrics["role_fit_score"],
        seniority_fit_score=aggregate_metrics["seniority_fit_score"],
        domain_fit_score=aggregate_metrics["domain_fit_score"],
        responsibility_match_score=aggregate_metrics["responsibility_match_score"],
        must_have_coverage_score=aggregate_metrics["must_have_coverage_score"],
        preferred_coverage_score=aggregate_metrics["preferred_coverage_score"],
        stale_risk_score=aggregate_metrics["stale_risk_score"],
        weak_evidence_ratio=aggregate_metrics["weak_evidence_ratio"],
        strategic_narrative_score=aggregate_metrics["strategic_narrative_score"],
        recent_role_bonus_applied=aggregate_metrics["recent_role_bonus_applied"],
        high_impact_bonus_applied=aggregate_metrics["high_impact_bonus_applied"],
        ownership_leadership_bonus_applied=aggregate_metrics[
            "ownership_leadership_bonus_applied"
        ],
        evidence_score_ids=[score.id for score in sorted_scores],
        selected_bullet_ids=selected_bullet_ids,
        omitted_bullet_ids=omitted_bullet_ids,
        ranking_explanation=explanation,
        selection_audit=_build_selection_audit(
            matched_requirements=aggregate_metrics["matched_requirements"],
            score_factors={
                "aggregate_score": aggregate_metrics["aggregate_score"],
                "strongest_evidence_score": aggregate_metrics[
                    "strongest_evidence_score"
                ],
                "average_relevant_evidence_score": aggregate_metrics[
                    "average_relevant_evidence_score"
                ],
                "recency_score": aggregate_metrics["recency_score"],
                "evidence_quality_score": aggregate_metrics["evidence_quality_score"],
                "ownership_leadership_score": aggregate_metrics[
                    "ownership_leadership_score"
                ],
                "impact_score": aggregate_metrics["impact_score"],
                "strategic_fit_score": aggregate_metrics["strategic_fit_score"],
                "direct_alignment_score": aggregate_metrics["direct_alignment_score"],
                "role_fit_score": aggregate_metrics["role_fit_score"],
                "seniority_fit_score": aggregate_metrics["seniority_fit_score"],
                "domain_fit_score": aggregate_metrics["domain_fit_score"],
                "responsibility_match_score": aggregate_metrics[
                    "responsibility_match_score"
                ],
                "must_have_coverage": aggregate_metrics["must_have_coverage_score"],
                "preferred_coverage": aggregate_metrics["preferred_coverage_score"],
                "requirement_diversity": _coverage_score(
                    aggregate_metrics["matched_requirement_diversity"],
                    _expected_requirement_count(job_features),
                ),
                "stale_risk_score": aggregate_metrics["stale_risk_score"],
                "weak_evidence_ratio": aggregate_metrics["weak_evidence_ratio"],
                "strategic_narrative_score": aggregate_metrics[
                    "strategic_narrative_score"
                ],
                "recent_role_bonus": aggregate_metrics["recent_role_bonus_applied"],
                "high_impact_bonus": aggregate_metrics["high_impact_bonus_applied"],
                "ownership_leadership_bonus": aggregate_metrics[
                    "ownership_leadership_bonus_applied"
                ],
            },
            evidence_signals=_selection_signals(
                item_type=item_type, metrics=aggregate_metrics
            ),
            selection_reason=_aggregate_selection_reason(
                item_type=item_type, metrics=aggregate_metrics
            ),
            supporting_evidence_ids=[score.id for score in sorted_scores],
            human_summary=explanation.summary,
        ),
    )
    if item_type == ItemType.EXPERIENCE:
        return ExperienceAggregateScore(**payload)
    return ProjectAggregateScore(**payload)


def _build_project_aggregate_score(
    *,
    source_item_id: str,
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    score_results_by_id: dict[str, HybridScoreResult],
    title: str,
    all_bullet_ids: list[str],
    max_bullets_per_item: int,
    min_bullets_if_available: int,
    job_features: JobRankingFeatures,
    selected_experience_keywords: set[str],
    selected_experience_requirements: set[str],
) -> ProjectAggregateScore:
    base = _build_aggregate_score(
        source_item_id=source_item_id,
        scores=scores,
        evidence_units_by_id=evidence_units_by_id,
        score_results_by_id=score_results_by_id,
        title=title,
        item_type=ItemType.PROJECT,
        all_bullet_ids=all_bullet_ids,
        max_bullets_per_item=max_bullets_per_item,
        min_bullets_if_available=min_bullets_if_available,
        job_features=job_features,
    )

    # Calculate project-specific strategic utility with better gap-filling emphasis
    project_utility_score = round(
        min(
            1.0,
            (
                base.strategic_fit_score * 0.45
                + base.strategic_narrative_score * 0.12
                + base.impact_score * 0.15
                + base.recency_score * 0.08
                + base.evidence_quality_score * 0.08
                + base.recent_role_bonus_applied * 0.03
                + base.high_impact_bonus_applied * 0.03
                + base.ownership_leadership_bonus_applied * 0.03
                + base.must_have_coverage_score * 0.08
                - base.stale_risk_score * 0.05
            ),
        ),
        4,
    )

    # Calculate uniqueness metrics
    keyword_set = {
        keyword.casefold() for keyword in base.ranking_explanation.matched_keywords
    }
    requirement_set = {
        requirement.casefold()
        for requirement in base.ranking_explanation.matched_job_requirements
    }
    keyword_unique = keyword_set - selected_experience_keywords
    requirement_unique = requirement_set - selected_experience_requirements
    all_project_signals = len(keyword_set.union(requirement_set))
    unique_signal_count = len(keyword_unique.union(requirement_unique))
    unique_evidence_score = (
        0.0
        if all_project_signals == 0
        else round(min(1.0, unique_signal_count / all_project_signals), 4)
    )
    overlap_signal_count = len(
        keyword_set.intersection(selected_experience_keywords)
    ) + len(requirement_set.intersection(selected_experience_requirements))
    redundancy_denominator = max(1, len(keyword_set) + len(requirement_set))
    redundancy_score = round(min(1.0, overlap_signal_count / redundancy_denominator), 4)

    return base.model_copy(
        update={
            "unique_evidence_score": unique_evidence_score,
            "redundancy_score": redundancy_score,
            "project_utility_score": project_utility_score,
            "ranking_explanation": base.ranking_explanation.model_copy(
                update={
                    "summary": (
                        f"Selected project for strategic role proof: "
                        f"utility {project_utility_score:.2f}, "
                        f"unique evidence {unique_evidence_score:.2f}, "
                        f"redundancy {redundancy_score:.2f}."
                    ),
                    "explanation_fragments": [
                        *base.ranking_explanation.explanation_fragments,
                        f"unique evidence score: {unique_evidence_score:.2f}",
                        f"redundancy score: {redundancy_score:.2f}",
                    ],
                }
            ),
            "selection_audit": base.selection_audit.model_copy(
                update={
                    "score_factors": {
                        **base.selection_audit.score_factors,
                        "unique_evidence_score": unique_evidence_score,
                        "redundancy_score": redundancy_score,
                        "project_utility_score": project_utility_score,
                    },
                    "evidence_signals": [
                        *base.selection_audit.evidence_signals,
                        f"unique_evidence:{unique_evidence_score:.2f}",
                        f"redundancy:{redundancy_score:.2f}",
                    ],
                    "selection_reason": (
                        "project_adds_unique_role_critical_proof"
                        if unique_evidence_score > 0.15
                        else "project_selected_as_supporting_proof"
                    ),
                }
            ),
        }
    )
    keyword_set = {
        keyword.casefold() for keyword in base.ranking_explanation.matched_keywords
    }
    requirement_set = {
        requirement.casefold()
        for requirement in base.ranking_explanation.matched_job_requirements
    }
    keyword_unique = keyword_set - selected_experience_keywords
    requirement_unique = requirement_set - selected_experience_requirements
    all_project_signals = len(keyword_set.union(requirement_set))
    unique_signal_count = len(keyword_unique.union(requirement_unique))
    unique_evidence_score = (
        0.0
        if all_project_signals == 0
        else round(min(1.0, unique_signal_count / all_project_signals), 4)
    )
    overlap_signal_count = len(
        keyword_set.intersection(selected_experience_keywords)
    ) + len(requirement_set.intersection(selected_experience_requirements))
    redundancy_denominator = max(1, len(keyword_set) + len(requirement_set))
    redundancy_score = round(min(1.0, overlap_signal_count / redundancy_denominator), 4)

    return base.model_copy(
        update={
            "unique_evidence_score": unique_evidence_score,
            "redundancy_score": redundancy_score,
            "project_utility_score": round(
                min(
                    1.0,
                    (
                        base.strategic_fit_score * 0.6
                        + unique_evidence_score * 0.15
                        + base.impact_score * 0.12
                        + base.recency_score * 0.08
                        + base.evidence_quality_score * 0.08
                        - redundancy_score * 0.03
                    ),
                ),
                4,
            ),
            "ranking_explanation": base.ranking_explanation.model_copy(
                update={
                    "summary": (
                        f"Selected project for strategic role proof: "
                        f"utility {min(1.0, (base.strategic_fit_score * 0.6 + unique_evidence_score * 0.15 + base.impact_score * 0.12 + base.recency_score * 0.08 + base.evidence_quality_score * 0.08 - redundancy_score * 0.03)):.2f}, "
                        f"unique evidence {unique_evidence_score:.2f}, redundancy {redundancy_score:.2f}."
                    ),
                    "explanation_fragments": [
                        *base.ranking_explanation.explanation_fragments,
                        f"unique evidence score: {unique_evidence_score:.2f}",
                        f"redundancy score: {redundancy_score:.2f}",
                    ],
                }
            ),
            "selection_audit": base.selection_audit.model_copy(
                update={
                    "score_factors": {
                        **base.selection_audit.score_factors,
                        "unique_evidence_score": unique_evidence_score,
                        "redundancy_score": redundancy_score,
                        "project_utility_score": round(
                            min(
                                1.0,
                                (
                                    base.strategic_fit_score * 0.6
                                    + unique_evidence_score * 0.15
                                    + base.impact_score * 0.12
                                    + base.recency_score * 0.08
                                    + base.evidence_quality_score * 0.08
                                    - redundancy_score * 0.03
                                ),
                            ),
                            4,
                        ),
                    },
                    "evidence_signals": [
                        *base.selection_audit.evidence_signals,
                        f"unique_evidence:{unique_evidence_score:.2f}",
                        f"redundancy:{redundancy_score:.2f}",
                    ],
                    "selection_reason": (
                        "project_adds_unique_role_critical_proof"
                        if unique_evidence_score > 0
                        else "project_selected_as_supporting_proof"
                    ),
                }
            ),
        }
    )


def _select_source_bullet_ids(
    *,
    scores: list[EvidenceScore],
    all_bullet_ids: list[str],
    max_bullets_per_item: int,
    min_bullets_if_available: int,
) -> list[str]:
    scored_bullet_ids: list[str] = []
    for score in scores:
        if (
            score.source_bullet_id is None
            or score.source_bullet_id in scored_bullet_ids
        ):
            continue
        scored_bullet_ids.append(score.source_bullet_id)

    desired_count = min(
        max_bullets_per_item,
        max(min_bullets_if_available, len(all_bullet_ids)),
    )
    if scored_bullet_ids:
        return scored_bullet_ids[:desired_count]

    if not all_bullet_ids:
        return []

    return all_bullet_ids[:desired_count]


def _aggregate_score(scores: list[EvidenceScore]) -> float:
    lead = max(score.relevance_score for score in scores)
    average = fmean(score.relevance_score for score in scores)
    support_bonus = min(0.08, 0.02 * max(0, len(scores) - 1))
    return round(min(1.0, (lead * 0.6) + (average * 0.4) + support_bonus), 4)


def _aggregate_keyword_count(scores: list[EvidenceScore]) -> int:
    return len(
        {
            keyword.casefold()
            for score in scores
            for keyword in score.ranking_explanation.matched_keywords
        }
    )


def _aggregate_bullet_count(scores: list[EvidenceScore]) -> int:
    return len(
        {
            score.source_bullet_id
            for score in scores
            if score.source_bullet_id is not None
        }
    )


def _dedupe_strings(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _comparison_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _aggregate_metrics(
    *,
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    score_results_by_id: dict[str, HybridScoreResult],
    job_features: JobRankingFeatures,
) -> dict[str, object]:
    matched_required = _dedupe_strings(
        skill
        for score in scores
        for skill in score.ranking_explanation.matched_required_skills
    )
    matched_preferred = _dedupe_strings(
        skill
        for score in scores
        for skill in score.ranking_explanation.matched_preferred_skills
    )
    matched_keywords = _dedupe_strings(
        keyword
        for score in scores
        for keyword in score.ranking_explanation.matched_keywords
    )
    matched_requirements = _dedupe_strings(
        requirement
        for score in scores
        for requirement in (
            [*score.ranking_explanation.matched_job_requirements]
            or [
                *score.ranking_explanation.matched_required_skills,
                *score.ranking_explanation.matched_preferred_skills,
            ]
        )
    )
    strongest_evidence_score = max(score.relevance_score for score in scores)
    average_relevant_evidence_score = round(
        fmean(score.relevance_score for score in scores),
        4,
    )
    recency_score = round(
        _mean_component_score(scores, "recency"),
        4,
    )
    evidence_quality_score = round(
        fmean(
            _evidence_quality_score(
                evidence_units_by_id[score.id], score_results_by_id[score.id]
            )
            for score in scores
        ),
        4,
    )
    ownership_leadership_score = round(
        fmean(
            _ownership_leadership_score(evidence_units_by_id[score.id])
            for score in scores
        ),
        4,
    )
    impact_score = round(
        fmean(
            _impact_signal_score(
                evidence_units_by_id[score.id], score_results_by_id[score.id]
            )
            for score in scores
        ),
        4,
    )
    role_fit_score = round(_mean_component_score(scores, "role_family_relevance"), 4)
    seniority_fit_score = round(_mean_component_score(scores, "seniority_relevance"), 4)
    domain_fit_score = round(_mean_component_score(scores, "domain_relevance"), 4)
    responsibility_match_score = round(
        _mean_component_score(scores, "title_responsibility_relevance"),
        4,
    )
    must_have_coverage_score = round(
        _coverage_score(
            len(matched_required), len(job_features.canonical_must_have_skills.values)
        ),
        4,
    )
    preferred_coverage_score = round(
        _coverage_score(
            len(matched_preferred),
            len(job_features.canonical_nice_to_have_skills.values),
        ),
        4,
    )
    requirement_coverage_score = round(
        _coverage_score(
            len(matched_requirements), _expected_requirement_count(job_features)
        ),
        4,
    )
    must_have_coverage_score = round(
        max(must_have_coverage_score, requirement_coverage_score * 0.85),
        4,
    )
    direct_alignment_score = round(
        min(
            1.0,
            (
                must_have_coverage_score * 0.32
                + requirement_coverage_score * 0.18
                + role_fit_score * 0.16
                + domain_fit_score * 0.14
                + responsibility_match_score * 0.1
                + seniority_fit_score * 0.1
            ),
        ),
        4,
    )
    stale_risk_score = round(
        fmean(
            _stale_risk_score(
                evidence_units_by_id[score.id], score_results_by_id[score.id], score
            )
            for score in scores
        ),
        4,
    )
    weak_evidence_ratio = round(
        fmean(
            _weak_evidence_penalty(
                evidence_units_by_id[score.id], score_results_by_id[score.id]
            )
            for score in scores
        ),
        4,
    )
    support_bonus = min(0.08, 0.025 * max(0, len(scores) - 1))
    stale_penalty = stale_risk_score * 0.15
    recency_bonus = recency_score * 0.05 if recency_score >= 0.7 else 0.0
    strategic_fit_score = round(
        max(
            0.0,
            min(
                1.0,
                (
                    must_have_coverage_score * 0.2
                    + preferred_coverage_score * 0.04
                    + requirement_coverage_score * 0.16
                    + direct_alignment_score * 0.24
                    + recency_score * 0.08
                    + evidence_quality_score * 0.1
                    + impact_score * 0.1
                    + ownership_leadership_score * 0.05
                    + strongest_evidence_score * 0.03
                    + support_bonus
                    + recency_bonus
                    - stale_penalty
                    - weak_evidence_ratio * 0.05
                ),
            ),
        ),
        4,
    )
    strategic_fit_floor = round(
        max(
            0.0,
            min(
                1.0,
                (
                    direct_alignment_score * 0.45
                    + requirement_coverage_score * 0.2
                    + evidence_quality_score * 0.15
                    + impact_score * 0.1
                    + ownership_leadership_score * 0.05
                    + recency_score * 0.05
                    - stale_risk_score * 0.05
                    - weak_evidence_ratio * 0.05
                ),
            ),
        ),
        4,
    )
    strategic_fit_score = round(max(strategic_fit_score, strategic_fit_floor), 4)
    aggregate_score = round(
        max(
            0.0,
            min(
                1.0,
                (
                    strongest_evidence_score * 0.14
                    + average_relevant_evidence_score * 0.12
                    + must_have_coverage_score * 0.16
                    + preferred_coverage_score * 0.04
                    + requirement_coverage_score * 0.14
                    + recency_score * 0.06
                    + evidence_quality_score * 0.09
                    + ownership_leadership_score * 0.05
                    + impact_score * 0.09
                    + direct_alignment_score * 0.16
                    + strategic_fit_score * 0.19
                    - stale_risk_score * 0.08
                    - weak_evidence_ratio * 0.04
                ),
            ),
        ),
        4,
    )
    aggregate_score_floor = round(
        max(
            0.0,
            min(
                1.0,
                (
                    direct_alignment_score * 0.4
                    + strategic_fit_score * 0.25
                    + requirement_coverage_score * 0.15
                    + evidence_quality_score * 0.1
                    + impact_score * 0.06
                    + recency_score * 0.04
                    - stale_risk_score * 0.04
                    - weak_evidence_ratio * 0.03
                ),
            ),
        ),
        4,
    )
    aggregate_score = round(max(aggregate_score, aggregate_score_floor), 4)
    return {
        "aggregate_score": aggregate_score,
        "strongest_evidence_score": strongest_evidence_score,
        "average_relevant_evidence_score": average_relevant_evidence_score,
        "matched_must_have_count": len(matched_required),
        "matched_preferred_count": len(matched_preferred),
        "matched_requirement_diversity": len(matched_requirements),
        "recency_score": recency_score,
        "evidence_quality_score": evidence_quality_score,
        "ownership_leadership_score": ownership_leadership_score,
        "impact_score": impact_score,
        "strategic_fit_score": strategic_fit_score,
        "direct_alignment_score": direct_alignment_score,
        "role_fit_score": role_fit_score,
        "seniority_fit_score": seniority_fit_score,
        "domain_fit_score": domain_fit_score,
        "responsibility_match_score": responsibility_match_score,
        "must_have_coverage_score": must_have_coverage_score,
        "preferred_coverage_score": preferred_coverage_score,
        "requirement_coverage_score": requirement_coverage_score,
        "stale_risk_score": stale_risk_score,
        "weak_evidence_ratio": weak_evidence_ratio,
        "matched_required": matched_required,
        "matched_preferred": matched_preferred,
        "matched_keywords": matched_keywords,
        "matched_requirements": matched_requirements,
    }


def _mean_component_score(scores: list[EvidenceScore], component_name: str) -> float:
    values = [
        _normalize_component(score.component_scores.get(component_name).value)
        for score in scores
        if score.component_scores.get(component_name) is not None
    ]
    if not values:
        return 0.0
    return float(fmean(values))


def _normalize_component(value: float) -> float:
    return max(0.0, min(1.0, value / 10.0))


def _evidence_quality_score(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
) -> float:
    quality_candidates = [
        evidence_unit.quality.overall_quality_score,
        evidence_unit.quality.strategic_usefulness_score,
        evidence_unit.quality.clarity_score,
        evidence_unit.quality.specificity_score,
    ]
    quality_values = [value for value in quality_candidates if value is not None]
    component = _normalize_component(
        score_result.component_scores["evidence_strength"].value
    )
    if not quality_values:
        return component
    return round((float(fmean(quality_values)) * 0.65) + (component * 0.35), 4)


def _ownership_leadership_score(evidence_unit: CanonicalEvidenceUnit) -> float:
    enrichment_values = [
        evidence_unit.enrichment.ownership_score,
        evidence_unit.enrichment.leadership_score,
        evidence_unit.enrichment.mentoring_score,
        evidence_unit.enrichment.stakeholder_management_score,
    ]
    values = [value for value in enrichment_values if value is not None]
    signal_bonus = min(1.0, len(evidence_unit.signals.leadership_signals) / 3)
    if not values:
        return round(signal_bonus, 4)
    return round(min(1.0, (float(fmean(values)) * 0.8) + (signal_bonus * 0.2)), 4)


def _impact_signal_score(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
) -> float:
    enrichment_values = [
        evidence_unit.enrichment.business_outcome_score,
        evidence_unit.enrichment.quantified_impact_score,
        evidence_unit.enrichment.delivery_execution_score,
        evidence_unit.enrichment.optimization_score,
    ]
    values = [value for value in enrichment_values if value is not None]
    component = _normalize_component(
        score_result.component_scores["impact_strength"].value
    )
    if not values:
        return component
    return round((float(fmean(values)) * 0.7) + (component * 0.3), 4)


def _stale_risk_score(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
    score: EvidenceScore,
) -> float:
    recency = _normalize_component(score_result.component_scores["recency"].value)
    role_fit = _normalize_component(
        score_result.component_scores["role_family_relevance"].value
    )
    domain_fit = _normalize_component(
        score_result.component_scores["domain_relevance"].value
    )
    responsibility = _normalize_component(
        score_result.component_scores["title_responsibility_relevance"].value
    )
    seniority_fit = _normalize_component(
        score_result.component_scores.get(
            "seniority_relevance",
            score_result.component_scores.get(
                "role_seniority_relevance", type("obj", (object,), {"value": 5.0})()
            ),
        ).value
    )
    has_required_match = bool(
        score.ranking_explanation.matched_required_skills
        or score.ranking_explanation.matched_job_requirements
    )
    stale_factor = 1.0 - recency
    weak_alignment = 1.0 - max(role_fit, domain_fit, responsibility)

    mismatch_bonus = 0.0
    if "stale_irrelevant_history" in score_result.mismatch_signals:
        mismatch_bonus = 0.3
    elif "legacy_technology" in score_result.mismatch_signals:
        mismatch_bonus = 0.25
    elif "wrong_role_family" in score_result.mismatch_signals:
        mismatch_bonus = 0.25

    missing_requirement_bonus = 0.2 if not has_required_match else 0.0
    seniority_mismatch_penalty = 0.2 if seniority_fit < 0.35 else 0.0
    role_family_mismatch_penalty = 0.25 if role_fit < 0.25 else 0.0

    legacy_tech_penalty = _legacy_technology_penalty(
        score.ranking_explanation.matched_keywords,
        score.ranking_explanation.matched_required_skills,
    )

    return round(
        min(
            1.0,
            stale_factor * 0.4
            + weak_alignment * 0.22
            + mismatch_bonus
            + missing_requirement_bonus
            + seniority_mismatch_penalty
            + role_family_mismatch_penalty
            + legacy_tech_penalty,
        ),
        4,
    )


def _legacy_technology_penalty(
    keywords: list[str],
    required_skills: list[str],
) -> float:
    legacy_tech_keywords = {
        "jquery",
        "prototype",
        "mootools",
        "dojo",
        "extjs",
        "wordpress",
        "drupal",
        "joomla",
        "wix",
        "squarespace",
        "struts",
        "jsp",
        "ejb",
        "applet",
        "vb",
        "vb.net",
        "classic asp",
        "flash",
        "flex",
        "silverlight",
        "cobol",
        "fortran",
        "perl",
        "ruby 1.8",
    }
    all_text = {kw.casefold() for kw in keywords + required_skills}
    legacy_matches = all_text.intersection(legacy_tech_keywords)
    if len(legacy_matches) >= 2:
        return 0.2
    elif len(legacy_matches) == 1:
        return 0.1
    return 0.0


def _weak_evidence_penalty(
    evidence_unit: CanonicalEvidenceUnit,
    score_result: HybridScoreResult,
) -> float:
    quality = _evidence_quality_score(evidence_unit, score_result)
    warning_signals = {
        "low_information",
        "vague_evidence",
        "unsupported_skill_mention",
        "weak_strategic_alignment",
    }
    mismatch_count = sum(
        1 for signal in score_result.mismatch_signals if signal in warning_signals
    )
    mismatch_penalty = min(1.0, mismatch_count / 3)
    return round(
        min(
            1.0,
            (1.0 - quality) * 0.7 + mismatch_penalty * 0.3,
        ),
        4,
    )


def _coverage_score(matched_count: int, possible_count: int) -> float:
    if possible_count <= 0:
        return 0.0
    return min(1.0, matched_count / possible_count)


def _strategic_narrative_score(
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
    job_features: JobRankingFeatures,
) -> float:
    """Calculate how well this item contributes to a coherent resume narrative."""
    if not scores:
        return 0.0

    # Count unique strategic signals
    strategic_signals = {
        signal.casefold()
        for score in scores
        for signal in score.ranking_explanation.matched_keywords
    }

    # Count unique requirements covered
    requirements_covered = {
        req.casefold()
        for score in scores
        for req in score.ranking_explanation.matched_job_requirements
    }

    # Calculate alignment with job family and role type
    role_family_alignment = _role_family_alignment_score(scores, job_features)
    recency_weighted_impact = _recency_weighted_impact(scores, evidence_units_by_id)

    # Combine factors
    signal_coverage = len(strategic_signals) / max(
        1, len(job_features.canonical_all_skills)
    )
    requirement_coverage = len(requirements_covered) / max(
        1, _expected_requirement_count(job_features)
    )

    narrative_score = (
        role_family_alignment * 0.4
        + recency_weighted_impact * 0.3
        + signal_coverage * 0.2
        + requirement_coverage * 0.1
    )

    return round(min(1.0, narrative_score), 4)


def _role_family_alignment_score(
    scores: list[EvidenceScore],
    job_features: JobRankingFeatures,
) -> float:
    """Measure alignment with the target role family."""
    if not job_features.role_family:
        return 0.0

    role_signals = {
        signal.casefold()
        for score in scores
        for signal in score.ranking_explanation.matched_keywords
    }

    # Key role family signals
    engineering_signals = {
        "backend",
        "frontend",
        "fullstack",
        "devops",
        "cloud",
        "sre",
        "platform",
    }
    data_signals = {"data", "ml", "ai", "analytics", "bi"}
    design_signals = {"design", "ui", "ux", "frontend"}

    role_family_score = 0.0
    if job_features.role_family == "engineering":
        if role_signals.intersection(engineering_signals):
            role_family_score = 1.0
        elif data_signals.intersection(role_signals):
            role_family_score = 0.5
    elif job_features.role_family == "data":
        if data_signals.intersection(role_signals):
            role_family_score = 1.0
    elif job_features.role_family == "design":
        if design_signals.intersection(role_signals):
            role_family_score = 1.0

    return role_family_score


def _recency_weighted_impact(
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
) -> float:
    """Weight impact by recency to prioritize recent high-impact work."""
    if not scores:
        return 0.0

    total_score = 0.0
    max_possible = 0.0

    for score in scores:
        evidence = evidence_units_by_id.get(score.id)
        if not evidence:
            continue
        # Use recency score as weight (0.0 to 1.0)
        weight = float(evidence.recency_score or 0)
        impact = float(evidence.impact_score or 0)
        total_score += weight * impact
        max_possible += weight  # Max if all had perfect impact

    return total_score / max_possible if max_possible > 0 else 0.0


def _recent_role_bonus(
    aggregate_metrics: dict[str, object],
    job_features: JobRankingFeatures,
) -> float:
    """Bonus for recent experience that demonstrates role fit."""
    recency = float(aggregate_metrics.get("recency_score", 0.0))
    strategic_fit = float(aggregate_metrics.get("strategic_fit_score", 0.0))

    # Only apply bonus if recency is good and strategic fit is strong
    if recency >= 0.7 and strategic_fit >= 0.6:
        return min(1.0, (recency - 0.5) * 2) * recent_role_bonus
    return 0.0


def _high_impact_bonus(
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
) -> float:
    """Bonus for high-impact evidence."""
    if not scores:
        return 0.0

    strong_impact_count = 0
    for score in scores:
        evidence = evidence_units_by_id.get(score.id)
        if evidence and (evidence.impact_score or 0) >= 0.7:
            strong_impact_count += 1

    impact_ratio = strong_impact_count / max(1, len(scores))
    return round(impact_ratio * 0.15, 4)  # Max bonus 0.15


def _ownership_leadership_bonus(
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
) -> float:
    """Bonus for evidence demonstrating ownership or leadership."""
    if not scores:
        return 0.0

    ownership_signals = {
        signal.casefold()
        for score in scores
        for signal in score.ranking_explanation.matched_keywords
        if any(
            keyword in signal
            for keyword in ["lead", "own", "architect", "drive", "spearhead"]
        )
    }

    leadership_signals = {
        signal.casefold()
        for score in scores
        for signal in score.ranking_explanation.matched_keywords
        if any(keyword in signal for keyword in ["mentor", "guide", "coach", "lead"])
    }

    ownership_score = min(1.0, len(ownership_signals) / 3)  # Max 3 ownership signals
    leadership_score = min(1.0, len(leadership_signals) / 2)  # Max 2 leadership signals

    return round((ownership_score * 0.08 + leadership_score * 0.07), 4)


def _expected_requirement_count(job_features: JobRankingFeatures) -> int:
    return max(
        1,
        len(job_features.canonical_must_have_skills.values)
        + len(job_features.canonical_nice_to_have_skills.values),
    )


def _aggregate_summary(*, item_type: ItemType, metrics: dict[str, object]) -> str:
    return (
        f"Selected {item_type.value} for strategic job coverage: "
        f"{metrics['matched_must_have_count']} must-have matches, "
        f"strategic fit {metrics['strategic_fit_score']:.2f}, "
        f"quality {metrics['evidence_quality_score']:.2f}, "
        f"recency {metrics['recency_score']:.2f}, "
        f"stale risk {metrics['stale_risk_score']:.2f}."
    )
    requirement_coverage = len(requirements_covered) / max(
        1, _expected_requirement_count(job_features)
    )

    narrative_score = (
        role_family_alignment * 0.4
        + recency_weighted_impact * 0.3
        + signal_coverage * 0.2
        + requirement_coverage * 0.1
    )

    return round(min(1.0, narrative_score), 4)


def _role_family_alignment_score(
    scores: list[EvidenceScore],
    job_features: JobRankingFeatures,
) -> float:
    """Measure alignment with the target role family."""
    if not job_features.role_family:
        return 0.0

    role_signals = {
        signal.casefold()
        for score in scores
        for signal in score.ranking_explanation.matched_keywords
    }

    # Key role family signals
    engineering_signals = {
        "backend",
        "frontend",
        "fullstack",
        "devops",
        "cloud",
        "sre",
        "platform",
    }
    data_signals = {"data", "ml", "ai", "analytics", "bi"}
    design_signals = {"design", "ui", "ux", "frontend"}

    role_family_score = 0.0
    if job_features.role_family == "engineering":
        if role_signals.intersection(engineering_signals):
            role_family_score = 1.0
        elif data_signals.intersection(role_signals):
            role_family_score = 0.5
    elif job_features.role_family == "data":
        if data_signals.intersection(role_signals):
            role_family_score = 1.0
    elif job_features.role_family == "design":
        if design_signals.intersection(role_signals):
            role_family_score = 1.0

    return role_family_score


def _recency_weighted_impact(
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
) -> float:
    """Weight impact by recency to prioritize recent high-impact work."""
    if not scores:
        return 0.0

    total_score = 0.0
    max_possible = 0.0

    for score in scores:
        evidence = evidence_units_by_id.get(score.id)
        if not evidence:
            continue
        # Use recency score as weight (0.0 to 1.0)
        weight = float(evidence.recency_score or 0)
        impact = float(evidence.impact_score or 0)
        total_score += weight * impact
        max_possible += weight  # Max if all had perfect impact

    return total_score / max_possible if max_possible > 0 else 0.0


def _recent_role_bonus(
    aggregate_metrics: dict[str, object],
    job_features: JobRankingFeatures,
) -> float:
    """Bonus for recent experience that demonstrates role fit."""
    recency = float(aggregate_metrics.get("recency_score", 0.0))
    strategic_fit = float(aggregate_metrics.get("strategic_fit_score", 0.0))

    # Only apply bonus if recency is good and strategic fit is strong
    if recency >= 0.7 and strategic_fit >= 0.6:
        return min(1.0, (recency - 0.5) * 2) * recent_role_bonus
    return 0.0


def _high_impact_bonus(
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
) -> float:
    """Bonus for high-impact evidence."""
    if not scores:
        return 0.0

    strong_impact_count = 0
    for score in scores:
        evidence = evidence_units_by_id.get(score.id)
        if evidence and (evidence.impact_score or 0) >= 0.7:
            strong_impact_count += 1

    impact_ratio = strong_impact_count / max(1, len(scores))
    return round(impact_ratio * 0.15, 4)  # Max bonus 0.15


def _ownership_leadership_bonus(
    scores: list[EvidenceScore],
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit],
) -> float:
    """Bonus for evidence demonstrating ownership or leadership."""
    if not scores:
        return 0.0

    ownership_signals = {
        signal.casefold()
        for score in scores
        for signal in score.ranking_explanation.matched_keywords
        if any(
            keyword in signal
            for keyword in ["lead", "own", "architect", "drive", "spearhead"]
        )
    }

    leadership_signals = {
        signal.casefold()
        for score in scores
        for signal in score.ranking_explanation.matched_keywords
        if any(keyword in signal for keyword in ["mentor", "guide", "coach", "lead"])
    }

    ownership_score = min(1.0, len(ownership_signals) / 3)  # Max 3 ownership signals
    leadership_score = min(1.0, len(leadership_signals) / 2)  # Max 2 leadership signals

    return round((ownership_score * 0.08 + leadership_score * 0.07), 4)


def _selection_signals(*, item_type: ItemType, metrics: dict[str, object]) -> list[str]:
    signals = [
        f"{item_type.value}_must_have_matches:{metrics['matched_must_have_count']}",
        f"{item_type.value}_preferred_matches:{metrics['matched_preferred_count']}",
        f"{item_type.value}_requirement_diversity:{metrics['matched_requirement_diversity']}",
    ]
    if metrics["evidence_quality_score"] >= 0.6:
        signals.append("strong_evidence_quality")
    if metrics["recency_score"] >= 0.6:
        signals.append("recent_supported_evidence")
    if metrics["strategic_fit_score"] >= 0.6:
        signals.append("strong_strategic_fit")
    if metrics["stale_risk_score"] >= 0.55:
        signals.append("stale_risk_present")
    if metrics["impact_score"] >= 0.6:
        signals.append("strong_impact_signal")
    if metrics["ownership_leadership_score"] >= 0.5:
        signals.append("ownership_or_leadership_signal")
    return signals


def _aggregate_selection_reason(
    *, item_type: ItemType, metrics: dict[str, object]
) -> str:
    if metrics.get("coverage_gain_score", 0.0) >= 0.35:
        return f"{item_type.value}_selected_to_close_requirement_gaps"
    if metrics["strategic_fit_score"] >= 0.7:
        return f"{item_type.value}_selected_for_strong_strategic_fit"
    if (
        metrics["matched_must_have_count"] > 0
        and metrics["matched_requirement_diversity"] > 1
    ):
        return f"{item_type.value}_selected_for_broad_requirement_coverage"
    if metrics["evidence_quality_score"] >= 0.7:
        return f"{item_type.value}_selected_for_strong_evidence_quality"
    if metrics["recency_score"] >= 0.7:
        return f"{item_type.value}_selected_for_recent_relevant_evidence"
    return f"{item_type.value}_selected_for_overall_strategic_value"


def _build_selection_audit(
    *,
    matched_requirements: list[str],
    score_factors: dict[str, float],
    evidence_signals: list[str],
    selection_reason: str,
    supporting_evidence_ids: list[str],
    human_summary: str,
) -> SelectionAudit:
    return SelectionAudit(
        matched_requirements=matched_requirements,
        score_factors={
            key: round(float(value), 4) for key, value in score_factors.items()
        },
        evidence_signals=evidence_signals,
        selection_reason=selection_reason,
        supporting_evidence_ids=supporting_evidence_ids,
        human_summary=human_summary,
    )


def _build_omission_audit(
    *,
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    selected: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    item_type: ItemType,
) -> SelectionAudit:
    omission_reason = _omission_reason(
        aggregate=aggregate, selected=selected, item_type=item_type
    )
    return SelectionAudit(
        matched_requirements=list(aggregate.selection_audit.matched_requirements),
        score_factors=dict(aggregate.selection_audit.score_factors),
        evidence_signals=list(aggregate.selection_audit.evidence_signals),
        selection_reason=f"{item_type.value}_omitted",
        supporting_evidence_ids=list(aggregate.evidence_score_ids),
        omission_reason=omission_reason,
        human_summary=_omission_rationale(
            aggregate=aggregate, selected=selected, item_type=item_type
        ),
    )


def _simple_omission_audit(
    *,
    matched_requirements: list[str],
    omission_reason: str,
    selection_reason: str,
    supporting_evidence_ids: list[str],
    score_factors: dict[str, float],
    human_summary: str,
) -> SelectionAudit:
    return SelectionAudit(
        matched_requirements=matched_requirements,
        score_factors={
            key: round(float(value), 4) for key, value in score_factors.items()
        },
        evidence_signals=[],
        selection_reason=selection_reason,
        supporting_evidence_ids=supporting_evidence_ids,
        omission_reason=omission_reason,
        human_summary=human_summary,
    )


def _omission_reason(
    *,
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    selected: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    item_type: ItemType,
) -> str:
    if not selected:
        return "insufficient_page_budget_priority"
    cutoff = selected[-1]
    if aggregate.relevance_score < 0.35:
        return "low_relevance"
    if aggregate.strategic_fit_score < 0.32:
        return "weak_strategic_fit"
    if aggregate.evidence_quality_score < 0.45:
        return "weak_evidence_quality"
    if (
        aggregate.stale_risk_score >= 0.55
        and aggregate.relevance_score <= cutoff.relevance_score
    ):
        return "outdated_content"
    if aggregate.matched_must_have_count < cutoff.matched_must_have_count:
        return "weak_strategic_fit"
    if aggregate.strategic_fit_score < cutoff.strategic_fit_score:
        return "weak_strategic_fit"
    if aggregate.evidence_quality_score < cutoff.evidence_quality_score:
        return "weak_evidence_quality"
    if (
        aggregate.stale_risk_score > cutoff.stale_risk_score
        and aggregate.relevance_score <= cutoff.relevance_score
    ):
        return "outdated_content"
    if aggregate.matched_requirement_diversity < cutoff.matched_requirement_diversity:
        return "weak_strategic_fit"
    return "insufficient_page_budget_priority"


def _omission_rationale(
    *,
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    selected: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    item_type: ItemType,
) -> str:
    reason = _omission_reason(
        aggregate=aggregate, selected=selected, item_type=item_type
    )
    rationales = {
        "low_relevance": "Selected alternatives mapped more directly to target job requirements.",
        "weak_evidence_quality": "Evidence quality was weaker than competing selected content.",
        "outdated_content": "Older content lost priority against similarly relevant, more recent evidence.",
        "redundant_with_stronger_selected_content": "Overlapped with stronger selected content and added little incremental value.",
        "insufficient_page_budget_priority": "Competing content received higher resume-space priority.",
        "weak_strategic_fit": "Coverage breadth and role-fit were weaker than retained items.",
    }
    return rationales.get(
        reason,
        f"Omitted from the {item_type.value} selection after deterministic ranking.",
    )


def _should_show_projects_section(
    *,
    selected_projects: list[ProjectAggregateScore],
    selected_experiences: list[ExperienceAggregateScore],
    job_features: JobRankingFeatures,
    portfolio_sensitive_role: bool,
    experience_gap_detected: bool,
) -> tuple[bool, list[str]]:
    if not selected_projects:
        if (
            selected_experiences
            and not experience_gap_detected
            and not portfolio_sensitive_role
        ):
            return False, ["experience_already_covers_target_fit_without_projects"]
        return False, ["no_projects_cleared_selection_thresholds"]

    reasons: list[str] = []
    if any(
        _getattr_safe(p, "unique_evidence_score", 0.0) >= 0.25
        for p in selected_projects
    ):
        reasons.append("projects_add_unique_role_critical_proof")
    if _projects_add_recent_strategic_support(
        selected_projects=selected_projects,
        selected_experiences=selected_experiences,
    ):
        reasons.append("projects_add_recent_strategic_support")
    if _projects_outperform_weaker_supporting_experience(
        selected_projects=selected_projects,
        selected_experiences=selected_experiences,
    ):
        reasons.append("projects_outperform_weaker_supporting_experience")
    if _projects_close_supporting_requirement_gaps(
        selected_projects=selected_projects,
        selected_experiences=selected_experiences,
    ):
        reasons.append("projects_close_supporting_requirement_gaps")
    if any(
        _getattr_safe(p, "project_utility_score", 0.0) >= 0.35
        and _getattr_safe(p, "unique_evidence_score", 0.0) >= 0.1
        for p in selected_projects
    ):
        reasons.append("projects_add_strong_strategic_support")
    if experience_gap_detected:
        reasons.append("experience_section_alone_is_insufficient")
    if portfolio_sensitive_role:
        reasons.append("target_role_is_project_portfolio_sensitive")
    if any(p.matched_must_have_count >= 1 for p in selected_projects):
        reasons.append("projects_cover_critical_must_have_requirements")

    if reasons:
        return True, reasons

    experience_coverage = _experience_coverage_ratio(selected_experiences, job_features)
    project_coverage = _project_coverage_ratio(selected_projects, job_features)
    if project_coverage > experience_coverage and any(
        _getattr_safe(p, "project_utility_score", 0.0) >= 0.35
        for p in selected_projects
    ):
        return True, ["projects_cover_more_target_requirements_than_experience"]

    return False, ["experience_already_covers_target_fit_without_projects"]


def _projects_add_recent_strategic_support(
    *,
    selected_projects: list[ProjectAggregateScore],
    selected_experiences: list[ExperienceAggregateScore],
) -> bool:
    if not selected_projects or len(selected_experiences) < 2:
        return False

    supporting_experience = min(
        selected_experiences,
        key=lambda experience: (
            experience.recency_score,
            experience.strategic_fit_score,
            experience.relevance_score,
        ),
    )
    for project in selected_projects:
        if (
            project.matched_requirement_diversity >= 2
            and project.relevance_score >= 0.38
            and project.impact_score >= 0.3
            and project.recency_score >= supporting_experience.recency_score + 0.05
        ):
            return True
    return False


def _projects_outperform_weaker_supporting_experience(
    *,
    selected_projects: list[ProjectAggregateScore],
    selected_experiences: list[ExperienceAggregateScore],
) -> bool:
    if not selected_projects or len(selected_experiences) < 2:
        return False

    supporting_experience = min(
        selected_experiences,
        key=lambda experience: (
            experience.strategic_fit_score,
            experience.relevance_score,
            experience.evidence_quality_score,
        ),
    )
    for project in selected_projects:
        if (
            project.matched_requirement_diversity >= 2
            and project.strategic_fit_score >= supporting_experience.strategic_fit_score
            and project.relevance_score >= supporting_experience.relevance_score + 0.03
            and project.impact_score >= 0.3
        ):
            return True
    return False


def _projects_close_supporting_requirement_gaps(
    *,
    selected_projects: list[ProjectAggregateScore],
    selected_experiences: list[ExperienceAggregateScore],
) -> bool:
    if not selected_projects or len(selected_experiences) < 2:
        return False

    supporting_experience = min(
        selected_experiences,
        key=lambda experience: (
            experience.strategic_fit_score,
            experience.relevance_score,
            experience.matched_requirement_diversity,
        ),
    )
    supporting_requirements = {
        requirement.casefold()
        for requirement in supporting_experience.ranking_explanation.matched_job_requirements
    }
    for project in selected_projects:
        project_requirements = {
            requirement.casefold()
            for requirement in project.ranking_explanation.matched_job_requirements
        }
        if (
            len(project_requirements - supporting_requirements) >= 1
            and project.matched_requirement_diversity >= 2
            and project.relevance_score >= 0.35
        ):
            return True
    return False


def _is_project_portfolio_sensitive(job_features: JobRankingFeatures) -> bool:
    tokens = {
        value.casefold()
        for value in [
            *job_features.canonical_all_skills,
            *job_features.domain_targets,
            *(job_features.role_family and [job_features.role_family] or []),
            *(job_features.role_type and [job_features.role_type] or []),
        ]
    }
    portfolio_sensitive_tokens = {
        "frontend",
        "fullstack",
        "react",
        "next.js",
        "typescript",
        "mobile",
        "design",
        "portfolio",
        "ui",
        "ux",
        "product",
    }
    return bool(tokens.intersection(portfolio_sensitive_tokens))


def _experience_gap_detected(
    selected_experiences: list[ExperienceAggregateScore],
    job_features: JobRankingFeatures,
) -> bool:
    return _experience_coverage_ratio(selected_experiences, job_features) < 0.68


def _project_fills_must_have_gaps(
    project: ProjectAggregateScore,
    selected_experiences: list[ExperienceAggregateScore],
    job_features: JobRankingFeatures,
) -> bool:
    if not selected_experiences:
        return project.matched_must_have_count >= 1

    project_must_haves = {
        skill.casefold()
        for skill in project.ranking_explanation.matched_required_skills
    }
    if not project_must_haves:
        return False

    experience_must_haves = {
        skill.casefold()
        for experience in selected_experiences
        for skill in experience.ranking_explanation.matched_required_skills
    }

    uncovered_must_haves = project_must_haves - experience_must_haves

    if uncovered_must_haves and len(uncovered_must_haves) >= 1:
        return True

    project_requirements = {
        req.casefold() for req in project.ranking_explanation.matched_job_requirements
    }
    experience_requirements = {
        req.casefold()
        for experience in selected_experiences
        for req in experience.ranking_explanation.matched_job_requirements
    }

    uncovered_requirements = project_requirements - experience_requirements
    return len(uncovered_requirements) >= 2 and project.strategic_fit_score >= 0.4


def _experience_coverage_ratio(
    selected_experiences: list[ExperienceAggregateScore],
    job_features: JobRankingFeatures,
) -> float:
    if not selected_experiences:
        return 0.0
    signal_buckets = _combined_signal_buckets(selected_experiences, job_features)
    required_score = _coverage_score(
        len(signal_buckets["must_have"]),
        len(job_features.canonical_must_have_skills.values),
    )
    requirement_score = _coverage_score(
        len(signal_buckets["requirements"]),
        _expected_requirement_count(job_features),
    )
    responsibility_score = _coverage_score(
        len(signal_buckets["responsibility"]),
        max(1, len(job_features.responsibility_themes) or 1),
    )
    return round(
        min(
            1.0,
            required_score * 0.55
            + requirement_score * 0.3
            + responsibility_score * 0.15,
        ),
        4,
    )


def _project_coverage_ratio(
    selected_projects: list[ProjectAggregateScore],
    job_features: JobRankingFeatures,
) -> float:
    if not selected_projects:
        return 0.0
    signal_buckets = _combined_signal_buckets(selected_projects, job_features)
    return round(
        min(
            1.0,
            _coverage_score(
                len(signal_buckets["must_have"]),
                len(job_features.canonical_must_have_skills.values),
            )
            * 0.6
            + _coverage_score(
                len(signal_buckets["requirements"]),
                _expected_requirement_count(job_features),
            )
            * 0.4,
        ),
        4,
    )


def _combined_signal_buckets(
    selected_items: list[ExperienceAggregateScore] | list[ProjectAggregateScore],
    job_features: JobRankingFeatures,
) -> dict[str, set[str]]:
    combined = {
        "must_have": set(),
        "preferred": set(),
        "requirements": set(),
        "responsibility": set(),
        "domain": set(),
        "leadership": set(),
    }
    for item in selected_items:
        item_signals = _aggregate_signal_buckets(item, job_features)
        for key, values in item_signals.items():
            combined[key].update(values)
    return combined


def _aggregate_signal_buckets(
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    job_features: JobRankingFeatures,
) -> dict[str, set[str]]:
    matched_keywords = {
        _comparison_key(keyword)
        for keyword in aggregate.ranking_explanation.matched_keywords
        if keyword
    }
    matched_requirements = {
        _comparison_key(requirement)
        for requirement in aggregate.ranking_explanation.matched_job_requirements
        if requirement
    }
    matched_required = {
        _comparison_key(skill)
        for skill in aggregate.ranking_explanation.matched_required_skills
        if skill
    }
    matched_preferred = {
        _comparison_key(skill)
        for skill in aggregate.ranking_explanation.matched_preferred_skills
        if skill
    }
    responsibility_themes = {
        _comparison_key(theme)
        for theme in job_features.responsibility_themes
        if theme
    }
    domain_targets = {
        _comparison_key(target)
        for target in job_features.domain_targets
        if target
    }

    responsibility_matches = {
        value
        for value in matched_keywords | matched_requirements
        if value in responsibility_themes
    }
    domain_matches = {
        value for value in matched_keywords | matched_requirements if value in domain_targets
    }
    leadership_matches = {
        value
        for value in matched_keywords | matched_requirements
        if any(
            token in value
            for token in (
                "lead",
                "manager",
                "mentor",
                "owner",
                "ownership",
                "stakeholder",
                "roadmap",
                "delivery",
                "execution",
                "architect",
                "strategy",
            )
        )
    }

    return {
        "must_have": matched_required,
        "preferred": matched_preferred,
        "requirements": matched_requirements,
        "responsibility": responsibility_matches,
        "domain": domain_matches,
        "leadership": leadership_matches,
    }


def _aggregate_overlap_signals(
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
) -> set[str]:
    signals = {
        f"required:{_comparison_key(skill)}"
        for skill in aggregate.ranking_explanation.matched_required_skills
        if skill
    }
    signals.update(
        f"preferred:{_comparison_key(skill)}"
        for skill in aggregate.ranking_explanation.matched_preferred_skills
        if skill
    )
    signals.update(
        f"requirement:{_comparison_key(requirement)}"
        for requirement in aggregate.ranking_explanation.matched_job_requirements
        if requirement
    )
    signals.update(
        f"keyword:{_comparison_key(keyword)}"
        for keyword in aggregate.ranking_explanation.matched_keywords
        if keyword
    )
    return signals
