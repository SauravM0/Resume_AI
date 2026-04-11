"""Pydantic IO models for the Phase 6 end-to-end pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import Field, model_validator

from backend.app.models.render_models import RenderJobInput, RenderJobOutput
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus
from backend.app.orchestration.types import PipelineArtifactRef, StageError, StageTiming
from backend.app.schemas.verification import (
    Phase4RenderingOutput,
    VerificationReport,
)
from backend.app.services.document_assembler import AssembledDocument
from backend.app.services.pdf_compiler import PdfCompileResult
from resume_optimizer.job_models import NormalizedJobAnalysis, ParsedJobAnalysisResponse, RawJobDescriptionRequest
from resume_optimizer.models import MasterProfile, NonEmptyStr, StableId, StrictModel
from resume_optimizer.phase1_deterministic_models import DeterministicJobDescriptionExtraction
from resume_optimizer.phase1_models import Phase1JobAnalysis, Phase1ParseResult
from resume_optimizer.phase2_models import Phase2SelectionResult
from resume_optimizer.phase3_models import (
    GenerationPreferences,
    Phase3GenerationPayload,
    Phase3GenerationRequest,
    Phase3GenerationResult,
)
from resume_optimizer.phase3_output_validation import Phase3ValidationReport
from resume_optimizer.phase3_section_planner import Phase3SectionPlan
from resume_optimizer.ranking_models import RankingResponse


class PipelineInput(StrictModel):
    """Public input needed to start a Phase 6 resume generation run."""

    pipeline_run_id: StableId | None = None
    source_profile_id: StableId | None = None
    source_profile_path: Path | None = None
    source_profile: MasterProfile | None = None
    job_description_text: NonEmptyStr
    job_posting_url: str | None = None
    generation_preferences: GenerationPreferences | None = None
    template_id: NonEmptyStr = "ats_standard"
    render_job_id: StableId | None = None
    persist_intermediate_artifacts: bool = True
    frontend_correlation_id: StableId | None = None

    @model_validator(mode="after")
    def validate_profile_source(self) -> "PipelineInput":
        """Require one explicit profile source."""

        if self.source_profile is None and self.source_profile_path is None and self.source_profile_id is None:
            raise ValueError("one profile source is required")
        return self


class LoadSourceProfileInput(StrictModel):
    """Input for loading source profile data."""

    source_profile_id: StableId | None = None
    source_profile_path: Path | None = None
    source_profile: MasterProfile | None = None


class LoadSourceProfileOutput(StrictModel):
    """Loaded source profile before optional normalization."""

    source_profile_id: StableId
    source_profile: MasterProfile
    loaded_from: NonEmptyStr


class NormalizeSourceDataInput(StrictModel):
    """Input for source profile normalization and validation."""

    source_profile: MasterProfile
    source_profile_id: StableId


class NormalizeSourceDataOutput(StrictModel):
    """Normalized source profile and validation summary."""

    source_profile_id: StableId
    normalized_profile: MasterProfile
    normalization_applied: bool = False
    validation_warnings: list[NonEmptyStr] = Field(default_factory=list)


class IngestJobDescriptionInput(StrictModel):
    """Raw job description ingestion input."""

    job_description_text: NonEmptyStr
    job_posting_url: str | None = None


class IngestJobDescriptionOutput(StrictModel):
    """Validated raw job description artifact for parsing."""

    request: RawJobDescriptionRequest
    jd_hash: NonEmptyStr | None = None
    source_url: str | None = None


class ParseJobDescriptionInput(StrictModel):
    """Input for Phase 1 job description parsing."""

    request: RawJobDescriptionRequest


class ParseJobDescriptionOutput(StrictModel):
    """Phase 1 parsed output carrying rich and compatibility-normalized views."""

    raw_analysis: ParsedJobAnalysisResponse | None = None
    normalized_analysis: NormalizedJobAnalysis
    phase1_result: Phase1ParseResult | None = None
    deterministic_extraction: DeterministicJobDescriptionExtraction | None = None
    llm_enrichment_payload: dict[str, object] = Field(default_factory=dict)
    final_analysis: Phase1JobAnalysis | None = None
    model_artifact_ref: PipelineArtifactRef | None = None


class RankSelectEvidenceInput(StrictModel):
    """Input for Phase 2 ranking and evidence selection."""

    job_analysis: NormalizedJobAnalysis
    source_profile: MasterProfile


class RankSelectEvidenceOutput(StrictModel):
    """Phase 2 ranking and canonical selection artifacts."""

    ranking_response: RankingResponse
    selection_result: Phase2SelectionResult


class GenerateStructuredContentInput(StrictModel):
    """Input for Phase 3 structured resume content generation."""

    job_analysis: NormalizedJobAnalysis
    phase1_final_analysis: Phase1JobAnalysis | None = None
    phase2_selection: Phase2SelectionResult
    phase2_ranking: RankingResponse
    source_profile: MasterProfile
    generation_preferences: GenerationPreferences | None = None


class GenerateStructuredContentOutput(StrictModel):
    """Phase 3 generated structured content and supporting artifacts."""

    request: Phase3GenerationRequest
    generation_payload: Phase3GenerationPayload
    section_plan: Phase3SectionPlan
    phase3_result: Phase3GenerationResult
    validation_report: Phase3ValidationReport
    bounded_generation_context: dict[str, object] = Field(default_factory=dict)
    bounded_generation_artifacts: dict[str, object] = Field(default_factory=dict)


class VerifyGeneratedContentInput(StrictModel):
    """Input for the Phase 6 verification gate."""

    source_profile_id: StableId
    job_analysis: NormalizedJobAnalysis
    source_profile: MasterProfile
    generation_payload: Phase3GenerationPayload
    phase3_result: Phase3GenerationResult
    phase3_validation_report: Phase3ValidationReport | None = None


class VerifyGeneratedContentOutput(StrictModel):
    """Phase 6 verification report and rendering gate."""

    verification_run_id: StableId
    verification_report: VerificationReport
    rendering_output: Phase4RenderingOutput


class RenderDeterministicLatexInput(StrictModel):
    """Input for deterministic Phase 5 LaTeX rendering."""

    source_profile: MasterProfile
    rendering_output: Phase4RenderingOutput
    template_id: NonEmptyStr
    render_job_id: StableId


class RenderDeterministicLatexOutput(StrictModel):
    """Deterministic LaTeX render output before PDF compilation."""

    render_input: RenderJobInput
    assembled_document: AssembledDocument
    render_output: RenderJobOutput | None = None


class CompilePdfInput(StrictModel):
    """Input for compiling assembled LaTeX into a PDF artifact."""

    render_job_id: StableId
    template_id: NonEmptyStr
    assembled_document: AssembledDocument


class CompilePdfOutput(StrictModel):
    """PDF compilation result and artifact metadata."""

    compile_result: PdfCompileResult
    pdf_artifact_ref: PipelineArtifactRef | None = None
    log_artifact_ref: PipelineArtifactRef | None = None


class PersistArtifactsInput(StrictModel):
    """Input for persisting final and intermediate pipeline artifacts."""

    pipeline_run_id: StableId
    stage_results: list["StageResult"] = Field(default_factory=list)
    requested_artifact_kinds: list[ArtifactKind] = Field(default_factory=list)


class PersistArtifactsOutput(StrictModel):
    """Persisted artifact manifest returned by the persistence stage."""

    pipeline_run_id: StableId
    artifact_refs: list[PipelineArtifactRef] = Field(default_factory=list)
    result_artifact_ref: PipelineArtifactRef | None = None


class StageResult(StrictModel):
    """Serializable result envelope for one stage attempt."""

    pipeline_run_id: StableId
    stage_name: StageName
    status: StageStatus
    attempt: int = Field(default=1, ge=1)
    timing: StageTiming = Field(default_factory=StageTiming)
    output: (
        LoadSourceProfileOutput
        | NormalizeSourceDataOutput
        | IngestJobDescriptionOutput
        | ParseJobDescriptionOutput
        | RankSelectEvidenceOutput
        | GenerateStructuredContentOutput
        | VerifyGeneratedContentOutput
        | RenderDeterministicLatexOutput
        | CompilePdfOutput
        | PersistArtifactsOutput
        | None
    ) = None
    output_artifacts: list[PipelineArtifactRef] = Field(default_factory=list)
    errors: list[StageError] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    retry_eligible: bool = False
    fallback_eligible: bool = False
    fallback_applied: bool = False

    @model_validator(mode="after")
    def validate_result_state(self) -> "StageResult":
        """Keep status, output, and errors aligned."""

        if self.status == StageStatus.SUCCEEDED and self.output is None:
            raise ValueError("succeeded stage results require output")
        if self.status in {StageStatus.FAILED, StageStatus.BLOCKED} and not self.errors:
            raise ValueError("failed or blocked stage results require errors")
        if self.fallback_applied and not self.fallback_eligible:
            raise ValueError("fallback_applied requires fallback_eligible")
        return self


class PipelineResult(StrictModel):
    """Final serializable Phase 6 pipeline result."""

    pipeline_run_id: StableId
    status: PipelineStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stage_results: list[StageResult] = Field(default_factory=list)
    artifact_manifest: list[PipelineArtifactRef] = Field(default_factory=list)
    final_pdf_artifact: PipelineArtifactRef | None = None
    final_latex_artifact: PipelineArtifactRef | None = None
    verification_report: VerificationReport | None = None
    errors: list[StageError] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pipeline_result(self) -> "PipelineResult":
        """Ensure terminal success has the expected final PDF artifact."""

        if self.status in {PipelineStatus.SUCCEEDED, PipelineStatus.SUCCEEDED_WITH_WARNINGS}:
            if self.final_pdf_artifact is None:
                raise ValueError("successful pipeline results require final_pdf_artifact")
        if self.status in {PipelineStatus.FAILED, PipelineStatus.BLOCKED} and not self.errors:
            raise ValueError("failed or blocked pipeline results require errors")
        return self


# Rebuild after forward reference from PersistArtifactsInput to StageResult.
PersistArtifactsInput.model_rebuild()
