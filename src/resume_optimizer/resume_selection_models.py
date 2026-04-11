"""Typed models for Phase 3A atomic scoring and resume-level selection."""

from __future__ import annotations

from pydantic import Field

from .models import ItemType, NonEmptyStr, ScoreValue, StableId, StrictModel
from .ranking_explanation_models import RankingExplanation
from .scoring_engine import ScoreComponent


class SelectionAudit(StrictModel):
    """Machine-readable explanation for one selection or omission decision."""

    matched_requirements: list[NonEmptyStr] = Field(default_factory=list)
    score_factors: dict[str, float] = Field(default_factory=dict)
    evidence_signals: list[NonEmptyStr] = Field(default_factory=list)
    selection_reason: NonEmptyStr
    supporting_evidence_ids: list[StableId] = Field(default_factory=list)
    omission_reason: NonEmptyStr | None = None
    human_summary: NonEmptyStr | None = None


class EvidenceScore(StrictModel):
    """Atomic Layer A score for one canonical evidence unit."""

    id: StableId
    item_type: ItemType
    source_item_id: StableId
    source_bullet_id: StableId | None = None
    title: NonEmptyStr
    evidence_text: NonEmptyStr
    domain_tags: list[NonEmptyStr] = Field(default_factory=list)
    relevant_for: list[NonEmptyStr] = Field(default_factory=list)
    keywords: list[NonEmptyStr] = Field(default_factory=list)
    relevance_score: ScoreValue
    ranking_explanation: RankingExplanation
    provenance: dict[str, object] = Field(default_factory=dict)
    component_scores: dict[str, ScoreComponent] = Field(default_factory=dict)


class ExperienceAggregateScore(StrictModel):
    """Resume-level experience selection derived from multiple evidence scores."""

    source_item_id: StableId
    title: NonEmptyStr
    relevance_score: ScoreValue
    strongest_evidence_score: ScoreValue = 0.0
    average_relevant_evidence_score: ScoreValue = 0.0
    matched_must_have_count: int = 0
    matched_preferred_count: int = 0
    matched_requirement_diversity: int = 0
    recency_score: ScoreValue = 0.0
    evidence_quality_score: ScoreValue = 0.0
    ownership_leadership_score: ScoreValue = 0.0
    impact_score: ScoreValue = 0.0
    strategic_fit_score: ScoreValue = 0.0
    direct_alignment_score: ScoreValue = 0.0
    role_fit_score: ScoreValue = 0.0
    seniority_fit_score: ScoreValue = 0.0
    domain_fit_score: ScoreValue = 0.0
    responsibility_match_score: ScoreValue = 0.0
    must_have_coverage_score: ScoreValue = 0.0
    preferred_coverage_score: ScoreValue = 0.0
    stale_risk_score: ScoreValue = 0.0
    weak_evidence_ratio: ScoreValue = 0.0
    strategic_narrative_score: ScoreValue = 0.0
    recent_role_bonus_applied: ScoreValue = 0.0
    high_impact_bonus_applied: ScoreValue = 0.0
    ownership_leadership_bonus_applied: ScoreValue = 0.0
    evidence_score_ids: list[StableId] = Field(default_factory=list)
    selected_bullet_ids: list[StableId] = Field(default_factory=list)
    omitted_bullet_ids: list[StableId] = Field(default_factory=list)
    ranking_explanation: RankingExplanation
    selection_audit: SelectionAudit


class ProjectAggregateScore(StrictModel):
    """Resume-level project selection derived from multiple evidence scores."""

    source_item_id: StableId
    title: NonEmptyStr
    relevance_score: ScoreValue
    strongest_evidence_score: ScoreValue = 0.0
    average_relevant_evidence_score: ScoreValue = 0.0
    matched_must_have_count: int = 0
    matched_preferred_count: int = 0
    matched_requirement_diversity: int = 0
    recency_score: ScoreValue = 0.0
    evidence_quality_score: ScoreValue = 0.0
    ownership_leadership_score: ScoreValue = 0.0
    impact_score: ScoreValue = 0.0
    strategic_fit_score: ScoreValue = 0.0
    direct_alignment_score: ScoreValue = 0.0
    role_fit_score: ScoreValue = 0.0
    seniority_fit_score: ScoreValue = 0.0
    domain_fit_score: ScoreValue = 0.0
    responsibility_match_score: ScoreValue = 0.0
    must_have_coverage_score: ScoreValue = 0.0
    preferred_coverage_score: ScoreValue = 0.0
    stale_risk_score: ScoreValue = 0.0
    weak_evidence_ratio: ScoreValue = 0.0
    unique_evidence_score: ScoreValue = 0.0
    redundancy_score: ScoreValue = 0.0
    project_utility_score: ScoreValue = 0.0
    strategic_narrative_score: ScoreValue = 0.0
    recent_role_bonus_applied: ScoreValue = 0.0
    high_impact_bonus_applied: ScoreValue = 0.0
    ownership_leadership_bonus_applied: ScoreValue = 0.0
    evidence_score_ids: list[StableId] = Field(default_factory=list)
    selected_bullet_ids: list[StableId] = Field(default_factory=list)
    omitted_bullet_ids: list[StableId] = Field(default_factory=list)
    ranking_explanation: RankingExplanation
    selection_audit: SelectionAudit


class SkillHighlightScore(StrictModel):
    """Resume-level selected skill signal surfaced for the final resume."""

    item_type: ItemType = ItemType.SKILL
    source_item_id: StableId
    skill_name: NonEmptyStr
    category: NonEmptyStr | None = None
    relevance_score: ScoreValue
    evidence_score_ids: list[StableId] = Field(default_factory=list)
    recency_score: ScoreValue = 0.0
    ats_value_score: ScoreValue = 0.0
    role_family_importance_score: ScoreValue = 0.0
    ranking_explanation: RankingExplanation
    selection_audit: SelectionAudit
    provenance: dict[str, object] = Field(default_factory=dict)


class OmittedSelectionItem(StrictModel):
    """One omitted resume candidate with a deterministic reason."""

    item_type: ItemType
    source_item_id: StableId
    evidence_score_ids: list[StableId] = Field(default_factory=list)
    reason: NonEmptyStr
    rationale: NonEmptyStr | None = None
    selection_audit: SelectionAudit | None = None


class ProjectSelectionReasoning(StrictModel):
    """Section-level decision for whether projects should appear at all."""

    show_projects_section: bool = False
    reasons: list[NonEmptyStr] = Field(default_factory=list)
    portfolio_sensitive_role: bool = False
    experience_gap_detected: bool = False
    selected_project_ids: list[StableId] = Field(default_factory=list)
    omitted_project_ids: list[StableId] = Field(default_factory=list)


class ResumeSelectionDecision(StrictModel):
    """Layer B output that composes final resume selections from atomic scores."""

    selected_experiences: list[ExperienceAggregateScore] = Field(default_factory=list)
    selected_projects: list[ProjectAggregateScore] = Field(default_factory=list)
    omitted_projects: list[OmittedSelectionItem] = Field(default_factory=list)
    project_selection_reasoning: ProjectSelectionReasoning = Field(
        default_factory=ProjectSelectionReasoning
    )
    selected_skills: list[SkillHighlightScore] = Field(default_factory=list)
    omitted_items: list[OmittedSelectionItem] = Field(default_factory=list)
