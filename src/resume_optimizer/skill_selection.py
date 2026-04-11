"""Deterministic strategic skill highlighting for Phase 3D."""

from __future__ import annotations

from collections import defaultdict

from .job_feature_adapter import JobRankingFeatures
from .models import MasterProfile
from .resume_selection_models import (
    EvidenceScore,
    ExperienceAggregateScore,
    OmittedSelectionItem,
    ProjectAggregateScore,
    SelectionAudit,
    SkillHighlightScore,
)


def select_strategic_skills(
    *,
    source_profile: MasterProfile,
    job_features: JobRankingFeatures,
    evidence_scores: list[EvidenceScore],
    selected_experiences: list[ExperienceAggregateScore],
    selected_projects: list[ProjectAggregateScore],
    max_highlighted_skills: int,
    max_per_category: int,
) -> tuple[list[SkillHighlightScore], list[OmittedSelectionItem]]:
    """Return ordered, evidence-backed skills plus explicit omission reasons."""

    selected_source_ids = {
        *[item.source_item_id for item in selected_experiences],
        *[item.source_item_id for item in selected_projects],
    }
    evidence_by_source: dict[str, list[EvidenceScore]] = defaultdict(list)
    for evidence in evidence_scores:
        if evidence.source_item_id in selected_source_ids:
            evidence_by_source[evidence.source_item_id].append(evidence)

    scored_skills: list[tuple[float, float, int, SkillHighlightScore]] = []
    omitted: list[OmittedSelectionItem] = []

    for skill in source_profile.skills:
        skill_key = _comparison_key(skill.name)
        jd_weight = _job_relevance_weight(skill_key, job_features)
        supporting_evidence = [
            evidence
            for evidence_list in evidence_by_source.values()
            for evidence in evidence_list
            if skill_key in {_comparison_key(keyword) for keyword in evidence.keywords}
            or skill_key in {_comparison_key(keyword) for keyword in evidence.ranking_explanation.matched_keywords}
        ]
        if jd_weight <= 0:
            omitted.append(
                OmittedSelectionItem(
                    item_type=skill.item_type,
                    source_item_id=skill.id,
                    reason="weak_strategic_fit",
                    rationale="Skill is not materially prioritized by the target role.",
                    selection_audit=SelectionAudit(
                        selection_reason="skill_omitted",
                        omission_reason="weak_strategic_fit",
                        human_summary="Skill was not materially prioritized by the target role.",
                    ),
                )
            )
            continue
        if not supporting_evidence:
            omitted.append(
                OmittedSelectionItem(
                    item_type=skill.item_type,
                    source_item_id=skill.id,
                    reason="low_relevance",
                    rationale="Skill is present in inventory but not supported by selected experiences or projects.",
                    selection_audit=SelectionAudit(
                        matched_requirements=[skill.name] if jd_weight > 0 else [],
                        selection_reason="skill_omitted",
                        omission_reason="low_relevance",
                        human_summary="Skill lacked support from selected evidence.",
                    ),
                )
            )
            continue

        support_strength = min(1.0, len(supporting_evidence) / 3)
        avg_relevance = sum(evidence.relevance_score for evidence in supporting_evidence) / len(
            supporting_evidence
        )
        recency = _average_component(supporting_evidence, "recency")
        ats_value = 1.0 if skill_key in {_comparison_key(value) for value in job_features.canonical_all_skills} else 0.0
        role_importance = _role_family_importance(skill_key, job_features)
        score = round(
            min(
                1.0,
                jd_weight * 0.35
                + support_strength * 0.2
                + avg_relevance * 0.2
                + recency * 0.1
                + ats_value * 0.1
                + role_importance * 0.05,
            ),
            4,
        )
        priority_index = _job_priority_index(skill_key, job_features)
        scored_skills.append(
            (
                score,
                jd_weight,
                priority_index,
                SkillHighlightScore(
                    source_item_id=skill.id,
                    skill_name=skill.name,
                    category=skill.category,
                    relevance_score=score,
                    evidence_score_ids=[evidence.id for evidence in supporting_evidence],
                    recency_score=round(recency, 4),
                    ats_value_score=round(ats_value, 4),
                    role_family_importance_score=round(role_importance, 4),
                    ranking_explanation=_build_skill_explanation(
                        skill.name,
                        jd_weight=jd_weight,
                        support_count=len(supporting_evidence),
                        avg_relevance=avg_relevance,
                    ),
                    selection_audit=SelectionAudit(
                        matched_requirements=[skill.name],
                        score_factors={
                            "job_relevance_weight": jd_weight,
                            "support_strength": round(support_strength, 4),
                            "average_evidence_relevance": round(avg_relevance, 4),
                            "recency_score": round(recency, 4),
                            "ats_value_score": round(ats_value, 4),
                            "role_family_importance_score": round(role_importance, 4),
                            "final_skill_score": score,
                        },
                        evidence_signals=[
                            f"support_count:{len(supporting_evidence)}",
                            "job_relevant_skill",
                            "evidence_backed_skill",
                        ],
                        selection_reason=(
                            "skill_selected_for_must_have_supported_match"
                            if jd_weight >= 1.0
                            else "skill_selected_for_supported_job_match"
                        ),
                        supporting_evidence_ids=[evidence.id for evidence in supporting_evidence],
                        human_summary=f"{skill.name} is job-relevant and supported by selected evidence.",
                    ),
                    provenance={"source_type": "skill", "source_item_id": skill.id},
                ),
            )
        )

    scored_skills.sort(
        key=lambda item: (
            -item[1],
            item[2],
            -item[0],
            -len(item[3].evidence_score_ids),
            -item[3].recency_score,
            item[3].skill_name.casefold(),
        ),
    )

    selected: list[SkillHighlightScore] = []
    category_counts: dict[str, int] = defaultdict(int)
    for _, _, _, skill in scored_skills:
        category_key = _comparison_key(skill.category)
        allow_must_have_overflow = (
            category_counts[category_key] < (max_per_category + 1)
            and skill.selection_audit.score_factors.get("job_relevance_weight", 0.0) >= 1.0
        )
        if len(selected) >= max_highlighted_skills:
            omitted.append(
                OmittedSelectionItem(
                    item_type=skill.item_type,
                    source_item_id=skill.source_item_id,
                    evidence_score_ids=skill.evidence_score_ids,
                    reason="insufficient_page_budget_priority",
                    rationale="Higher-priority evidence-backed skills already fill the highlight budget.",
                    selection_audit=SelectionAudit(
                        matched_requirements=[skill.skill_name],
                        score_factors={"final_skill_score": skill.relevance_score},
                        selection_reason="skill_omitted",
                        supporting_evidence_ids=skill.evidence_score_ids,
                        omission_reason="insufficient_page_budget_priority",
                        human_summary="Higher-priority skills already fill the highlight budget.",
                    ),
                )
            )
            continue
        if category_counts[category_key] >= max_per_category and not allow_must_have_overflow:
            omitted.append(
                OmittedSelectionItem(
                    item_type=skill.item_type,
                    source_item_id=skill.source_item_id,
                    evidence_score_ids=skill.evidence_score_ids,
                    reason="redundant_with_stronger_selected_content",
                    rationale="Another stronger skill from the same category was already selected.",
                    selection_audit=SelectionAudit(
                        matched_requirements=[skill.skill_name],
                        score_factors={"final_skill_score": skill.relevance_score},
                        selection_reason="skill_omitted",
                        supporting_evidence_ids=skill.evidence_score_ids,
                        omission_reason="redundant_with_stronger_selected_content",
                        human_summary="A stronger skill from the same category was already selected.",
                    ),
                )
            )
            continue
        category_counts[category_key] += 1
        selected.append(skill)

    return selected, omitted


