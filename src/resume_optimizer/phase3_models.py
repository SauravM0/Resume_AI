"""Strict contracts for Phase 3 structured resume content generation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from .job_models import NormalizedJobAnalysis
from .models import (
    EvidenceStrength,
    ItemType,
    MasterProfile,
    NonEmptyStr,
    PartialDate,
    ScoreValue,
    StableId,
    StrictModel,
    VerifiedStatus,
)
from .phase2_models import Phase2SelectionResult, Phase2Status
from .ranking_models import RankingResponse

_BULLET_SOURCE_ITEM_TYPES = (
    ItemType.EXPERIENCE,
    ItemType.PROJECT,
    ItemType.EDUCATION,
)
_PHASE3_SELECTED_ITEM_TYPES = (
    ItemType.EXPERIENCE,
    ItemType.PROJECT,
)


class SupportLevel(StrEnum):
    """Strength of support behind a generated Phase 3 item."""

    DIRECT = "direct"
    SYNTHESIZED = "synthesized"
    INFERRED = "inferred"


class WarningLevel(StrEnum):
    """Severity level for generation-time warnings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class OmissionReason(StrEnum):
    """Why a source item or bullet was not carried into generated content."""

    PHASE2_NOT_SELECTED = "phase2_not_selected"
    LOW_RELEVANCE = "low_relevance"
    REDUNDANT = "redundant"
    OUTDATED = "outdated"
    LOW_SUPPORT = "low_support"
    SPACE_CONSTRAINT = "space_constraint"
    PREFERENCE_FILTERED = "preference_filtered"


class BulletRewriteStrategy(StrEnum):
    """How a generated bullet relates to its source bullet text."""

    LIGHT_REWRITE = "light_rewrite"
    CONDENSED = "condensed"
    MERGED = "merged"


class Phase3JobAnalysisInput(NormalizedJobAnalysis):
    """Normalized Phase 1 output consumed by Phase 3 generation."""


class Phase3SelectionInput(Phase2SelectionResult):
    """Canonical Phase 2 output consumed by Phase 3 generation."""


class Phase3SourceProfileInput(MasterProfile):
    """Normalized source profile consumed by Phase 3 generation."""


class GenerationPreferences(StrictModel):
    """Optional knobs that shape Phase 3 output without changing source truth."""

    target_role_title: NonEmptyStr | None = None
    target_tone: NonEmptyStr | None = None
    target_page_count: int | None = Field(default=None, ge=1, le=2)
    headline_max_words: int | None = Field(default=None, ge=2, le=24)
    summary_max_sentences: int | None = Field(default=None, ge=1, le=6)
    max_experience_bullets: int | None = Field(default=None, ge=1, le=8)
    max_project_bullets: int | None = Field(default=None, ge=1, le=6)
    emphasize_metrics: bool = True
    preserve_chronology: bool = True
    suppress_low_support_content: bool = True


class Phase3RankingInput(RankingResponse):
    """Backward-compatible Phase 2 ranking response consumed by the assembler."""


class Phase3RoleContext(StrictModel):
    """Compact job-target context carried into structured generation."""

    target_role_title: NonEmptyStr | None = None
    target_role_type: NonEmptyStr | None = None
    target_seniority: NonEmptyStr | None = None
    target_industry_domain: NonEmptyStr | None = None
    must_have_skills: list[NonEmptyStr] = Field(default_factory=list)
    preferred_skills: list[NonEmptyStr] = Field(default_factory=list)
    must_have_requirements: list[NonEmptyStr] = Field(default_factory=list)
    preferred_requirements: list[NonEmptyStr] = Field(default_factory=list)
    company_terminology: list[NonEmptyStr] = Field(default_factory=list)
    action_verbs: list[NonEmptyStr] = Field(default_factory=list)


class Phase3SummaryHint(StrictModel):
    """Structured summary emphasis hint derived from Phase 2 ranking output."""

    theme: NonEmptyStr
    supporting_keywords: list[NonEmptyStr] = Field(default_factory=list)


