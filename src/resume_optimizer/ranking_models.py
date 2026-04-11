"""Backward-compatible exports for Phase 2 ranking contracts."""

from __future__ import annotations

from pydantic import Field, field_validator

from .phase2_models import (
    CandidateProfileInput,
    EvidenceUnit,
    JobAnalysisInput,
    Phase2SelectionResult,
    ScoredEvidenceUnit,
)
from .job_models import NormalizedJobAnalysis
from .models import MasterProfile, NonEmptyStr, StrictModel
from .ranking_explanation_models import RankingExplanation
from .resume_selection_models import EvidenceScore, ResumeSelectionDecision


class SummaryBriefTheme(StrictModel):
    """Structured summary theme for later composition, not generated prose."""

    theme: NonEmptyStr
    supporting_keywords: list[NonEmptyStr] = Field(default_factory=list)


class RankingRequest(StrictModel):
    """Legacy Phase 2 request contract preserved for current API and tests."""

    job_analysis: JobAnalysisInput
    source_profile: CandidateProfileInput
    candidate_evidence: list[EvidenceUnit] = Field(default_factory=list)

    @field_validator("job_analysis", mode="before")
    @classmethod
    def coerce_job_analysis(cls, value: object) -> object:
        """Accept the existing NormalizedJobAnalysis model as a Phase 2 input."""

        if isinstance(value, NormalizedJobAnalysis):
            return value.model_dump()
        return value

    @field_validator("source_profile", mode="before")
    @classmethod
    def coerce_source_profile(cls, value: object) -> object:
        """Accept the existing MasterProfile model as a Phase 2 input."""

        if isinstance(value, MasterProfile):
            return value.model_dump()
        return value


class RankingResponse(StrictModel):
    """Legacy Phase 2 response contract preserved while Phase2SelectionResult lands."""

    ranked_experiences: list[ScoredEvidenceUnit] = Field(default_factory=list)
    ranked_projects: list[ScoredEvidenceUnit] = Field(default_factory=list)
    ranked_certifications: list[ScoredEvidenceUnit] = Field(default_factory=list)
    atomic_evidence_scores: list[EvidenceScore] = Field(default_factory=list)
    resume_selection_decision: ResumeSelectionDecision | None = None
    skills_to_highlight: list[NonEmptyStr] = Field(default_factory=list)
    headline_suggestion: NonEmptyStr | None = None
    summary_brief_themes: list[SummaryBriefTheme] = Field(default_factory=list)


CandidateEvidenceItem = EvidenceUnit
RankedItem = ScoredEvidenceUnit

__all__ = [
    "CandidateEvidenceItem",
    "CandidateProfileInput",
    "EvidenceUnit",
    "JobAnalysisInput",
    "Phase2SelectionResult",
    "RankingExplanation",
    "RankedItem",
    "RankingRequest",
    "RankingResponse",
    "ScoredEvidenceUnit",
    "SummaryBriefTheme",
]
