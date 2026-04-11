"""Deterministic intermediate artifacts for Phase 1 job-description parsing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .models import NonEmptyStr, ScoreValue, StrictModel


class JDSectionKind(StrEnum):
    """Canonical section buckets detected from messy job descriptions."""

    HEADER = "header"
    SUMMARY = "summary"
    RESPONSIBILITIES = "responsibilities"
    REQUIREMENTS = "requirements"
    PREFERRED = "preferred"
    QUALIFICATIONS = "qualifications"
    BENEFITS = "benefits"
    COMPANY = "company"
    OTHER = "other"


class RequirementStrength(StrEnum):
    """Strength of a requirement marker detected deterministically."""

    MUST_HAVE = "must_have"
    PREFERRED = "preferred"
    BONUS = "bonus"


class DeterministicFindingType(StrEnum):
    """Typed deterministic finding categories emitted before LLM enrichment."""

    TITLE = "title"
    COMPANY_NAME = "company_name"
    YEARS_EXPERIENCE = "years_experience"
    REQUIREMENT_MARKER = "requirement_marker"
    TOOL_PLATFORM = "tool_platform"
    REPEATED_KEYWORD = "repeated_keyword"
    ACTION_VERB = "action_verb"
    WORK_MODEL = "work_model"
    LEADERSHIP = "leadership"
    SCOPE = "scope"
    EDUCATION = "education"
    DOMAIN = "domain"


class DetectedSection(StrictModel):
    """A contiguous chunk of JD text grouped under one inferred section label."""

    id: NonEmptyStr
    kind: JDSectionKind
    heading: NonEmptyStr | None = Field(
        default=None,
        description="Original heading line when one was detected.",
    )
    line_start: int = Field(ge=0)
    line_end: int = Field(ge=0)
    text: NonEmptyStr = Field(
        description="Normalized section text preserving original content order."
    )
    confidence: ScoreValue = Field(
        description="Confidence that the section label was inferred correctly."
    )


class DeterministicFinding(StrictModel):
    """One inspectable deterministic extraction with evidence and confidence."""

    finding_type: DeterministicFindingType
    value: NonEmptyStr
    canonical_value: NonEmptyStr
    source_text: NonEmptyStr
    line_index: int = Field(ge=0)
    section_id: NonEmptyStr | None = None
    confidence: ScoreValue
    notes: list[NonEmptyStr] = Field(default_factory=list)


class YearsExperienceFinding(StrictModel):
    """One explicit years-of-experience mention with directional semantics."""

    years: int = Field(ge=0, le=50)
    source_text: NonEmptyStr
    line_index: int = Field(ge=0)
    section_id: NonEmptyStr | None = None
    minimum_like: bool = Field(
        default=True,
        description="Whether the wording indicates a minimum requirement rather than a preference.",
    )
    confidence: ScoreValue


class RequirementMarkerFinding(StrictModel):
    """A requirement line classified as must-have, preferred, or bonus."""

    strength: RequirementStrength
    text: NonEmptyStr
    canonical_text: NonEmptyStr
    line_index: int = Field(ge=0)
    section_id: NonEmptyStr | None = None
    marker_phrase: NonEmptyStr
    confidence: ScoreValue
    extracted_keywords: list[NonEmptyStr] = Field(default_factory=list)


class KeywordFrequencyFinding(StrictModel):
    """A repeated normalized keyword extracted from the whole JD body."""

    keyword: NonEmptyStr
    count: int = Field(ge=2)
    representative_texts: list[NonEmptyStr] = Field(default_factory=list)
    confidence: ScoreValue


class DeterministicJobDescriptionExtraction(StrictModel):
    """Full deterministic extraction artifact produced before any LLM enrichment."""

    raw_job_text: NonEmptyStr
    normalized_lines: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Normalized non-empty lines preserved in original order.",
    )
    sections: list[DetectedSection] = Field(default_factory=list)
    title_candidates: list[DeterministicFinding] = Field(default_factory=list)
    company_name_candidates: list[DeterministicFinding] = Field(default_factory=list)
    years_experience_findings: list[YearsExperienceFinding] = Field(default_factory=list)
    requirement_markers: list[RequirementMarkerFinding] = Field(default_factory=list)
    tool_platform_findings: list[DeterministicFinding] = Field(default_factory=list)
    repeated_keyword_findings: list[KeywordFrequencyFinding] = Field(default_factory=list)
    action_verb_findings: list[DeterministicFinding] = Field(default_factory=list)
    work_model_findings: list[DeterministicFinding] = Field(default_factory=list)
    leadership_findings: list[DeterministicFinding] = Field(default_factory=list)
    scope_indicator_findings: list[DeterministicFinding] = Field(default_factory=list)
    education_requirement_findings: list[DeterministicFinding] = Field(default_factory=list)
    domain_findings: list[DeterministicFinding] = Field(default_factory=list)
    extraction_notes: list[NonEmptyStr] = Field(default_factory=list)
