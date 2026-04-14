"""Pydantic models for the Phase 1 job understanding engine."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from .models import (
    NonEmptyStr,
    OptionalUrl,
    RoleType,
    SeniorityLevel,
    StrictModel,
)


class SkillPriority(StrEnum):
    CORE = "core"
    IMPORTANT = "important"
    NICE_TO_HAVE = "nice_to_have"


class RawJobDescriptionRequest(StrictModel):
    """Raw Phase 1 backend input before any AI parsing or normalization."""

    job_description_text: NonEmptyStr
    job_posting_url: OptionalUrl = None


class ParsedJobAnalysisResponse(StrictModel):
    """Raw Phase 1 AI Call 1 response preserved before internal normalization."""

    technical_skills: list[NonEmptyStr] = Field(default_factory=list)
    soft_skills: list[NonEmptyStr] = Field(default_factory=list)
    seniority_level: NonEmptyStr | None = None
    role_type: NonEmptyStr | None = None
    industry_domain: NonEmptyStr | None = None
    key_action_verbs: list[NonEmptyStr] = Field(default_factory=list)
    must_have_requirements: list[NonEmptyStr] = Field(default_factory=list)
    nice_to_have_requirements: list[NonEmptyStr] = Field(default_factory=list)
    company_culture_signals: list[NonEmptyStr] = Field(default_factory=list)


class NormalizedSkillRequirement(StrictModel):
    """Canonical normalized skill requirement for downstream Phase 1 consumers."""

    skill_name: NonEmptyStr
    priority: SkillPriority
    evidence: NonEmptyStr | None = None


class NormalizedJobAnalysis(StrictModel):
    """Canonical internal Phase 1 contract for normalized job understanding."""

    role_type: RoleType | None = None
    seniority_level: SeniorityLevel | None = None
    industry_domain: NonEmptyStr | None = None
    technical_skills: list[NonEmptyStr] = Field(default_factory=list)
    soft_skills: list[NonEmptyStr] = Field(default_factory=list)
    key_action_verbs: list[NonEmptyStr] = Field(default_factory=list)
    must_have_requirements: list[NonEmptyStr] = Field(default_factory=list)
    nice_to_have_requirements: list[NonEmptyStr] = Field(default_factory=list)
    company_culture_signals: list[NonEmptyStr] = Field(default_factory=list)
    years_experience_required: int | None = Field(default=None, ge=0, le=50)
    prioritized_skills: list[NormalizedSkillRequirement] = Field(default_factory=list)

    @field_validator("prioritized_skills")
    @classmethod
    def validate_unique_skill_names(
        cls, value: list[NormalizedSkillRequirement]
    ) -> list[NormalizedSkillRequirement]:
        seen: set[str] = set()
        duplicates: set[str] = set()

        for item in value:
            normalized_name = item.skill_name.casefold()
            if normalized_name in seen:
                duplicates.add(item.skill_name)
            seen.add(normalized_name)

        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(
                f"prioritized_skills must not contain duplicate skill names: {duplicate_list}"
            )

        return value
