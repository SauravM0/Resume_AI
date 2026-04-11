"""Strongly typed Phase 1 job-description understanding contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from .models import NonEmptyStr, ScoreValue, StrictModel
from .phase1_deterministic_models import DeterministicJobDescriptionExtraction
from .phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode


class JobSeniorityLevel(StrEnum):
    """Target seniority level for the job itself.

    The enum stays level-oriented and does not absorb org-mode concepts such as
    manager or director.
    """

    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    EXECUTIVE = "executive"


class EducationLevel(StrEnum):
    """Common education thresholds referenced by job descriptions."""

    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    DOCTORATE = "doctorate"
    BOOTCAMP = "bootcamp"
    CERTIFICATION = "certification"


class LeadershipScope(StrEnum):
    """Canonical leadership expectation levels for the target role."""

    NONE = "none"
    MENTORSHIP = "mentorship"
    TECHNICAL_LEADERSHIP = "technical_leadership"
    TEAM_LEADERSHIP = "team_leadership"
    PEOPLE_MANAGEMENT = "people_management"
    EXECUTIVE_LEADERSHIP = "executive_leadership"


class DeliveryScopeLevel(StrEnum):
    """Canonical delivery-scope levels inferred from the job description."""

    TASK = "task"
    FEATURE = "feature"
    SYSTEM = "system"
    PLATFORM = "platform"
    MULTI_TEAM = "multi_team"
    ORGANIZATION = "organization"


class RequirementConfidenceItemType(StrEnum):
    """Typed item categories that can carry an item-level extraction confidence."""

    REQUIREMENT_MARKER = "requirement_marker"
    JOB_TITLE = "job_title"
    COMPANY_NAME = "company_name"
    FUNCTIONAL_ROLE_FAMILY = "functional_role_family"
    ORGANIZATIONAL_ROLE_MODE = "organizational_role_mode"
    SENIORITY_LEVEL = "seniority_level"
    RESPONSIBILITY_CLUSTER = "primary_responsibility_cluster"
    MUST_HAVE_SKILL = "must_have_skill"
    NICE_TO_HAVE_SKILL = "nice_to_have_skill"
    REQUIRED_TOOL_PLATFORM = "required_tool_platform"
    REQUIRED_DOMAIN = "required_domain"
    MUST_HAVE_BEHAVIOR = "must_have_behavior"
    BUSINESS_GOAL_SIGNAL = "business_goal_signal"
    IMPACT_SIGNAL = "impact_signal"
    EDUCATION_REQUIREMENT = "education_requirement"
    LEADERSHIP_REQUIREMENT = "leadership_requirement"
    DELIVERY_SCOPE_REQUIREMENT = "delivery_scope_requirement"
    CONSTRAINT_SIGNAL = "constraint_signal"
    WORK_MODEL_SIGNAL = "work_model_signal"
    INDUSTRY_DOMAIN = "industry_domain"
    KEY_ACTION_VERB = "key_action_verb"


class PrioritizedRequirementTier(StrEnum):
    """Priority buckets for downstream requirement ordering."""

    CRITICAL = "critical"
    MUST_HAVE = "must_have"
    IMPORTANT = "important"
    NICE_TO_HAVE = "nice_to_have"


class BreadthPreference(StrEnum):
    """Whether the target role rewards range or depth more strongly."""

    BREADTH = "breadth"
    BALANCED = "balanced"
    SPECIALIZATION = "specialization"
    UNKNOWN = "unknown"


class PersuasiveEvidenceType(StrEnum):
    """Evidence shapes most likely to persuade the recruiter for this role."""

    ARCHITECTURE_DECISIONS = "architecture_decisions"
    EXECUTION_DELIVERY = "execution_delivery"
    CROSS_FUNCTIONAL_LEADERSHIP = "cross_functional_leadership"
    PEOPLE_LEADERSHIP = "people_leadership"
    DOMAIN_DEPTH = "domain_depth"
    RELIABILITY_SCALE = "reliability_scale"
    PRODUCT_PARTNERSHIP = "product_partnership"
    GENERALIST_RANGE = "generalist_range"


class IntentEmphasisProfile(StrictModel):
    """Relative recruiter emphasis across core candidate-story dimensions."""

    architecture: ScoreValue = Field(
        default=0.0,
        description="How strongly the JD emphasizes system design, platform design, or architecture decisions.",
    )
    execution: ScoreValue = Field(
        default=0.0,
        description="How strongly the JD emphasizes shipping, delivery, implementation, and concrete execution.",
    )
    collaboration: ScoreValue = Field(
        default=0.0,
        description="How strongly the JD emphasizes cross-functional partnership, stakeholders, or team coordination.",
    )
    leadership: ScoreValue = Field(
        default=0.0,
        description="How strongly the JD emphasizes mentoring, technical leadership, or people leadership.",
    )


class RecruiterIntentProfile(StrictModel):
    """Downstream-usable model of the candidate story the recruiter is likely seeking."""

    likely_success_shape: NonEmptyStr | None = Field(
        default=None,
        description="Concise statement of what a successful candidate is most likely expected to demonstrate.",
    )
    emphasis_profile: IntentEmphasisProfile = Field(
        default_factory=IntentEmphasisProfile,
        description="Relative emphasis on architecture, execution, collaboration, and leadership.",
    )
    persuasive_evidence_types: list[PersuasiveEvidenceType] = Field(
        default_factory=list,
        description="Canonical evidence categories most likely to persuade the recruiter.",
    )
    pace_environment_signals: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Signals about operating pace or environment, such as startup pace or structured enterprise expectations.",
    )
    domain_specific_emphasis: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Specific domain themes that should shape resume selection or bullet choice.",
    )
    breadth_preference: BreadthPreference = Field(
        default=BreadthPreference.UNKNOWN,
        description="Whether the role appears to prefer breadth, specialization, or a balanced profile.",
    )
    confidence: ScoreValue = Field(
        default=0.0,
        description="Confidence in the recruiter-intent interpretation.",
    )
    notes: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Short ambiguity or inference notes for downstream planning and verification.",
    )

    @field_validator("pace_environment_signals", "domain_specific_emphasis", "notes")
    @classmethod
    def validate_unique_lists(cls, value: list[str]) -> list[str]:
        return _validate_unique_strings(value)

    @field_validator("persuasive_evidence_types")
    @classmethod
    def validate_unique_evidence_types(
        cls, value: list[PersuasiveEvidenceType]
    ) -> list[PersuasiveEvidenceType]:
        seen: set[PersuasiveEvidenceType] = set()
        result: list[PersuasiveEvidenceType] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result


class JDQualityBreakdown(StrictModel):
    """Deterministic quality scores describing how trustworthy and usable the JD is."""

    completeness_score: ScoreValue = Field(
        default=0.0,
        description="How much of the expected job-description structure is present.",
    )
    specificity_score: ScoreValue = Field(
        default=0.0,
        description="How concrete and implementation-usable the JD wording is.",
    )
    ambiguity_score: ScoreValue = Field(
        default=0.0,
        description="How much the JD leaves room for multiple incompatible interpretations. Higher means more ambiguous.",
    )
    consistency_score: ScoreValue = Field(
        default=0.0,
        description="How internally consistent the JD signals are. Higher means more consistent.",
    )
    downstream_risk_score: ScoreValue = Field(
        default=0.0,
        description="How risky it is to over-trust this JD downstream. Higher means more downstream caution is needed.",
    )
    notes: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Concise reasons behind the quality scores for debugging and downstream caution handling.",
    )

    @field_validator("notes")
    @classmethod
    def validate_unique_notes(cls, value: list[str]) -> list[str]:
        return _validate_unique_strings(value)


class EducationRequirement(StrictModel):
    """Structured education or certification expectations from the JD."""

    minimum_level: EducationLevel | None = Field(
        default=None,
        description="Minimum education threshold explicitly required by the job description.",
    )
    preferred_level: EducationLevel | None = Field(
        default=None,
        description="Preferred, but not strictly required, education threshold.",
    )
    fields_of_study: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Relevant academic subjects or degree focus areas explicitly mentioned.",
    )
    certifications: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Certifications called out as required or preferred.",
    )
    required: bool | None = Field(
        default=None,
        description="Whether education is clearly stated as required rather than optional.",
    )
    notes: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Free-text qualifiers or caveats that do not fit the structured fields above.",
    )

    @field_validator("fields_of_study", "certifications", "notes")
    @classmethod
    def validate_unique_lists(cls, value: list[str]) -> list[str]:
        return _validate_unique_strings(value)


class LeadershipRequirement(StrictModel):
    """Structured leadership expectation for the target role."""

    scope: LeadershipScope | None = Field(
        default=None,
        description="Canonical leadership level required or strongly implied by the JD.",
    )
    people_management_required: bool | None = Field(
        default=None,
        description="Whether direct people-management responsibility is explicitly required.",
    )
    mentoring_expected: bool | None = Field(
        default=None,
        description="Whether mentoring or coaching is expected even if people management is absent.",
    )
    strategy_ownership_expected: bool | None = Field(
        default=None,
        description="Whether the role is expected to define direction, roadmap, or strategy.",
    )
    notes: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Leadership qualifiers that should remain visible to downstream consumers.",
    )

    @field_validator("notes")
    @classmethod
    def validate_unique_notes(cls, value: list[str]) -> list[str]:
        return _validate_unique_strings(value)


class DeliveryScopeRequirement(StrictModel):
    """Structured description of the level of delivery ownership expected."""

    scope_level: DeliveryScopeLevel | None = Field(
        default=None,
        description="Canonical scope level such as feature, system, platform, or multi-team.",
    )
    cross_functional_coordination_required: bool | None = Field(
        default=None,
        description="Whether the role must coordinate across teams, functions, or stakeholders.",
    )
    roadmap_ownership_expected: bool | None = Field(
        default=None,
        description="Whether roadmap, planning, or prioritization ownership is expected.",
    )
    notes: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Free-text scope qualifiers preserved for later planning or verification.",
    )

    @field_validator("notes")
    @classmethod
    def validate_unique_notes(cls, value: list[str]) -> list[str]:
        return _validate_unique_strings(value)


class RequirementConfidenceItem(StrictModel):
    """Confidence attached to one extracted job-understanding item."""

    item_type: RequirementConfidenceItemType = Field(
        description="Typed category of the extracted value."
    )
    item_value: NonEmptyStr = Field(
        description="Canonical extracted value whose confidence is being reported."
    )
    confidence: ScoreValue = Field(
        description="Bounded confidence score in the extraction of this specific value."
    )
    notes: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Optional short notes explaining ambiguity or parser caveats for this item.",
    )

    @field_validator("notes")
    @classmethod
    def validate_unique_notes(cls, value: list[str]) -> list[str]:
        return _validate_unique_strings(value)


class PrioritizedRequirement(StrictModel):
    """One requirement ranked for downstream planning and content selection."""

    requirement_text: NonEmptyStr = Field(
        description="Human-readable requirement text preserved for downstream ranking or planning."
    )
    requirement_type: RequirementConfidenceItemType = Field(
        description="Typed category of the requirement."
    )
    priority_rank: int = Field(
        ge=1,
        description="Stable 1-based rank where lower numbers indicate higher downstream priority.",
    )
    priority_tier: PrioritizedRequirementTier = Field(
        description="Priority bucket used by downstream stages."
    )
    confidence: ScoreValue = Field(
        description="Confidence that this priority assignment is accurate."
    )
    rationale: NonEmptyStr | None = Field(
        default=None,
        description="Short explanation of why the item received its rank or tier.",
    )


class Phase1JobAnalysis(StrictModel):
    """Rich Phase 1 output contract for parsed job-description understanding."""

    raw_job_text: NonEmptyStr = Field(
        description="Exact raw job-description text used as the Phase 1 source document."
    )
    job_title: NonEmptyStr | None = Field(
        default=None,
        description="Normalized target job title when it is explicit enough to trust.",
    )
    company_name: NonEmptyStr | None = Field(
        default=None,
        description="Hiring company or organization name when present in the JD.",
    )
    functional_role_family: FunctionalRoleFamily = Field(
        default=FunctionalRoleFamily.OTHER,
        description="Technical or functional family such as backend, platform, data, product, or design.",
    )
    organizational_role_mode: OrganizationalRoleMode = Field(
        default=OrganizationalRoleMode.UNKNOWN,
        description="How the role sits in the organization, kept separate from technical family.",
    )
    seniority_level: JobSeniorityLevel | None = Field(
        default=None,
        description="Target seniority level for the role itself.",
    )
    primary_responsibility_clusters: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Top responsibility themes grouped into concise downstream-usable clusters.",
    )
    must_have_skills: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Skills that the JD clearly treats as required.",
    )
    nice_to_have_skills: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Skills the JD treats as preferred, bonus, or otherwise non-blocking.",
    )
    required_tools_platforms: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Named tools, platforms, clouds, frameworks, or systems expected for the role.",
    )
    required_domains: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Domain or industry specialties explicitly required by the JD.",
    )
    must_have_behaviors: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Behavioral expectations that appear mandatory, such as ownership or collaboration style.",
    )
    business_goal_signals: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Signals about business outcomes the role is expected to support.",
    )
    impact_signals: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Signals about scale, KPI movement, reliability, revenue, growth, or other impact outcomes.",
    )
    recruiter_intent: RecruiterIntentProfile = Field(
        default_factory=RecruiterIntentProfile,
        description="Structured recruiter-intent interpretation used by later ranking and section-planning phases.",
    )
    years_experience_requirement: int | None = Field(
        default=None,
        ge=0,
        le=50,
        description="Minimum explicit years-of-experience requirement when confidently extractable.",
    )
    education_requirement: EducationRequirement = Field(
        default_factory=EducationRequirement,
        description="Structured education and certification expectation block.",
    )
    leadership_requirement: LeadershipRequirement = Field(
        default_factory=LeadershipRequirement,
        description="Structured leadership expectation block.",
    )
    delivery_scope_requirement: DeliveryScopeRequirement = Field(
        default_factory=DeliveryScopeRequirement,
        description="Structured delivery-scope expectation block.",
    )
    constraint_signals: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Hard constraints such as clearance, work authorization, travel, or location restrictions.",
    )
    work_model_signals: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Signals about remote, hybrid, onsite, travel, or schedule expectations.",
    )
    industry_domain: NonEmptyStr | None = Field(
        default=None,
        description="Primary industry or business domain when one domain is dominant enough to trust.",
    )
    key_action_verbs: list[NonEmptyStr] = Field(
        default_factory=list,
        description="High-signal verbs that describe the target work or expected behavior.",
    )
    jd_quality_breakdown: JDQualityBreakdown = Field(
        default_factory=JDQualityBreakdown,
        description="Deterministic JD-quality sub-scores that explain why the overall quality score is high or low.",
    )
    jd_quality_score: ScoreValue = Field(
        description="Quality score for the job description itself as parsing input."
    )
    parser_confidence: ScoreValue = Field(
        description="Overall confidence in the structured Phase 1 output."
    )
    requirement_confidence_by_item: list[RequirementConfidenceItem] = Field(
        default_factory=list,
        description="Item-level confidence records for extracted fields that downstream phases may weight differently.",
    )
    extraction_notes: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Explicit parser caveats or ambiguity notes preserved for debugging and later verification.",
    )
    normalized_keywords: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Stable normalized keywords used as a broad retrieval and ranking surface.",
    )
    prioritized_requirements: list[PrioritizedRequirement] = Field(
        default_factory=list,
        description="Requirement list already ordered for downstream ranking, planning, and summary construction.",
    )

    @field_validator(
        "primary_responsibility_clusters",
        "must_have_skills",
        "nice_to_have_skills",
        "required_tools_platforms",
        "required_domains",
        "must_have_behaviors",
        "business_goal_signals",
        "impact_signals",
        "constraint_signals",
        "work_model_signals",
        "key_action_verbs",
        "extraction_notes",
        "normalized_keywords",
    )
    @classmethod
    def validate_unique_lists(cls, value: list[str]) -> list[str]:
        return _validate_unique_strings(value)

    @field_validator("requirement_confidence_by_item")
    @classmethod
    def validate_unique_confidence_items(
        cls, value: list[RequirementConfidenceItem]
    ) -> list[RequirementConfidenceItem]:
        seen: set[tuple[str, str]] = set()
        duplicates: list[str] = []
        for item in value:
            key = (item.item_type.value, _fold_key(item.item_value))
            if key in seen:
                duplicates.append(f"{item.item_type.value}:{item.item_value}")
                continue
            seen.add(key)
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(
                "requirement_confidence_by_item must not contain duplicates: "
                f"{duplicate_list}"
            )
        return value

    @field_validator("prioritized_requirements")
    @classmethod
    def validate_prioritized_requirements(
        cls, value: list[PrioritizedRequirement]
    ) -> list[PrioritizedRequirement]:
        seen_ranks: set[int] = set()
        seen_items: set[tuple[str, str]] = set()
        duplicate_ranks: set[int] = set()
        duplicate_items: set[str] = set()
        for item in value:
            if item.priority_rank in seen_ranks:
                duplicate_ranks.add(item.priority_rank)
            seen_ranks.add(item.priority_rank)

            item_key = (item.requirement_type.value, _fold_key(item.requirement_text))
            if item_key in seen_items:
                duplicate_items.add(
                    f"{item.requirement_type.value}:{item.requirement_text}"
                )
            seen_items.add(item_key)

        if duplicate_ranks:
            raise ValueError(
                "prioritized_requirements must use unique priority_rank values: "
                + ", ".join(str(rank) for rank in sorted(duplicate_ranks))
            )
        if duplicate_items:
            raise ValueError(
                "prioritized_requirements must not repeat the same requirement item: "
                + ", ".join(sorted(duplicate_items))
            )
        return value

    @model_validator(mode="after")
    def validate_cross_field_consistency(self) -> "Phase1JobAnalysis":
        must_have_keys = {_fold_key(value) for value in self.must_have_skills}
        nice_to_have_overlap = [
            value for value in self.nice_to_have_skills if _fold_key(value) in must_have_keys
        ]
        if nice_to_have_overlap:
            overlap_list = ", ".join(nice_to_have_overlap)
            raise ValueError(
                "nice_to_have_skills must not repeat must_have_skills: "
                f"{overlap_list}"
            )

        prioritized_values = {_fold_key(item.requirement_text) for item in self.prioritized_requirements}
        missing_confidence_items: list[str] = []
        for item in self.prioritized_requirements:
            if item.priority_tier == PrioritizedRequirementTier.CRITICAL and item.confidence < 0.5:
                raise ValueError(
                    "critical prioritized requirements must have confidence >= 0.5"
                )
        if self.parser_confidence < 0.35 and not self.extraction_notes:
            raise ValueError(
                "low-confidence parsed job analyses must include extraction_notes"
            )
        for confidence_item in self.requirement_confidence_by_item:
            folded = _fold_key(confidence_item.item_value)
            if folded in prioritized_values:
                continue
            if confidence_item.item_type in {
                RequirementConfidenceItemType.JOB_TITLE,
                RequirementConfidenceItemType.COMPANY_NAME,
                RequirementConfidenceItemType.FUNCTIONAL_ROLE_FAMILY,
                RequirementConfidenceItemType.ORGANIZATIONAL_ROLE_MODE,
                RequirementConfidenceItemType.SENIORITY_LEVEL,
                RequirementConfidenceItemType.INDUSTRY_DOMAIN,
            }:
                continue
            missing_confidence_items.append(
                f"{confidence_item.item_type.value}:{confidence_item.item_value}"
            )
        if missing_confidence_items:
            raise ValueError(
                "requirement_confidence_by_item includes values that are not represented "
                "by prioritized_requirements or supported scalar fields: "
                + ", ".join(sorted(missing_confidence_items))
            )
        return self


class Phase1ParseResult(StrictModel):
    """Full Phase 1 parsing result preserving deterministic, LLM, and merged artifacts."""

    deterministic_extraction: DeterministicJobDescriptionExtraction
    llm_enrichment_payload: dict[str, Any] = Field(default_factory=dict)
    enriched_analysis: Phase1JobAnalysis
    merged_analysis: Phase1JobAnalysis | None = None

    @model_validator(mode="after")
    def hydrate_merged_analysis(self) -> "Phase1ParseResult":
        """Keep `merged_analysis` explicit while preserving the older alias field."""

        if self.merged_analysis is None:
            object.__setattr__(self, "merged_analysis", self.enriched_analysis)
        return self


def _validate_unique_strings(value: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in value:
        key = _fold_key(item)
        if key in seen:
            duplicates.add(item)
        seen.add(key)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"list entries must be unique: {duplicate_list}")
    return value


def _fold_key(value: str) -> str:
    return " ".join(value.casefold().split())