class Phase3LengthConstraints(StrictModel):
    """Compact output-length hints for generation without rendering concerns."""

    target_page_count: int | None = Field(default=None, ge=1, le=2)
    headline_max_words: int | None = Field(default=None, ge=2, le=24)
    summary_max_sentences: int | None = Field(default=None, ge=1, le=6)
    max_experience_bullets: int | None = Field(default=None, ge=1, le=8)
    max_project_bullets: int | None = Field(default=None, ge=1, le=6)


class Phase3SelectedBulletPayload(StrictModel):
    """Minimal bullet context exposed to the generator with stable source references."""

    id: StableId
    text: NonEmptyStr
    tools: list[NonEmptyStr] = Field(default_factory=list)
    metric_ids: list[StableId] = Field(default_factory=list)
    evidence_strength: EvidenceStrength
    verified_status: VerifiedStatus
    rewrite_allowed: bool = True


class Phase3SelectedExperiencePayload(StrictModel):
    """Selected experience entry compacted for Phase 3 generation."""

    id: StableId
    evidence_unit_ids: list[StableId] = Field(min_length=1)
    organization: NonEmptyStr
    title: NonEmptyStr
    start_date: PartialDate
    end_date: PartialDate | None = None
    current: bool = False
    tools: list[NonEmptyStr] = Field(default_factory=list)
    bullets: list[Phase3SelectedBulletPayload] = Field(default_factory=list)
    relevance_score: ScoreValue
    matched_requirements: list[NonEmptyStr] = Field(default_factory=list)
    selection_reason: NonEmptyStr | None = None
    supporting_evidence_ids: list[StableId] = Field(default_factory=list)
    score_factors: dict[str, float] = Field(default_factory=dict)


class Phase3SelectedProjectPayload(StrictModel):
    """Selected project entry compacted for Phase 3 generation."""

    id: StableId
    evidence_unit_ids: list[StableId] = Field(min_length=1)
    name: NonEmptyStr
    role: NonEmptyStr | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    summary: NonEmptyStr | None = None
    tools: list[NonEmptyStr] = Field(default_factory=list)
    bullets: list[Phase3SelectedBulletPayload] = Field(default_factory=list)
    relevance_score: ScoreValue
    matched_requirements: list[NonEmptyStr] = Field(default_factory=list)
    selection_reason: NonEmptyStr | None = None
    supporting_evidence_ids: list[StableId] = Field(default_factory=list)
    score_factors: dict[str, float] = Field(default_factory=dict)


class Phase3SelectedSkillPayload(StrictModel):
    """Selected skill signal preserved for generation and later validation."""

    id: StableId
    skill_name: NonEmptyStr
    relevance_score: ScoreValue
    evidence_strength: EvidenceStrength
    verified_status: VerifiedStatus
    matched_requirements: list[NonEmptyStr] = Field(default_factory=list)
    selection_reason: NonEmptyStr | None = None
    supporting_evidence_ids: list[StableId] = Field(default_factory=list)
    score_factors: dict[str, float] = Field(default_factory=dict)


class Phase3SelectedCertificationPayload(StrictModel):
    """Selected certification signal included when Phase 2 ranked it."""

    id: StableId
    evidence_unit_ids: list[StableId] = Field(min_length=1)
    name: NonEmptyStr
    issuer: NonEmptyStr
    issue_date: PartialDate | None = None
    expiration_date: PartialDate | None = None
    relevance_score: ScoreValue


class Phase3ValidationMetadata(StrictModel):
    """Small validation-oriented context preserved alongside the generation payload."""

    profile_id: StableId
    phase2_status: Phase2Status = Phase2Status.SUCCESS
    allowed_experience_ids: list[StableId] = Field(default_factory=list)
    allowed_project_ids: list[StableId] = Field(default_factory=list)
    allowed_certification_ids: list[StableId] = Field(default_factory=list)
    allowed_skill_ids: list[StableId] = Field(default_factory=list)
    allowed_bullet_ids: list[StableId] = Field(default_factory=list)


