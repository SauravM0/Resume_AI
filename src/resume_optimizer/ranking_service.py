"""Deterministic Phase 2 ranking and constrained selection service."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import logging
import re

from .evidence_models import CandidateEvidenceCoverageMap, CandidateEvidenceGraph, CanonicalEvidenceUnit, EvidenceSourceType
from .explainability import build_phase2_diagnostics, build_ranking_explanation
from .job_feature_adapter import JobRankingFeatures, adapt_job_analysis_to_ranking_features
from .job_models import NormalizedJobAnalysis
from .models import ItemType, MasterProfile
from .phase2_artifacts import Phase2CandidateArtifacts, build_phase2_candidate_artifacts
from .phase2_config import DEFAULT_PHASE2_CONFIG
from .phase2_models import (
    Phase2SelectionResult,
    SelectedExperience,
    SelectedProject,
    SelectedSkill,
)
from .ranking_models import RankedItem, RankingResponse, SummaryBriefTheme
from .provenance import build_provenance_payload, validate_provenance_against_profile
from .resume_selection import compose_resume_selection
from .resume_selection_models import (
    EvidenceScore,
    ExperienceAggregateScore,
    ProjectAggregateScore,
    ResumeSelectionDecision,
    SkillHighlightScore,
)
from .scoring_config import DEFAULT_HYBRID_SCORING_CONFIG
from .scoring_engine import HybridScoreResult, HybridScoringEngine
from .semantic_scoring import build_semantic_scorer

MAX_EXPERIENCES = DEFAULT_PHASE2_CONFIG.selection_limits.max_experiences
MAX_PROJECTS = DEFAULT_PHASE2_CONFIG.selection_limits.max_projects
MAX_CERTIFICATIONS = DEFAULT_PHASE2_CONFIG.selection_limits.max_certifications
_MAX_BULLETS_PER_ITEM = DEFAULT_PHASE2_CONFIG.selection_limits.max_bullets_per_item
_MIN_BULLETS_IF_AVAILABLE = DEFAULT_PHASE2_CONFIG.selection_limits.min_bullets_if_available
_THEME_LIMIT = DEFAULT_PHASE2_CONFIG.selection_limits.max_summary_themes
_RECENT_EVIDENCE_THRESHOLD = DEFAULT_PHASE2_CONFIG.thresholds.recent_evidence_score_threshold
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ROLE_HEADLINES = {
    "individual_contributor": "Software Engineer",
    "lead": "Lead Software Engineer",
    "manager": "Engineering Manager",
    "director": "Engineering Director",
    "executive": "Engineering Leader",
    "consultant": "Consulting Engineer",
    "founder": "Technical Founder",
    "researcher": "Research Engineer",
    "student": "Student Engineer",
    "advisor": "Technical Advisor",
}
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Phase2RankingArtifacts:
    """Full Phase 2 artifacts for service integration and downstream phases."""

    ranking_response: RankingResponse
    selection_result: Phase2SelectionResult
    job_features: JobRankingFeatures
    candidate_artifacts: Phase2CandidateArtifacts

    @property
    def evidence_graph(self) -> CandidateEvidenceGraph:
        return self.candidate_artifacts.evidence_graph

    @property
    def coverage_map(self) -> CandidateEvidenceCoverageMap:
        return self.candidate_artifacts.coverage_map


def rank_evidence_for_job(
    job_analysis: NormalizedJobAnalysis,
    source_profile: MasterProfile,
    *,
    today: date | None = None,
    scoring_engine: HybridScoringEngine | None = None,
) -> RankingResponse:
    """Return the backward-compatible Phase 2 ranking response."""

    return build_phase2_ranking_artifacts(
        job_analysis,
        source_profile,
        today=today,
        scoring_engine=scoring_engine,
    ).ranking_response


def build_phase2_ranking_artifacts(
    job_analysis: NormalizedJobAnalysis,
    source_profile: MasterProfile,
    *,
    today: date | None = None,
    scoring_engine: HybridScoringEngine | None = None,
) -> Phase2RankingArtifacts:
    """Build canonical Phase 2 artifacts plus the legacy ranking response."""

    job_features = adapt_job_analysis_to_ranking_features(job_analysis)
    candidate_artifacts = build_phase2_candidate_artifacts(source_profile)
    evidence_pool = candidate_artifacts.ranking_compatible_evidence

    evidence_scores, scored_evidence, score_results_by_id, evidence_units_by_id, provenance_warnings = _score_atomic_evidence(
        evidence_pool=evidence_pool,
        job_features=job_features,
        source_profile=source_profile,
        today=today,
        scoring_engine=scoring_engine or _build_scoring_engine(),
    )
    resume_selection = compose_resume_selection(
        evidence_scores=evidence_scores,
        evidence_units_by_id=evidence_units_by_id,
        score_results_by_id=score_results_by_id,
        source_profile=source_profile,
        job_features=job_features,
        max_experiences=MAX_EXPERIENCES,
        max_projects=MAX_PROJECTS,
        max_highlighted_skills=DEFAULT_PHASE2_CONFIG.selection_limits.max_highlighted_skills,
        max_highlighted_skills_per_category=DEFAULT_PHASE2_CONFIG.selection_limits.max_highlighted_skills_per_category,
        max_bullet_share_per_experience=DEFAULT_PHASE2_CONFIG.selection_limits.max_bullet_share_per_experience,
        minimum_experience_spread=DEFAULT_PHASE2_CONFIG.selection_limits.minimum_experience_spread,
        dominant_experience_score_gap=DEFAULT_PHASE2_CONFIG.thresholds.dominant_experience_score_gap,
        similar_experience_score_gap=DEFAULT_PHASE2_CONFIG.thresholds.similar_experience_score_gap,
        max_bullets_per_item=_MAX_BULLETS_PER_ITEM,
        min_bullets_if_available=_MIN_BULLETS_IF_AVAILABLE,
    )
    logger.debug(
        "phase2 selection decision",
        extra={
            "selected_experiences": [
                {
                    "id": item.source_item_id,
                    "reason": item.selection_audit.selection_reason,
                    "summary": item.selection_audit.human_summary,
                    "score_factors": item.selection_audit.score_factors,
                }
                for item in resume_selection.selected_experiences
            ],
            "selected_projects": [
                {
                    "id": item.source_item_id,
                    "reason": item.selection_audit.selection_reason,
                    "summary": item.selection_audit.human_summary,
                    "score_factors": item.selection_audit.score_factors,
                }
                for item in resume_selection.selected_projects
            ],
            "selected_skills": [
                {
                    "id": item.source_item_id,
                    "skill": item.skill_name,
                    "reason": item.selection_audit.selection_reason,
                    "summary": item.selection_audit.human_summary,
                    "score_factors": item.selection_audit.score_factors,
                }
                for item in resume_selection.selected_skills
            ],
            "omitted_candidates": [
                {
                    "id": item.source_item_id,
                    "type": item.item_type.value,
                    "reason": item.reason,
                    "summary": item.selection_audit.human_summary,
                }
                for item in resume_selection.omitted_items[:10]
            ],
        },
    )
    ranked_experiences = [
        _project_aggregate_to_ranked_item(aggregate, source_profile, ItemType.EXPERIENCE)
        for aggregate in resume_selection.selected_experiences
    ]
    ranked_projects = [
        _project_aggregate_to_ranked_item(aggregate, source_profile, ItemType.PROJECT)
        for aggregate in resume_selection.selected_projects
    ]
    ranked_certifications = _select_ranked_items(
        scored_evidence,
        item_type=ItemType.CERTIFICATION,
        limit=MAX_CERTIFICATIONS,
    )

    selected_ids = _selected_evidence_ids(
        resume_selection=resume_selection,
        ranked_certifications=ranked_certifications,
    )
    selected_score_results = [
        score_results_by_id[evidence_id]
        for evidence_id in selected_ids
        if evidence_id in score_results_by_id
    ]
    diagnostics = build_phase2_diagnostics(
        scored_items=[
            (evidence_units_by_id[evidence_score.id], score_results_by_id[evidence_score.id])
            for evidence_score in evidence_scores
        ],
        selected_item_ids=selected_ids,
        warnings=provenance_warnings,
    )
    if diagnostics.warnings or diagnostics.weak_coverage_areas or diagnostics.near_miss_item_ids:
        logger.debug(
            "phase2 diagnostics",
            extra={
                "warnings": diagnostics.warnings,
                "weak_coverage_areas": diagnostics.weak_coverage_areas,
                "near_miss_item_ids": diagnostics.near_miss_item_ids,
            },
        )

    ranking_response = RankingResponse(
        ranked_experiences=ranked_experiences,
        ranked_projects=ranked_projects,
        ranked_certifications=ranked_certifications,
        atomic_evidence_scores=evidence_scores,
        resume_selection_decision=resume_selection,
        skills_to_highlight=[item.skill_name for item in resume_selection.selected_skills],
        headline_suggestion=_build_headline_suggestion(job_analysis),
        summary_brief_themes=_build_summary_brief_themes(selected_score_results),
    )
    selection_result = Phase2SelectionResult(
        job_analysis=job_analysis.model_dump(),
        candidate_profile_id=source_profile.id,
        evidence_scores=evidence_scores,
        scored_evidence=scored_evidence,
        resume_selection_decision=resume_selection,
        selected_experiences=_build_selected_experiences(resume_selection),
        selected_projects=_build_selected_projects(resume_selection),
        selected_skills=_build_selected_skills(resume_selection.selected_skills),
        diagnostics=diagnostics.model_copy(
            update={"candidate_evidence_count": len(evidence_pool)}
        ),
    )
    return Phase2RankingArtifacts(
        ranking_response=ranking_response,
        selection_result=selection_result,
        job_features=job_features,
        candidate_artifacts=candidate_artifacts,
    )


def _select_ranked_items(
    scored_items: list[RankedItem],
    *,
    item_type: ItemType,
    limit: int,
) -> list[RankedItem]:
    filtered = [ranked_item for ranked_item in scored_items if ranked_item.item_type == item_type]
    filtered.sort(
        key=lambda item: (
            item.relevance_score,
            len(item.matching_keywords),
            len(item.include_bullet_indexes),
            item.id,
        ),
        reverse=True,
    )
    return filtered[:limit]

def _score_atomic_evidence(
    *,
    evidence_pool: list[CanonicalEvidenceUnit],
    job_features: JobRankingFeatures,
    source_profile: MasterProfile,
    today: date | None,
    scoring_engine: HybridScoringEngine,
) -> tuple[
    list[EvidenceScore],
    list[RankedItem],
    dict[str, HybridScoreResult],
    dict[str, CanonicalEvidenceUnit],
    list[str],
]:
    evidence_scores: list[EvidenceScore] = []
    scored_evidence: list[RankedItem] = []
    score_results_by_id: dict[str, HybridScoreResult] = {}
    evidence_units_by_id: dict[str, CanonicalEvidenceUnit] = {}
    provenance_warnings: list[str] = []

    for evidence_item in evidence_pool:
        item_type = _legacy_item_type(evidence_item)
        if item_type is None:
            continue
        score_result = scoring_engine.score_evidence_unit(
            evidence_item,
            job_features=job_features,
            today=today,
        )
        provenance_warnings.extend(validate_provenance_against_profile(evidence_item, source_profile))
        evidence_score = _build_evidence_score(evidence_item, item_type, score_result, job_features)
        evidence_scores.append(evidence_score)
        scored_evidence.append(_project_evidence_score_to_ranked_item(evidence_score, evidence_item))
        score_results_by_id[evidence_score.id] = score_result
        evidence_units_by_id[evidence_score.id] = evidence_item

    scored_evidence.sort(
        key=lambda item: (
            item.relevance_score,
            len(item.matching_keywords),
            item.id,
        ),
        reverse=True,
    )
    return (
        evidence_scores,
        scored_evidence,
        score_results_by_id,
        evidence_units_by_id,
        provenance_warnings,
    )


def _build_scoring_engine() -> HybridScoringEngine:
    return HybridScoringEngine(
        semantic_scorer=build_semantic_scorer(DEFAULT_HYBRID_SCORING_CONFIG.semantic),
    )


def _build_evidence_score(
    evidence_item: CanonicalEvidenceUnit,
    item_type: ItemType,
    score_result: HybridScoreResult,
    job_features: JobRankingFeatures,
) -> EvidenceScore:
    return EvidenceScore(
        id=evidence_item.evidence_unit_id,
        item_type=item_type,
        source_item_id=evidence_item.source_entity_id,
        source_bullet_id=evidence_item.source_bullet_id,
        title=evidence_item.provenance.source_entity_title or evidence_item.raw_text,
        evidence_text=evidence_item.raw_text,
        domain_tags=evidence_item.normalized_domains,
        relevant_for=[
            *evidence_item.inferred_role_types,
            *evidence_item.seniority_signals,
            *evidence_item.impact_signals,
        ],
        keywords=[*evidence_item.normalized_skills, *evidence_item.normalized_tools],
        relevance_score=round(score_result.total_score / 100.0, 4),
        ranking_explanation=build_ranking_explanation(
            evidence_unit=evidence_item,
            score_result=score_result,
            job_features=job_features,
        ),
        provenance=build_provenance_payload(evidence_item),
        component_scores=score_result.component_scores,
    )


def _project_evidence_score_to_ranked_item(
    evidence_score: EvidenceScore,
    evidence_item: CanonicalEvidenceUnit,
) -> RankedItem:
    include_bullet_indexes = [0] if evidence_score.source_bullet_id is not None else []
    selected_bullet_ids = [evidence_score.source_bullet_id] if evidence_score.source_bullet_id else []
    return RankedItem(
        id=evidence_score.id,
        item_type=evidence_score.item_type,
        source_item_id=evidence_score.source_item_id,
        source_bullet_ids=selected_bullet_ids,
        title=evidence_score.title,
        domain_tags=evidence_score.domain_tags,
        relevant_for=evidence_score.relevant_for,
        keywords=evidence_score.keywords,
        bullets=[evidence_score.evidence_text] if evidence_score.source_bullet_id else [],
        impact=1.0 if "high_impact_score" in evidence_item.impact_signals else None,
        level=evidence_item.seniority_signals[0] if evidence_item.seniority_signals else None,
        start=evidence_item.recency.start_date,
        end=evidence_item.recency.end_date,
        relevance_score=evidence_score.relevance_score,
        ranking_explanation=evidence_score.ranking_explanation,
        provenance=evidence_score.provenance,
        component_scores=evidence_score.component_scores,
        selected_bullet_ids=selected_bullet_ids,
        include_bullet_indexes=include_bullet_indexes,
    )


def _project_aggregate_to_ranked_item(
    aggregate: ExperienceAggregateScore | ProjectAggregateScore,
    source_profile: MasterProfile,
    item_type: ItemType,
) -> RankedItem:
    source_entries = (
        {entry.id: entry for entry in source_profile.experience}
        if item_type == ItemType.EXPERIENCE
        else {entry.id: entry for entry in source_profile.projects}
    )
    entry = source_entries[aggregate.source_item_id]
    bullet_lookup = {bullet.id: bullet.text for bullet in entry.bullets}
    bullet_indexes = {bullet.id: index for index, bullet in enumerate(entry.bullets)}
    return RankedItem(
        id=f"agg.{aggregate.source_item_id}",
        item_type=item_type,
        source_item_id=aggregate.source_item_id,
        source_bullet_ids=list(aggregate.selected_bullet_ids),
        title=aggregate.title,
        domain_tags=[],
        relevant_for=[],
        keywords=list(aggregate.ranking_explanation.matched_keywords),
        bullets=[
            bullet_lookup[bullet_id]
            for bullet_id in aggregate.selected_bullet_ids
            if bullet_id in bullet_lookup
        ],
        relevance_score=aggregate.relevance_score,
        ranking_explanation=aggregate.ranking_explanation,
        provenance={
            "source_type": item_type.value,
            "source_item_id": aggregate.source_item_id,
            "evidence_score_ids": list(aggregate.evidence_score_ids),
        },
        component_scores={},
        selected_bullet_ids=list(aggregate.selected_bullet_ids),
        include_bullet_indexes=[
            bullet_indexes[bullet_id]
            for bullet_id in aggregate.selected_bullet_ids
            if bullet_id in bullet_indexes
        ],
    )


def _selected_evidence_ids(
    *,
    resume_selection: ResumeSelectionDecision,
    ranked_certifications: list[RankedItem],
) -> set[str]:
    selected_ids = {
        evidence_id
        for aggregate in [*resume_selection.selected_experiences, *resume_selection.selected_projects]
        for evidence_id in aggregate.evidence_score_ids
    }
    selected_ids.update(item.id for item in ranked_certifications)
    return selected_ids


def _build_selected_experiences(
    resume_selection: ResumeSelectionDecision,
) -> list[SelectedExperience]:
    selected: list[SelectedExperience] = []
    for item in resume_selection.selected_experiences:
        if not item.selected_bullet_ids:
            continue
        selected.append(
            SelectedExperience(
                id=f"sel.{item.source_item_id}",
                source_item_id=item.source_item_id,
                relevance_score=item.relevance_score,
                evidence_unit_ids=item.evidence_score_ids,
                selected_bullet_ids=item.selected_bullet_ids,
                ranking_explanation=item.ranking_explanation,
                provenance={
                    "source_type": ItemType.EXPERIENCE.value,
                    "source_item_id": item.source_item_id,
                    "evidence_score_ids": item.evidence_score_ids,
                },
            )
        )
    return selected


def _build_selected_projects(
    resume_selection: ResumeSelectionDecision,
) -> list[SelectedProject]:
    selected: list[SelectedProject] = []
    for item in resume_selection.selected_projects:
        if not item.selected_bullet_ids:
            continue
        selected.append(
            SelectedProject(
                id=f"sel.{item.source_item_id}",
                source_item_id=item.source_item_id,
                relevance_score=item.relevance_score,
                evidence_unit_ids=item.evidence_score_ids,
                selected_bullet_ids=item.selected_bullet_ids,
                ranking_explanation=item.ranking_explanation,
                provenance={
                    "source_type": ItemType.PROJECT.value,
                    "source_item_id": item.source_item_id,
                    "evidence_score_ids": item.evidence_score_ids,
                },
            )
        )
    return selected


def _build_selected_skills(
    skills_to_highlight: list[SkillHighlightScore],
) -> list[SelectedSkill]:
    selected: list[SelectedSkill] = []
    for skill in skills_to_highlight:
        skill_key = _comparison_key(skill.skill_name).replace(" ", ".")
        selected.append(
            SelectedSkill(
                id=f"sel.skill.{skill_key}",
                source_item_id=skill.source_item_id,
                relevance_score=skill.relevance_score,
                skill_name=skill.skill_name,
                ranking_explanation=skill.ranking_explanation,
                provenance=skill.provenance,
            )
        )
    return selected


def _build_headline_suggestion(
    job_analysis: NormalizedJobAnalysis,
) -> str | None:
    role_value = job_analysis.role_type.value if job_analysis.role_type is not None else None
    seniority_value = (
        job_analysis.seniority_level.value if job_analysis.seniority_level is not None else None
    )

    if role_value is None and seniority_value is None:
        return None

    base_headline = _ROLE_HEADLINES.get(role_value or "", "Software Engineer")
    if seniority_value in {"intern", "junior", "mid", "senior", "staff", "principal"}:
        return f"{seniority_value.replace('_', ' ').title()} {base_headline}"
    return base_headline


def _build_summary_brief_themes(
    score_results: list[HybridScoreResult],
) -> list[SummaryBriefTheme]:
    if not score_results:
        return []

    keyword_counts = Counter(
        keyword
        for result in score_results
        for keyword in [*result.matched_required_skills, *result.matched_preferred_skills]
    )
    relevant_counts = Counter(tag for result in score_results for tag in result.explanation_fragments)
    domain_counts = Counter(
        "domain overlap"
        for result in score_results
        if result.component_scores["domain_relevance"].value > 0
    )

    candidates: list[tuple[int, SummaryBriefTheme]] = []
    if keyword_counts:
        candidates.append(
            (
                sum(keyword_counts.values()),
                SummaryBriefTheme(
                    theme="Technical skill alignment",
                    supporting_keywords=[item for item, _ in keyword_counts.most_common(3)],
                ),
            )
        )
    if domain_counts:
        candidates.append(
            (
                sum(domain_counts.values()),
                SummaryBriefTheme(
                    theme="Relevant domain experience",
                    supporting_keywords=[item for item, _ in domain_counts.most_common(3)],
                ),
            )
        )
    if relevant_counts:
        candidates.append(
            (
                sum(relevant_counts.values()),
                SummaryBriefTheme(
                    theme="Relevant delivery themes",
                    supporting_keywords=[item for item, _ in relevant_counts.most_common(3)],
                ),
            )
        )

    if any(result.component_scores["recency"].value >= _RECENT_EVIDENCE_THRESHOLD for result in score_results):
        candidates.append(
            (
                1,
                SummaryBriefTheme(
                    theme="Recent evidence",
                    supporting_keywords=[],
                ),
            )
        )

    candidates.sort(key=lambda item: (item[0], item[1].theme), reverse=True)
    return [theme for _, theme in candidates[:_THEME_LIMIT]]


def _legacy_item_type(evidence_item: CanonicalEvidenceUnit) -> ItemType | None:
    if evidence_item.source_type in {
        EvidenceSourceType.EXPERIENCE_BULLET,
        EvidenceSourceType.EXPERIENCE_SUMMARY,
    }:
        return ItemType.EXPERIENCE
    if evidence_item.source_type in {
        EvidenceSourceType.PROJECT_BULLET,
        EvidenceSourceType.PROJECT_SUMMARY,
    }:
        return ItemType.PROJECT
    if evidence_item.source_type == EvidenceSourceType.CERTIFICATION:
        return ItemType.CERTIFICATION
    return None


def _comparison_key(value: str) -> str:
    return " ".join(_tokenize(value))


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())
