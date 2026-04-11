"""Pydantic contracts for deterministic Phase 5 resume rendering.

Developer note:
Phase 5 uses deterministic, code-driven rendering because verified resume
content must not be reinterpreted or expanded by an AI model after Phase 4.
This contract is the stable boundary between verified structured content,
LaTeX template rendering, compilation, artifact storage, and diagnostics.
Later rendering tasks will depend on these models for section ordering,
source provenance preservation, layout constraints, compile results, and
partial failure reporting.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator

from backend.app.services.verification.types import VerificationStatus
from resume_optimizer.models import NonEmptyStr, ScoreValue, StableId, StrictModel

RENDER_INPUT_SCHEMA_VERSION = "phase5.render.input.v1"
RENDER_OUTPUT_SCHEMA_VERSION = "phase5.render.output.v1"


class RenderSectionType(StrEnum):
    """Canonical resume section keys supported by deterministic rendering."""

    PERSONAL_INFO = "personal_info"
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    SKILLS = "skills"
    EDUCATION = "education"
    CERTIFICATIONS = "certifications"


class TargetPagePolicy(StrEnum):
    """Allowed page policies for renderer layout decisions."""

    STRICT_ONE_PAGE = "strict_one_page"
    PREFER_ONE_PAGE = "prefer_one_page"
    TWO_PAGE_MAX = "two_page_max"
    AUTO = "auto"


class RenderOutputStatus(StrEnum):
    """Lifecycle state for a render job result."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class RenderFailureSeverity(StrEnum):
    """Renderer-facing failure severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RenderFailureStage(StrEnum):
    """Pipeline stage where a render failure was detected."""

    CONTRACT_VALIDATION = "contract_validation"
    CONTENT_VALIDATION = "content_validation"
    TEMPLATE_RENDER = "template_render"
    LATEX_COMPILE = "latex_compile"
    ARTIFACT_STORAGE = "artifact_storage"


class ArtifactKind(StrEnum):
    """Artifact types produced by Phase 5 rendering."""

    TEX = "tex"
    PDF = "pdf"
    LOG = "log"
    AUXILIARY = "auxiliary"


class LatexCompiler(StrEnum):
    """Supported LaTeX compilers."""

    PDFLATEX = "pdflatex"
    XELATEX = "xelatex"
    LUALATEX = "lualatex"


class TemplatePlaceholder(StrEnum):
    """Allowed deterministic LaTeX insertion points."""

    PERSONAL_INFO = "PERSONAL_INFO"
    SUMMARY_SECTION = "SUMMARY_SECTION"
    EXPERIENCE_SECTION = "EXPERIENCE_SECTION"
    PROJECTS_SECTION = "PROJECTS_SECTION"
    SKILLS_SECTION = "SKILLS_SECTION"
    EDUCATION_SECTION = "EDUCATION_SECTION"
    CERTIFICATIONS_SECTION = "CERTIFICATIONS_SECTION"


class LatexTemplateMetadata(StrictModel):
    """Registry metadata for a controlled LaTeX template asset."""

    template_id: StableId
    version: NonEmptyStr
    display_name: NonEmptyStr
    description: NonEmptyStr
    active: bool = False
    ats_safe: bool = True
    max_recommended_pages: int = Field(default=1, ge=1, le=3)
    filesystem_path: Path
    required_placeholders: list[TemplatePlaceholder] = Field(min_length=1)
    optional_placeholders: list[TemplatePlaceholder] = Field(default_factory=list)
    checksum_sha256: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_template_metadata(self) -> Self:
        """Keep template identity and placeholder sets deterministic."""

        _validate_unique_ids(
            [placeholder.value for placeholder in self.required_placeholders],
            "required template placeholders",
        )
        _validate_unique_ids(
            [placeholder.value for placeholder in self.optional_placeholders],
            "optional template placeholders",
        )

        overlapping_placeholders = set(self.required_placeholders).intersection(
            self.optional_placeholders
        )
        if overlapping_placeholders:
            placeholder_list = ", ".join(
                sorted(placeholder.value for placeholder in overlapping_placeholders)
            )
            raise ValueError(
                "template placeholders cannot be both required and optional: "
                + placeholder_list
            )
        return self


class LoadedLatexTemplate(StrictModel):
    """Loaded LaTeX template content with validated registry metadata."""

    metadata: LatexTemplateMetadata
    content: NonEmptyStr
    discovered_placeholders: list[TemplatePlaceholder] = Field(default_factory=list)
    checksum_sha256: NonEmptyStr


class ConfidenceMetadata(StrictModel):
    """Confidence and verification metadata carried forward from earlier phases."""

    verified_status: VerificationStatus = VerificationStatus.PASSED
    confidence_score: ScoreValue | None = None
    support_score: ScoreValue | None = None
    evidence_strength: NonEmptyStr | None = None
    verification_run_id: StableId | None = None
    notes: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_renderable_status(self) -> Self:
        """Reject statuses that should not enter deterministic rendering."""

        blocked_statuses = {
            VerificationStatus.FAILED,
            VerificationStatus.BLOCKED,
            VerificationStatus.NEEDS_RETRY,
        }
        if self.verified_status in blocked_statuses:
            raise ValueError("renderable content cannot have failed, blocked, or retryable status")
        return self


class LayoutConstraints(StrictModel):
    """Section or job-level layout constraints used by deterministic templates."""

    max_pages: int | None = Field(default=None, ge=1, le=3)
    max_lines: int | None = Field(default=None, ge=1)
    max_bullets: int | None = Field(default=None, ge=0)
    min_bullets: int | None = Field(default=None, ge=0)
    allow_truncation: bool = False
    keep_with_next: bool = False
    priority: int = Field(default=50, ge=0, le=100)

    @model_validator(mode="after")
    def validate_bullet_bounds(self) -> Self:
        """Keep min/max bullet layout constraints coherent."""

        if (
            self.min_bullets is not None
            and self.max_bullets is not None
            and self.min_bullets > self.max_bullets
        ):
            raise ValueError("min_bullets cannot exceed max_bullets")
        return self


class RenderOptions(StrictModel):
    """Renderer options that do not change verified content semantics."""

    latex_compiler: LatexCompiler = LatexCompiler.PDFLATEX
    include_diagnostics: bool = True
    emit_intermediate_artifacts: bool = False
    deterministic_seed: int | None = Field(default=None, ge=0)
    fail_on_layout_overflow: bool = True
    locale: NonEmptyStr = "en-US"


class RenderSourceProvenance(StrictModel):
    """Source IDs preserved with renderable content whenever available."""

    source_item_ids: list[StableId] = Field(default_factory=list)
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    source_metric_ids: list[StableId] = Field(default_factory=list)
    generated_item_id: StableId | None = None


class RenderBullet(StrictModel):
    """Display-ready bullet with selected source bullet IDs preserved."""

    id: StableId
    text: NonEmptyStr
    selected_bullet_ids: list[StableId] = Field(default_factory=list)
    provenance: RenderSourceProvenance
    display_order: int = Field(ge=0)
    truncation_eligible: bool = True
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)

    @model_validator(mode="after")
    def validate_selected_bullets_match_provenance(self) -> Self:
        """Keep selected bullet IDs anchored in the provenance payload."""

        provenance_bullet_ids = set(self.provenance.source_bullet_ids)
        missing_bullet_ids = [
            bullet_id
            for bullet_id in self.selected_bullet_ids
            if bullet_id not in provenance_bullet_ids
        ]
        if missing_bullet_ids:
            raise ValueError(
                "selected_bullet_ids must be represented in provenance.source_bullet_ids: "
                + ", ".join(missing_bullet_ids)
            )
        return self


class RenderPersonalInfo(StrictModel):
    """Display-ready personal information for the resume header."""

    full_name: NonEmptyStr
    email: NonEmptyStr
    phone: NonEmptyStr | None = None
    location: NonEmptyStr | None = None
    headline: NonEmptyStr | None = None
    links: list[NonEmptyStr] = Field(default_factory=list)
    provenance: RenderSourceProvenance = Field(default_factory=RenderSourceProvenance)
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)


class RenderSummary(StrictModel):
    """Display-ready professional summary."""

    text: NonEmptyStr
    provenance: RenderSourceProvenance
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)
    truncation_eligible: bool = True


class RenderExperience(StrictModel):
    """Display-ready experience block."""

    id: StableId
    source_item_id: StableId
    organization: NonEmptyStr
    title: NonEmptyStr
    start_date: NonEmptyStr
    end_date: NonEmptyStr | None = None
    current: bool = False
    location: NonEmptyStr | None = None
    bullets: list[RenderBullet] = Field(default_factory=list)
    display_order: int = Field(ge=0)
    truncation_eligible: bool = True
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)

    @model_validator(mode="after")
    def validate_bullet_ordering(self) -> Self:
        """Require deterministic bullet ordering inside the experience block."""

        _validate_unique_order_values(self.bullets, "experience bullets")
        _validate_unique_ids([bullet.id for bullet in self.bullets], "experience bullet ids")
        return self


class RenderProject(StrictModel):
    """Display-ready project block."""

    id: StableId
    source_item_id: StableId
    name: NonEmptyStr
    role: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    bullets: list[RenderBullet] = Field(default_factory=list)
    tools: list[NonEmptyStr] = Field(default_factory=list)
    display_order: int = Field(ge=0)
    truncation_eligible: bool = True
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)

    @model_validator(mode="after")
    def validate_bullet_ordering(self) -> Self:
        """Require deterministic bullet ordering inside the project block."""

        _validate_unique_order_values(self.bullets, "project bullets")
        _validate_unique_ids([bullet.id for bullet in self.bullets], "project bullet ids")
        return self


class RenderSkillGroup(StrictModel):
    """Display-ready skill group."""

    id: StableId
    label: NonEmptyStr
    skills: list[NonEmptyStr] = Field(min_length=1)
    source_ids: list[StableId] = Field(default_factory=list)
    display_order: int = Field(ge=0)
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)


class RenderEducation(StrictModel):
    """Display-ready education item."""

    id: StableId
    source_item_id: StableId
    institution: NonEmptyStr
    degree: NonEmptyStr
    field_of_study: NonEmptyStr | None = None
    location: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    details: list[NonEmptyStr] = Field(default_factory=list)
    display_order: int = Field(ge=0)
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)


class RenderCertification(StrictModel):
    """Display-ready certification item."""

    id: StableId
    source_item_id: StableId
    name: NonEmptyStr
    issuer: NonEmptyStr
    issued_date: NonEmptyStr | None = None
    expiration_date: NonEmptyStr | None = None
    credential_id: NonEmptyStr | None = None
    display_order: int = Field(ge=0)
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)


class RenderSection(StrictModel):
    """Section-level content contract shared by renderers and layout planners."""

    id: StableId
    section_type: RenderSectionType
    title: NonEmptyStr
    visible: bool = True
    display_order: int = Field(ge=0)
    source_ids: list[StableId] = Field(default_factory=list)
    selected_bullet_ids: list[StableId] = Field(default_factory=list)
    item_ids: list[StableId] = Field(default_factory=list)
    truncation_eligible: bool = False
    layout_constraints: LayoutConstraints = Field(default_factory=LayoutConstraints)
    verified_status: VerificationStatus = VerificationStatus.PASSED
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)

    @model_validator(mode="after")
    def validate_render_section(self) -> Self:
        """Validate deterministic section metadata and bullet selection."""

        _validate_unique_ids(
            self.selected_bullet_ids,
            f"{self.section_type.value} selected bullet ids",
        )
        if self.verified_status in {
            VerificationStatus.FAILED,
            VerificationStatus.BLOCKED,
            VerificationStatus.NEEDS_RETRY,
        }:
            raise ValueError("render sections cannot have failed, blocked, or retryable status")
        if self.verified_status != self.confidence.verified_status:
            raise ValueError("verified_status must match confidence.verified_status")
        return self


class RenderJobInput(StrictModel):
    """Verified, display-ready input for deterministic Phase 5 rendering."""

    schema_version: NonEmptyStr = RENDER_INPUT_SCHEMA_VERSION
    render_job_id: StableId
    source_profile_id: StableId
    template_id: NonEmptyStr
    target_page_policy: TargetPagePolicy = TargetPagePolicy.PREFER_ONE_PAGE
    personal_info: RenderPersonalInfo
    summary: RenderSummary | None = None
    experiences: list[RenderExperience] = Field(default_factory=list)
    projects: list[RenderProject] = Field(default_factory=list)
    skills: list[RenderSkillGroup] = Field(default_factory=list)
    education: list[RenderEducation] = Field(default_factory=list)
    certifications: list[RenderCertification] = Field(default_factory=list)
    sections: list[RenderSection] = Field(min_length=1)
    section_visibility: dict[RenderSectionType, bool] = Field(default_factory=dict)
    layout_constraints: LayoutConstraints = Field(default_factory=LayoutConstraints)
    render_options: RenderOptions = Field(default_factory=RenderOptions)
    verified_status: VerificationStatus = VerificationStatus.PASSED
    confidence: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)

    @field_validator("template_id")
    @classmethod
    def validate_template_id(cls, value: str) -> str:
        """Require an explicit template id for deterministic template selection."""

        if not value.strip():
            raise ValueError("template_id is required")
        return value

    @model_validator(mode="after")
    def validate_render_job_input(self) -> Self:
        """Validate the render job as a deterministic, verified input payload."""

        if self.verified_status in {
            VerificationStatus.FAILED,
            VerificationStatus.BLOCKED,
            VerificationStatus.NEEDS_RETRY,
        }:
            raise ValueError("render job input must be verified before rendering")
        if self.verified_status != self.confidence.verified_status:
            raise ValueError("verified_status must match confidence.verified_status")

        _validate_unique_order_values(self.sections, "sections")
        _validate_unique_ids([section.id for section in self.sections], "section ids")

        visible_section_types = {
            section.section_type for section in self.sections if section.visible
        }
        if RenderSectionType.PERSONAL_INFO not in visible_section_types:
            raise ValueError("personal_info section must be visible")

        for section_type, visible in self.section_visibility.items():
            if visible and section_type not in {section.section_type for section in self.sections}:
                raise ValueError(f"visible section missing from sections: {section_type.value}")

        self._validate_section_content_presence()
        self._validate_section_bullet_uniqueness()
        return self

    def _validate_section_content_presence(self) -> None:
        """Ensure visible sections have corresponding display-ready content."""

        content_counts = {
            RenderSectionType.PERSONAL_INFO: 1,
            RenderSectionType.SUMMARY: 1 if self.summary is not None else 0,
            RenderSectionType.EXPERIENCE: len(self.experiences),
            RenderSectionType.PROJECTS: len(self.projects),
            RenderSectionType.SKILLS: len(self.skills),
            RenderSectionType.EDUCATION: len(self.education),
            RenderSectionType.CERTIFICATIONS: len(self.certifications),
        }
        for section in self.sections:
            if section.visible and content_counts[section.section_type] == 0:
                raise ValueError(f"visible section has no content: {section.section_type.value}")

    def _validate_section_bullet_uniqueness(self) -> None:
        """Reject duplicate bullet IDs within each bullet-owning section."""

        section_bullet_ids: dict[RenderSectionType, list[str]] = {
            RenderSectionType.EXPERIENCE: [
                bullet.id for experience in self.experiences for bullet in experience.bullets
            ],
            RenderSectionType.PROJECTS: [
                bullet.id for project in self.projects for bullet in project.bullets
            ],
        }
        for section_type, bullet_ids in section_bullet_ids.items():
            _validate_unique_ids(bullet_ids, f"{section_type.value} bullet ids")


class RenderFailure(StrictModel):
    """Structured render failure for diagnostics and API-safe error reporting."""

    code: StableId
    message: NonEmptyStr
    severity: RenderFailureSeverity = RenderFailureSeverity.ERROR
    stage: RenderFailureStage
    section_id: StableId | None = None
    section_type: RenderSectionType | None = None
    item_id: StableId | None = None
    source_ids: list[StableId] = Field(default_factory=list)
    selected_bullet_ids: list[StableId] = Field(default_factory=list)
    retryable: bool = False


class RenderSectionStats(StrictModel):
    """Section-level render statistics emitted by deterministic rendering."""

    section_id: StableId
    section_type: RenderSectionType
    rendered: bool
    item_count: int = Field(default=0, ge=0)
    bullet_count: int = Field(default=0, ge=0)
    estimated_lines: int | None = Field(default=None, ge=0)
    truncated_item_ids: list[StableId] = Field(default_factory=list)
    omitted_item_ids: list[StableId] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)


class RenderArtifactMetadata(StrictModel):
    """Metadata for artifacts produced by rendering and compilation."""

    artifact_id: StableId
    render_job_id: StableId
    kind: ArtifactKind
    template_id: NonEmptyStr
    content_type: NonEmptyStr
    path: NonEmptyStr | None = None
    storage_ref: NonEmptyStr | None = None
    sha256: NonEmptyStr | None = None
    size_bytes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_artifact_location(self) -> Self:
        """Require at least one location reference for persisted artifacts."""

        if self.path is None and self.storage_ref is None:
            raise ValueError("artifact metadata requires path or storage_ref")
        return self


class RenderedLatexArtifact(StrictModel):
    """Generated LaTeX artifact prior to PDF compilation."""

    metadata: RenderArtifactMetadata
    latex_content: NonEmptyStr
    warnings: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tex_artifact_kind(self) -> Self:
        """Ensure this artifact describes generated .tex content."""

        if self.metadata.kind != ArtifactKind.TEX:
            raise ValueError("RenderedLatexArtifact metadata.kind must be tex")
        return self


class CompileResult(StrictModel):
    """Result contract for a LaTeX compilation attempt."""

    success: bool
    compiler: LatexCompiler
    exit_code: int | None = None
    pdf_artifact: RenderArtifactMetadata | None = None
    log_artifact: RenderArtifactMetadata | None = None
    stdout_excerpt: NonEmptyStr | None = None
    stderr_excerpt: NonEmptyStr | None = None
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    failures: list[RenderFailure] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_compile_result(self) -> Self:
        """Keep compile success state aligned with artifacts and failures."""

        if self.success:
            if self.pdf_artifact is None:
                raise ValueError("successful compile requires pdf_artifact")
            if self.pdf_artifact.kind != ArtifactKind.PDF:
                raise ValueError("pdf_artifact.kind must be pdf")
            if any(
                failure.severity in {RenderFailureSeverity.ERROR, RenderFailureSeverity.CRITICAL}
                for failure in self.failures
            ):
                raise ValueError("successful compile cannot include error or critical failures")
        return self


class RenderDiagnostics(StrictModel):
    """Diagnostic bundle emitted by validation, rendering, and compilation."""

    warnings: list[NonEmptyStr] = Field(default_factory=list)
    failures: list[RenderFailure] = Field(default_factory=list)
    section_stats: list[RenderSectionStats] = Field(default_factory=list)
    estimated_page_count: float | None = Field(default=None, ge=0)
    layout_overflow: bool = False
    compile_log_excerpt: NonEmptyStr | None = None


class RenderJobOutput(StrictModel):
    """Final Phase 5 rendering result, including partial diagnostic failures."""

    schema_version: NonEmptyStr = RENDER_OUTPUT_SCHEMA_VERSION
    render_job_id: StableId
    status: RenderOutputStatus
    success: bool
    generated_tex_content: NonEmptyStr | None = None
    latex_artifact: RenderedLatexArtifact | None = None
    pdf_artifact_path: NonEmptyStr | None = None
    pdf_storage_ref: NonEmptyStr | None = None
    compile_success: bool = False
    compile_result: CompileResult | None = None
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    diagnostics: RenderDiagnostics = Field(default_factory=RenderDiagnostics)
    section_stats: list[RenderSectionStats] = Field(default_factory=list)
    estimated_page_count: float | None = Field(default=None, ge=0)
    failures: list[RenderFailure] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_output_state(self) -> Self:
        """Allow success and partial failures while keeping result state coherent."""

        if self.success and self.status != RenderOutputStatus.SUCCEEDED:
            raise ValueError("successful render output must use succeeded status")
        if not self.success and self.status == RenderOutputStatus.SUCCEEDED:
            raise ValueError("succeeded status requires success=true")
        if self.success and self.generated_tex_content is None:
            raise ValueError("successful render output requires generated_tex_content")
        if (
            self.success
            and self.pdf_artifact_path is None
            and self.pdf_storage_ref is None
        ):
            raise ValueError(
                "successful render output requires pdf_artifact_path or pdf_storage_ref"
            )
        if (
            self.compile_result is not None
            and self.compile_success != self.compile_result.success
        ):
            raise ValueError("compile_success must match compile_result.success")
        if self.latex_artifact is not None and self.generated_tex_content is not None:
            if self.latex_artifact.latex_content != self.generated_tex_content:
                raise ValueError("generated_tex_content must match latex_artifact.latex_content")
        return self


def _validate_unique_order_values(items: list[object], label: str) -> None:
    """Raise when display_order values are duplicated."""

    order_values = [getattr(item, "display_order") for item in items]
    duplicates = sorted(value for value in set(order_values) if order_values.count(value) > 1)
    if duplicates:
        raise ValueError(
            f"duplicate display_order values in {label}: {duplicates}"
        )


def _validate_unique_ids(ids: list[str], label: str) -> None:
    """Raise when IDs are duplicated."""

    duplicates = sorted(item_id for item_id in set(ids) if ids.count(item_id) > 1)
    if duplicates:
        raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