class Phase3GenerationPayload(StrictModel):
    """Compact deterministic payload prepared for the Phase 3 generator LLM."""

    role_context: Phase3RoleContext
    selected_experiences: list[Phase3SelectedExperiencePayload] = Field(default_factory=list)
    selected_projects: list[Phase3SelectedProjectPayload] = Field(default_factory=list)
    matched_skills: list[Phase3SelectedSkillPayload] = Field(default_factory=list)
    selected_certifications: list[Phase3SelectedCertificationPayload] = Field(default_factory=list)
    headline_hint: NonEmptyStr | None = None
    summary_hints: list[Phase3SummaryHint] = Field(default_factory=list)
    length_constraints: Phase3LengthConstraints | None = None
    validation_metadata: Phase3ValidationMetadata


class Phase3AssemblerInput(StrictModel):
    """Full upstream artifact set required to assemble a generator-safe Phase 3 payload."""

    job_analysis: Phase3JobAnalysisInput
    phase2_selection: Phase3SelectionInput
    phase2_ranking: Phase3RankingInput
    source_profile: Phase3SourceProfileInput
    generation_preferences: GenerationPreferences | None = None

    @field_validator("job_analysis", mode="before")
    @classmethod
    def coerce_job_analysis(cls, value: object) -> object:
        """Accept the existing normalized job-analysis contract as assembler input."""

        if isinstance(value, NormalizedJobAnalysis):
            return value.model_dump(exclude_computed_fields=True)
        return value

    @field_validator("phase2_selection", mode="before")
    @classmethod
    def coerce_phase2_selection(cls, value: object) -> object:
        """Accept the existing Phase 2 selection contract as assembler input."""

        if isinstance(value, Phase2SelectionResult):
            return value.model_dump(exclude_computed_fields=True)
        return value

    @field_validator("phase2_ranking", mode="before")
    @classmethod
    def coerce_phase2_ranking(cls, value: object) -> object:
        """Accept the existing Phase 2 ranking response as assembler input."""

        if isinstance(value, RankingResponse):
            return value.model_dump(exclude_computed_fields=True)
        return value

    @field_validator("source_profile", mode="before")
    @classmethod
    def coerce_source_profile(cls, value: object) -> object:
        """Accept the existing master-profile contract as assembler input."""

        if isinstance(value, MasterProfile):
            return value.model_dump(exclude_computed_fields=True)
        return value

    @model_validator(mode="after")
    def validate_cross_phase_references(self) -> "Phase3AssemblerInput":
        """Ensure upstream artifacts belong to the same candidate and job context."""

        if self.phase2_selection.candidate_profile_id != self.source_profile.id:
            raise ValueError(
                "phase2_selection.candidate_profile_id must match source_profile.id"
            )

        if self.phase2_selection.job_analysis.model_dump() != self.job_analysis.model_dump():
            raise ValueError("phase2_selection.job_analysis must match job_analysis")

        return self


class SourceReference(StrictModel):
    """Atomic provenance reference used by generated Phase 3 content."""

    source_item_id: StableId
    source_item_type: ItemType
    source_bullet_id: StableId | None = None
    source_metric_ids: list[StableId] = Field(default_factory=list)
    support_level: SupportLevel = SupportLevel.DIRECT
    support_score: ScoreValue | None = None

    @model_validator(mode="after")
    def validate_bullet_reference_shape(self) -> "SourceReference":
        """Only allow bullet ids for source item types that can own bullets."""

        if (
            self.source_bullet_id is not None
            and self.source_item_type not in _BULLET_SOURCE_ITEM_TYPES
        ):
            raise ValueError(
                "source_bullet_id is only valid for experience, project, or education items"
            )
        return self


