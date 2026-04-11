"""Typed schemas for Phase 7 evaluation case definitions.

This module defines the canonical schema for all evaluation packs:
- jd_parse: job-description parsing regression cases
- selection: ranking and evidence-selection regression cases
- end_to_end: full real pipeline evaluation cases
- red_team: adversarial, abuse, and failure-oriented cases

The schema is designed to be practical for human review. Authors should be able to
write cases in YAML or JSON without deep familiarity with the code.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from ..models import NonEmptyStr, ScoreValue, StrictModel


class RoleFamily(StrEnum):
    """Normalized role family tags for categorizing evaluation cases."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    DATA = "data"
    ML = "ml"
    PLATFORM = "platform"
    DEV_OPS = "devops"
    PRODUCT = "product"
    DESIGN = "design"
    SECURITY = "security"
    MANAGEMENT = "management"
    OTHER = "other"


class SeniorityLevel(StrEnum):
    """Target seniority level for the evaluation case."""

    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    VP = "vp"


class EdgeCaseType(StrEnum):
    """Characterizes edge-case properties for targeted regression testing."""

    NOISY_JD = "noisy_jd"
    SPARSE_PROFILE = "sparse_profile"
    AMBIGUOUS_TITLE = "ambiguous_title"
    CONTRADICTORY_SIGNALS = "contradictory_signals"
    GENERIC_JD = "generic_jd"
    NO_LLM_ACCESS = "no_llm_access"
    EMPTY_PROFILE = "empty_profile"
    MALFORMED_INPUT = "malformed_input"
    NONE = "none"


class ExpectationType(StrEnum):
    """Defines how expected outputs should be interpreted."""

    MUST_INCLUDE = "must_include"
    MUST_NOT_INCLUDE = "must_not_include"
    PREFER_INCLUDE = "prefer_include"
    ACCEPTABLE_ALTERNATIVE = "acceptable_alternative"