def _job_relevance_weight(skill_key: str, job_features: JobRankingFeatures) -> float:
    if skill_key in {_comparison_key(value) for value in job_features.canonical_must_have_skills.values}:
        return 1.0
    if skill_key in {_comparison_key(value) for value in job_features.canonical_nice_to_have_skills.values}:
        return 0.75
    if skill_key in {_comparison_key(value) for value in job_features.canonical_all_skills}:
        return 0.5
    return 0.0


def _job_priority_index(skill_key: str, job_features: JobRankingFeatures) -> int:
    ordered = [
        *job_features.canonical_must_have_skills.values,
        *job_features.canonical_nice_to_have_skills.values,
        *job_features.canonical_all_skills,
    ]
    for index, value in enumerate(ordered):
        if _comparison_key(value) == skill_key:
            return index
    return 999


def _average_component(evidence_scores: list[EvidenceScore], component_name: str) -> float:
    values = [
        max(0.0, min(1.0, score.component_scores[component_name].value / 10.0))
        for score in evidence_scores
        if component_name in score.component_scores
    ]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _role_family_importance(skill_key: str, job_features: JobRankingFeatures) -> float:
    role_family = _comparison_key(job_features.role_family or "")
    domain_targets = {_comparison_key(value) for value in job_features.domain_targets}
    if role_family and role_family in skill_key:
        return 1.0
    if skill_key in domain_targets:
        return 0.8
    return 0.5 if skill_key in {_comparison_key(value) for value in job_features.canonical_all_skills} else 0.0


def _build_skill_explanation(
    skill_name: str,
    *,
    jd_weight: float,
    support_count: int,
    avg_relevance: float,
):
    from .ranking_explanation_models import RankingExplanation

    return RankingExplanation(
        summary=(
            f"Selected because {skill_name} is job-relevant and supported by selected evidence."
        ),
        matched_keywords=[skill_name],
        matched_required_skills=[skill_name] if jd_weight >= 1.0 else [],
        matched_preferred_skills=[skill_name] if 0.75 <= jd_weight < 1.0 else [],
        matched_job_requirements=[skill_name],
        matched_prioritized_skills=[skill_name],
        explanation_fragments=[
            f"job relevance weight: {jd_weight:.2f}",
            f"supporting evidence count: {support_count}",
            f"average evidence relevance: {avg_relevance:.2f}",
        ],
        signal_labels=["job_skill_match", "evidence_backed_skill"],
    )


def _comparison_key(value: str) -> str:
    return " ".join(value.casefold().split())