class GeneratedTextItem(StrictModel):
    """Shared generated text payload with strict source attribution."""

    text: NonEmptyStr
    source_item_ids: list[StableId] = Field(min_length=1)
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    provenance: list[SourceReference] = Field(min_length=1)
    support_level: SupportLevel
    confidence_score: ScoreValue | None = None

    @model_validator(mode="after")
    def validate_source_alignment(self) -> "GeneratedTextItem":
        """Ensure flattened source ids match the detailed provenance payload."""

        provenance_item_ids = {reference.source_item_id for reference in self.provenance}
        missing_item_ids = [
            source_item_id
            for source_item_id in self.source_item_ids
            if source_item_id not in provenance_item_ids
        ]
        if missing_item_ids:
            missing_list = ", ".join(missing_item_ids)
            raise ValueError(
                f"source_item_ids must be represented in provenance: {missing_list}"
            )

        provenance_bullet_ids = {
            reference.source_bullet_id
            for reference in self.provenance
            if reference.source_bullet_id is not None
        }
        missing_bullet_ids = [
            bullet_id
            for bullet_id in self.source_bullet_ids
            if bullet_id not in provenance_bullet_ids
        ]
        if missing_bullet_ids:
            missing_list = ", ".join(missing_bullet_ids)
            raise ValueError(
                f"source_bullet_ids must be represented in provenance: {missing_list}"
            )
        return self


class GeneratedHeadline(GeneratedTextItem):
    """Structured headline output for later verification and rendering."""


class GeneratedSummary(GeneratedTextItem):
    """Structured summary output for later verification and rendering."""


class SectionEmphasis(GeneratedTextItem):
    """Optional section-level emphasis guidance for later resume composition."""

    section_key: NonEmptyStr


class GeneratedSkillHighlight(StrictModel):
    """Skill signal selected for emphasis in the rendered resume."""

    skill_name: NonEmptyStr
    source_item_ids: list[StableId] = Field(min_length=1)
    provenance: list[SourceReference] = Field(min_length=1)
    support_level: SupportLevel
    confidence_score: ScoreValue | None = None

    @model_validator(mode="after")
    def validate_provenance_alignment(self) -> "GeneratedSkillHighlight":
        """Require every highlighted skill to point to explicit source items."""

        provenance_item_ids = {reference.source_item_id for reference in self.provenance}
        missing_item_ids = [
            source_item_id
            for source_item_id in self.source_item_ids
            if source_item_id not in provenance_item_ids
        ]
        if missing_item_ids:
            missing_list = ", ".join(missing_item_ids)
            raise ValueError(
                f"source_item_ids must be represented in provenance: {missing_list}"
            )
        return self


class GeneratedBullet(StrictModel):
    """Rewritten bullet with bullet-level provenance preserved for verification."""

    id: StableId
    source_item_id: StableId
    source_item_type: ItemType
    source_bullet_ids: list[StableId] = Field(min_length=1)
    rewritten_text: NonEmptyStr
    rewrite_strategy: BulletRewriteStrategy
    provenance: list[SourceReference] = Field(min_length=1)
    support_level: SupportLevel
    confidence_score: ScoreValue | None = None

    @model_validator(mode="after")
    def validate_generated_bullet_references(self) -> "GeneratedBullet":
        """Keep generated bullets anchored to their source item and source bullets."""

        if self.source_item_type not in _PHASE3_SELECTED_ITEM_TYPES:
            allowed = ", ".join(item.value for item in _PHASE3_SELECTED_ITEM_TYPES)
            raise ValueError(f"generated bullet source_item_type must be one of: {allowed}")

        provenance_item_ids = {reference.source_item_id for reference in self.provenance}
        if self.source_item_id not in provenance_item_ids:
            raise ValueError("source_item_id must be represented in provenance")

        provenance_bullet_ids = {
            reference.source_bullet_id
            for reference in self.provenance
            if reference.source_bullet_id is not None
        }
        missing_bullet_ids = [
            bullet_id
            for bullet_id in self.source_bullet_ids
            if bullet_id not in provenance_bullet_ids
        ]
        if missing_bullet_ids:
            missing_list = ", ".join(missing_bullet_ids)
            raise ValueError(
                f"source_bullet_ids must be represented in provenance: {missing_list}"
            )
        return self