class ExpectationMatchMode(StrEnum):
    """Controls matching behavior for expectations."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    SUBSET = "subset"
    SUPERSET = "superset"


class Expectation(StrictModel):
    """One expected output for evaluation scoring.

    Supports four modes suitable for human review:
    - must_include: The output MUST contain this value (fail if missing)
    - must_not_include: The output MUST NOT contain this value (fail if present)
    - prefer_include: The output should contain this value (partial credit)
    - acceptable_alternative: Multiple valid answers exist (flexible matching)
    """

    type: ExpectationType = Field(description="How this expectation should be scored.")
    value: str = Field(description="The expected value or pattern.")
    match_mode: ExpectationMatchMode = Field(
        default=ExpectationMatchMode.EXACT,
        description="Matching behavior for the value.",
    )
    weight: float = Field(
        ge=0.0,
        le=1.0,
        default=1.0,
        description="Relative importance for scoring.",
    )
    reason: str | None = Field(
        default=None,
        description="Human-readable explanation for this expectation.",
    )
    alternative_group: str | None = Field(
        default=None,
        description=(
            "Optional group key for acceptable alternatives. Expectations that share "
            "this key are treated as one any-of expectation bucket."
        ),
    )


class JobDescriptionInput(StrictModel):
    """The job description text used as input for evaluation."""

    raw_text: str = Field(description="Raw JD text as it would be passed to Phase 1.")
    source: str | None = Field(
        default=None,
        description="Origin (e.g., 'linkedin', 'manual', 'generated').",
    )
    is_noisy: bool = Field(
        default=False,
        description="Whether this JD has quality issues.",
    )


class ProfileInputReference(StrictModel):
    """Reference to a profile file for selection/end-to-end cases.

    Uses a relative path from the evaluation pack root. The loader
    resolves this against the pack's base directory.
    """

    path: str = Field(description="Relative path to the profile JSON file.")
    summary: str | None = Field(
        default=None,
        description="Brief description of the profile contents.",
    )


class Phase1ParseExpectations(StrictModel):
    """Expected Phase 1 (JD parsing) outputs for this case."""

    expected_job_title: str | None = Field(
        default=None,
        description="Expected parsed job title.",
    )
    expected_role_family: RoleFamily | None = Field(
        default=None,
        description="Expected parsed role family.",
    )
    expected_seniority: SeniorityLevel | None = Field(
        default=None,
        description="Expected parsed seniority level.",
    )
    expected_skills: list[Expectation] = Field(
        default_factory=list,
        description="Expected skills that should be extracted.",
    )
    min_quality_score: float = Field(
        ge=0.0,
        le=1.0,
        default=0.5,
        description="Minimum acceptable JD quality score.",
    )
    min_parser_confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.5,
        description="Minimum acceptable parser confidence.",
    )


class SelectionExpectations(StrictModel):
    """Expected Phase 2 (selection) outputs for this case."""

    experience_expectations: list[Expectation] = Field(
        default_factory=list,
        description="Experience entries expected to be selected or omitted.",
    )
    project_expectations: list[Expectation] = Field(
        default_factory=list,
        description="Project entries expected to be selected or omitted.",
    )
    bullet_expectations: list[Expectation] = Field(
        default_factory=list,
        description="Bullets expected to survive or be omitted.",
    )
    skill_expectations: list[Expectation] = Field(
        default_factory=list,
        description="Skills expected to be highlighted or omitted.",
    )
    expected_selected_skills: list[Expectation] = Field(
        default_factory=list,
        description="Deprecated alias for skill_expectations.",
    )
    expected_highlighted_experiences: list[Expectation] = Field(
        default_factory=list,
        description="Deprecated alias for experience_expectations.",
    )
    expected_omitted_items: list[Expectation] = Field(
        default_factory=list,
        description="Deprecated alias for must-exclude expectations across categories.",
    )
    min_selection_relevance: float = Field(
        ge=0.0,
        le=1.0,
        default=0.6,
        description="Minimum acceptable relevance score.",
    )
    min_bullet_count: int = Field(
        default=3,
        ge=0,
        description="Minimum number of bullets that should survive final selection.",
    )
    min_experience_precision: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable experience precision for passing.",
    )
    min_experience_recall: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable experience recall for passing.",
    )
    min_project_precision: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable project precision for passing.",
    )
    min_project_recall: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable project recall for passing.",
    )
    min_bullet_precision: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable bullet precision for passing.",
    )
    min_bullet_recall: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable bullet recall for passing.",
    )
    min_skill_correctness: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable skill highlight correctness for passing.",
    )
    min_diversity_balance: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable breadth / balance sanity score.",
    )

    @model_validator(mode="after")
    def hydrate_legacy_selection_fields(self) -> "SelectionExpectations":
        experience_expectations = list(self.experience_expectations)
        project_expectations = list(self.project_expectations)
        bullet_expectations = list(self.bullet_expectations)
        skill_expectations = list(self.skill_expectations)

        if self.expected_highlighted_experiences:
            experience_expectations.extend(self.expected_highlighted_experiences)
        if self.expected_selected_skills:
            skill_expectations.extend(self.expected_selected_skills)

        if self.expected_omitted_items:
            for expectation in self.expected_omitted_items:
                if expectation.type != ExpectationType.MUST_NOT_INCLUDE:
                    continue
                experience_expectations.append(expectation)
                project_expectations.append(expectation)
                bullet_expectations.append(expectation)
                skill_expectations.append(expectation)

        object.__setattr__(self, "experience_expectations", experience_expectations)
        object.__setattr__(self, "project_expectations", project_expectations)
        object.__setattr__(self, "bullet_expectations", bullet_expectations)
        object.__setattr__(self, "skill_expectations", skill_expectations)
        return self


class EndToEndExpectations(StrictModel):
    """Expected end-to-end pipeline outputs for this case."""

    expected_sections: list[Expectation] = Field(
        default_factory=list,
        description="Sections expected in the final resume.",
    )
    expected_headline: Expectation | None = Field(
        default=None,
        description="Expected resume headline.",
    )
    expected_summary: Expectation | None = Field(
        default=None,
        description="Expected professional summary.",
    )
    min_quality_score: float = Field(
        ge=0.0,
        le=1.0,
        default=0.6,
        description="Minimum acceptable generation quality.",
    )
    max_hallucination_rate: float = Field(
        ge=0.0,
        le=1.0,
        default=0.1,
        description="Maximum acceptable hallucination rate.",
    )


class ScoringWeights(StrictModel):
    """Custom scoring weights for this evaluation case.

    These override defaults when specified. Useful for targeting specific
    evaluation dimensions.
    """

    parse_accuracy: float = Field(
        ge=0.0,
        le=1.0,
        default=0.4,
        description="Weight for parsing accuracy.",
    )
    selection_relevance: float = Field(
        ge=0.0,
        le=1.0,
        default=0.3,
        description="Weight for selection relevance.",
    )
    generation_quality: float = Field(
        ge=0.0,
        le=1.0,
        default=0.3,
        description="Weight for generation quality.",
    )


class EvaluationCase(StrictModel):
    """One complete evaluation case definition.

    This is the primary schema that humans author. It should be
    read naturally without needing to understand the code.
    """

    case_id: str = Field(description="Unique identifier for this case.")
    description: str = Field(
        description="Human-readable description of what this case tests."
    )
    pack_type: str = Field(
        description="Which pack this case belongs to (jd_parse, selection, end_to_end, red_team)."
    )

    job_description: JobDescriptionInput | None = Field(
        default=None,
        description="JD input for parse or end-to-end cases.",
    )
    profile: ProfileInputReference | None = Field(
        default=None,
        description="Profile input for selection or end-to-end cases.",
    )

    phase1_expectations: Phase1ParseExpectations | None = Field(
        default=None,
        description="Expected Phase 1 outputs.",
    )
    selection_expectations: SelectionExpectations | None = Field(
        default=None,
        description="Expected Phase 2 outputs.",
    )
    end_to_end_expectations: EndToEndExpectations | None = Field(
        default=None,
        description="Expected end-to-end outputs.",
    )

    scoring_weights: ScoringWeights | None = Field(
        default=None,
        description="Custom scoring weights.",
    )

    tags: list[str] = Field(
        default_factory=list,
        description="Categorization tags (role_family, seniority, edge_case_type, etc.).",
    )

    actual_selection: dict[str, Any] | None = Field(
        default=None,
        description="Actual selection output for scoring (used by selection/end_to_end packs).",
    )

    notes: list[str] = Field(
        default_factory=list,
        description="Author notes for future maintainers.",
    )

    @field_validator("tags")
    @classmethod
    def validate_unique_tags(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in value:
            key = item.lower().strip()
            if key in seen:
                duplicates.add(item)
            seen.add(key)
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"tags must be unique: {duplicate_list}")
        return value

    @model_validator(mode="after")
    def validate_case_completeness(self) -> "EvaluationCase":
        if self.pack_type == "jd_parse":
            if self.job_description is None:
                raise ValueError("jd_parse cases must have job_description")
            if self.phase1_expectations is None:
                raise ValueError("jd_parse cases must have phase1_expectations")
        elif self.pack_type == "selection":
            if self.profile is None:
                raise ValueError("selection cases must have profile")
            if self.phase1_expectations is None:
                raise ValueError("selection cases need phase1_expectations (JD)")
            if self.selection_expectations is None:
                raise ValueError("selection cases must have selection_expectations")
        elif self.pack_type == "end_to_end":
            if self.job_description is None:
                raise ValueError("end_to_end cases must have job_description")
            if self.profile is None:
                raise ValueError("end_to_end cases must have profile")
            if self.end_to_end_expectations is None:
                raise ValueError("end_to_end cases must have end_to_end_expectations")
        elif self.pack_type == "red_team":
            pass
        return self


class EvaluationPack(StrictModel):
    """A collection of evaluation cases that share a common fixture pack.

    Packs are the unit of loading for CI and local testing.
    """

    pack_id: str = Field(description="Unique identifier for this pack.")
    pack_type: str = Field(description="Which pack type (jd_parse, selection, etc.).")
    description: str = Field(
        description="Human-readable description of what this pack tests."
    )
    version: str = Field(
        default="1.0.0",
        description="Schema version for this pack.",
    )

    templates: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Reusable templates that cases can extend.",
    )
    cases: list[EvaluationCase] = Field(
        default_factory=list,
        description="The evaluation cases in this pack.",
    )

    @field_validator("cases")
    @classmethod
    def validate_unique_case_ids(
        cls, value: list[EvaluationCase]
    ) -> list[EvaluationCase]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for case in value:
            if case.case_id in seen:
                duplicates.add(case.case_id)
            seen.add(case.case_id)
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"case_ids must be unique within pack: {duplicate_list}")
        return value


class EvaluationManifest(StrictModel):
    """Root manifest referencing all evaluation packs."""

    manifest_version: str = Field(default="1.0.0")
    description: str = Field(default="Phase 7 evaluation manifest for all packs.")
    packs: list[EvaluationPack] = Field(default_factory=list)