class GeneratedExperience(StrictModel):
    """Selected experience block for later verification and final rendering."""

    source_item_id: StableId
    item_type: ItemType = ItemType.EXPERIENCE
    organization: NonEmptyStr
    title: NonEmptyStr
    start_date: PartialDate
    end_date: PartialDate | None = None
    current: bool = False
    generated_bullets: list[GeneratedBullet] = Field(min_length=1)
    ranking_relevance_score: ScoreValue | None = None
    support_level: SupportLevel
    confidence_score: ScoreValue | None = None

    @model_validator(mode="after")
    def validate_generated_bullet_ownership(self) -> "GeneratedExperience":
        """Ensure every rewritten bullet belongs to this selected experience."""

        for bullet in self.generated_bullets:
            if bullet.source_item_id != self.source_item_id:
                raise ValueError("generated bullets must reference the parent experience id")
            if bullet.source_item_type != ItemType.EXPERIENCE:
                raise ValueError("generated experience bullets must use experience source_item_type")
        return self


class GeneratedProject(StrictModel):
    """Selected project block for later verification and final rendering."""

    source_item_id: StableId
    item_type: ItemType = ItemType.PROJECT
    name: NonEmptyStr
    role: NonEmptyStr | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    generated_bullets: list[GeneratedBullet] = Field(min_length=1)
    ranking_relevance_score: ScoreValue | None = None
    support_level: SupportLevel
    confidence_score: ScoreValue | None = None

    @model_validator(mode="after")
    def validate_generated_bullet_ownership(self) -> "GeneratedProject":
        """Ensure every rewritten bullet belongs to this selected project."""

        for bullet in self.generated_bullets:
            if bullet.source_item_id != self.source_item_id:
                raise ValueError("generated bullets must reference the parent project id")
            if bullet.source_item_type != ItemType.PROJECT:
                raise ValueError("generated project bullets must use project source_item_type")
        return self


class OmittedItem(StrictModel):
    """Explicit record of a source item or bullet that was intentionally omitted."""

    source_item_id: StableId
    source_item_type: ItemType
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    reason: OmissionReason
    detail: NonEmptyStr | None = None
    superseded_by_source_item_ids: list[StableId] = Field(default_factory=list)


class GenerationWarning(StrictModel):
    """Structured warning emitted during Phase 3 content generation."""

    code: StableId
    level: WarningLevel
    message: NonEmptyStr
    source_item_ids: list[StableId] = Field(default_factory=list)
    source_bullet_ids: list[StableId] = Field(default_factory=list)


class GenerationMetadata(StrictModel):
    """Operational metadata that future phases can use for verification and rendering."""

    schema_version: NonEmptyStr = "phase3.v1"
    phase: NonEmptyStr = "phase3"
    source_profile_id: StableId
    phase2_status: Phase2Status = Phase2Status.SUCCESS
    selected_experience_count: int = Field(default=0, ge=0)
    selected_project_count: int = Field(default=0, ge=0)
    highlighted_skill_count: int = Field(default=0, ge=0)
    omitted_item_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    preferences_applied: list[NonEmptyStr] = Field(default_factory=list)


class Phase3GenerationRequest(StrictModel):
    """Full Phase 3 input contract assembled from upstream structured artifacts."""

    job_analysis: Phase3JobAnalysisInput
    phase2_selection: Phase3SelectionInput
    source_profile: Phase3SourceProfileInput
    generation_preferences: GenerationPreferences | None = None

    @field_validator("job_analysis", mode="before")
    @classmethod
    def coerce_job_analysis(cls, value: object) -> object:
        """Accept the existing normalized job analysis contract as Phase 3 input."""

        if isinstance(value, NormalizedJobAnalysis):
            return value.model_dump(exclude_computed_fields=True)
        return value

    @field_validator("phase2_selection", mode="before")
    @classmethod
    def coerce_phase2_selection(cls, value: object) -> object:
        """Accept the existing Phase 2 selection contract as Phase 3 input."""

        if isinstance(value, Phase2SelectionResult):
            return value.model_dump(exclude_computed_fields=True)
        return value

    @field_validator("source_profile", mode="before")
    @classmethod
    def coerce_source_profile(cls, value: object) -> object:
        """Accept the existing master-profile contract as Phase 3 input."""

        if isinstance(value, MasterProfile):
            return value.model_dump(exclude_computed_fields=True)
        return value

    @model_validator(mode="after")
    def validate_cross_phase_references(self) -> "Phase3GenerationRequest":
        """Ensure Phase 1, Phase 2, and source-profile artifacts point to the same profile data."""

        if self.phase2_selection.candidate_profile_id != self.source_profile.id:
            raise ValueError(
                "phase2_selection.candidate_profile_id must match source_profile.id"
            )

        if self.phase2_selection.job_analysis.model_dump() != self.job_analysis.model_dump():
            raise ValueError("phase2_selection.job_analysis must match job_analysis")

        evidence_by_id = {
            item.id: item for item in self.phase2_selection.scored_evidence
        }
        experience_ids = {entry.id for entry in self.source_profile.experience}
        project_ids = {entry.id for entry in self.source_profile.projects}
        skill_ids = {entry.id for entry in self.source_profile.skills}

        for selected in self.phase2_selection.selected_experiences:
            if selected.source_item_id in experience_ids:
                resolved_source_id = selected.source_item_id
            else:
                selected_evidence = evidence_by_id.get(selected.source_item_id)
                resolved_source_id = (
                    selected_evidence.source_item_id if selected_evidence is not None else None
                )
            if resolved_source_id not in experience_ids:
                raise ValueError(
                    "phase2 selected experience source_item_id not found in scored_evidence/source_profile: "
                    f"{selected.source_item_id}"
                )

        for selected in self.phase2_selection.selected_projects:
            if selected.source_item_id in project_ids:
                resolved_source_id = selected.source_item_id
            else:
                selected_evidence = evidence_by_id.get(selected.source_item_id)
                resolved_source_id = (
                    selected_evidence.source_item_id if selected_evidence is not None else None
                )
            if resolved_source_id not in project_ids:
                raise ValueError(
                    "phase2 selected project source_item_id not found in scored_evidence/source_profile: "
                    f"{selected.source_item_id}"
                )

        for selected in self.phase2_selection.selected_skills:
            if selected.source_item_id not in skill_ids:
                raise ValueError(
                    "phase2 selected skill source_item_id not found in source_profile: "
                    f"{selected.source_item_id}"
                )

        return self


class Phase3GenerationResult(StrictModel):
    """Canonical Phase 3 output carrying structured, source-linked generated content."""

    headline: GeneratedHeadline | None = None
    summary: GeneratedSummary | None = None
    section_emphasis: list[SectionEmphasis] = Field(default_factory=list)
    selected_experiences: list[GeneratedExperience] = Field(default_factory=list)
    selected_projects: list[GeneratedProject] = Field(default_factory=list)
    skills_to_highlight: list[GeneratedSkillHighlight] = Field(default_factory=list)
    omitted_items: list[OmittedItem] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)
    metadata: GenerationMetadata

    @model_validator(mode="after")
    def validate_result_consistency(self) -> "Phase3GenerationResult":
        """Keep Phase 3 outputs internally consistent and count metadata deterministic."""

        generated_bullet_ids: list[str] = []
        for experience in self.selected_experiences:
            generated_bullet_ids.extend(bullet.id for bullet in experience.generated_bullets)
        for project in self.selected_projects:
            generated_bullet_ids.extend(bullet.id for bullet in project.generated_bullets)

        duplicate_bullet_ids = sorted(
            bullet_id
            for bullet_id in set(generated_bullet_ids)
            if generated_bullet_ids.count(bullet_id) > 1
        )
        if duplicate_bullet_ids:
            duplicate_list = ", ".join(duplicate_bullet_ids)
            raise ValueError(f"duplicate generated bullet ids detected: {duplicate_list}")

        object.__setattr__(
            self,
            "metadata",
            self.metadata.model_copy(
                update={
                    "selected_experience_count": len(self.selected_experiences),
                    "selected_project_count": len(self.selected_projects),
                    "highlighted_skill_count": len(self.skills_to_highlight),
                    "omitted_item_count": len(self.omitted_items),
                    "warning_count": len(self.warnings),
                }
            ),
        )
        return self


class Phase3GenerationResultRecord(StrictModel):
    """Persistence-oriented DTO for storing one Phase 3 generation snapshot later."""

    profile_id: StableId
    request: Phase3GenerationRequest
    result: Phase3GenerationResult
