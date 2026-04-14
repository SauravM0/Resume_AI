"""Canonical Phase 6 stage contracts.

The models in this module describe how an orchestrator may call stages. They do
not execute stages, call providers, persist data, or render artifacts.
"""

from __future__ import annotations

from pydantic import Field

from backend.app.orchestration.enums import (
    ArtifactKind,
    FallbackEligibility,
    OrchestrationFailureType,
    RetryEligibility,
    StageName,
)
from backend.app.orchestration.pipeline_models import (
    CompilePdfInput,
    CompilePdfOutput,
    GenerateStructuredContentInput,
    GenerateStructuredContentOutput,
    IngestJobDescriptionInput,
    IngestJobDescriptionOutput,
    LoadSourceProfileInput,
    LoadSourceProfileOutput,
    NormalizeSourceDataInput,
    NormalizeSourceDataOutput,
    ParseJobDescriptionInput,
    ParseJobDescriptionOutput,
    PersistArtifactsInput,
    PersistArtifactsOutput,
    RankSelectEvidenceInput,
    RankSelectEvidenceOutput,
    RenderDeterministicLatexInput,
    RenderDeterministicLatexOutput,
    VerifyGeneratedContentInput,
    VerifyGeneratedContentOutput,
)
from backend.app.orchestration.types import FallbackPolicy, RetryPolicy, StageIORef
from resume_optimizer.models import NonEmptyStr, StrictModel


class StageContract(StrictModel):
    """Declarative contract for one pipeline stage."""

    stage_name: StageName
    description: NonEmptyStr
    input_schema: NonEmptyStr
    output_schema: NonEmptyStr
    required_inputs: list[StageIORef] = Field(default_factory=list)
    produced_outputs: list[StageIORef] = Field(default_factory=list)
    possible_failure_types: list[OrchestrationFailureType] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    fallback_policy: FallbackPolicy = Field(default_factory=FallbackPolicy)
    wraps_existing_modules: list[NonEmptyStr] = Field(default_factory=list)


PIPELINE_STAGE_CONTRACTS: tuple[StageContract, ...] = (
    StageContract(
        stage_name=StageName.LOAD_SOURCE_PROFILE,
        description="Load source profile by inline payload, profile id, or configured file path.",
        input_schema=LoadSourceProfileInput.__name__,
        output_schema=LoadSourceProfileOutput.__name__,
        required_inputs=[
            StageIORef(
                name="source_profile_reference",
                artifact_kind=ArtifactKind.SOURCE_PROFILE,
                schema_ref=LoadSourceProfileInput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="source_profile",
                artifact_kind=ArtifactKind.SOURCE_PROFILE,
                schema_ref=LoadSourceProfileOutput.__name__,
            )
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.SOURCE_PROFILE_LOAD,
        ],
        wraps_existing_modules=["resume_optimizer.loaders"],
    ),
    StageContract(
        stage_name=StageName.NORMALIZE_SOURCE_DATA,
        description="Normalize and validate source profile data before downstream selection.",
        input_schema=NormalizeSourceDataInput.__name__,
        output_schema=NormalizeSourceDataOutput.__name__,
        required_inputs=[
            StageIORef(
                name="source_profile",
                artifact_kind=ArtifactKind.SOURCE_PROFILE,
                schema_ref=LoadSourceProfileOutput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="normalized_profile",
                artifact_kind=ArtifactKind.NORMALIZED_PROFILE,
                schema_ref=NormalizeSourceDataOutput.__name__,
            )
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.SOURCE_PROFILE_NORMALIZATION,
        ],
        wraps_existing_modules=[
            "resume_optimizer.normalizers",
            "resume_optimizer.validators",
        ],
    ),
    StageContract(
        stage_name=StageName.INGEST_JOB_DESCRIPTION,
        description="Validate and fingerprint the raw job description input.",
        input_schema=IngestJobDescriptionInput.__name__,
        output_schema=IngestJobDescriptionOutput.__name__,
        required_inputs=[
            StageIORef(
                name="raw_job_description",
                artifact_kind=ArtifactKind.RAW_JOB_DESCRIPTION,
                schema_ref=IngestJobDescriptionInput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="job_description_request",
                artifact_kind=ArtifactKind.RAW_JOB_DESCRIPTION,
                schema_ref=IngestJobDescriptionOutput.__name__,
            )
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.JOB_DESCRIPTION_INGESTION,
        ],
    ),
    StageContract(
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
        description="Parse and normalize job description into the Phase 1 job analysis contract.",
        input_schema=ParseJobDescriptionInput.__name__,
        output_schema=ParseJobDescriptionOutput.__name__,
        required_inputs=[
            StageIORef(
                name="job_description_request",
                artifact_kind=ArtifactKind.RAW_JOB_DESCRIPTION,
                schema_ref=IngestJobDescriptionOutput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="job_analysis",
                artifact_kind=ArtifactKind.JOB_ANALYSIS,
                schema_ref=ParseJobDescriptionOutput.__name__,
            ),
            StageIORef(
                name="phase1_deterministic_extraction",
                artifact_kind=ArtifactKind.PHASE1_DETERMINISTIC_EXTRACTION,
                schema_ref=ParseJobDescriptionOutput.__name__,
            ),
            StageIORef(
                name="phase1_llm_enrichment",
                artifact_kind=ArtifactKind.PHASE1_LLM_ENRICHMENT,
                schema_ref=ParseJobDescriptionOutput.__name__,
            ),
            StageIORef(
                name="phase1_final_analysis",
                artifact_kind=ArtifactKind.PHASE1_FINAL_ANALYSIS,
                schema_ref=ParseJobDescriptionOutput.__name__,
            ),
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.JOB_DESCRIPTION_PARSE,
            OrchestrationFailureType.TIMEOUT,
        ],
        retry_policy=RetryPolicy(
            eligibility=RetryEligibility.RETRYABLE_WITH_BACKOFF,
            max_attempts=2,
            backoff_seconds=1.0,
            retryable_failure_types=[
                OrchestrationFailureType.JOB_DESCRIPTION_PARSE,
                OrchestrationFailureType.TIMEOUT,
            ],
        ),
        wraps_existing_modules=[
            "resume_optimizer.ai_service",
            "resume_optimizer.phase1_parser",
            "resume_optimizer.phase1_legacy_adapter",
        ],
    ),
    StageContract(
        stage_name=StageName.RANK_SELECT_EVIDENCE,
        description="Rank and select source evidence against normalized job analysis.",
        input_schema=RankSelectEvidenceInput.__name__,
        output_schema=RankSelectEvidenceOutput.__name__,
        required_inputs=[
            StageIORef(
                name="job_analysis",
                artifact_kind=ArtifactKind.JOB_ANALYSIS,
                schema_ref=ParseJobDescriptionOutput.__name__,
            ),
            StageIORef(
                name="normalized_profile",
                artifact_kind=ArtifactKind.NORMALIZED_PROFILE,
                schema_ref=NormalizeSourceDataOutput.__name__,
            ),
        ],
        produced_outputs=[
            StageIORef(
                name="phase2_selection",
                artifact_kind=ArtifactKind.PHASE2_SELECTION,
                schema_ref=RankSelectEvidenceOutput.__name__,
            ),
            StageIORef(
                name="phase2_ranking",
                artifact_kind=ArtifactKind.PHASE2_RANKING,
                schema_ref=RankSelectEvidenceOutput.__name__,
            ),
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.RANKING_SELECTION,
        ],
        wraps_existing_modules=["resume_optimizer.ranking_service"],
    ),
    StageContract(
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        description="Generate structured Phase 3 resume content from selected evidence.",
        input_schema=GenerateStructuredContentInput.__name__,
        output_schema=GenerateStructuredContentOutput.__name__,
        required_inputs=[
            StageIORef(
                name="phase2_selection",
                artifact_kind=ArtifactKind.PHASE2_SELECTION,
                schema_ref=RankSelectEvidenceOutput.__name__,
            ),
            StageIORef(
                name="phase2_ranking",
                artifact_kind=ArtifactKind.PHASE2_RANKING,
                schema_ref=RankSelectEvidenceOutput.__name__,
            ),
        ],
        produced_outputs=[
            StageIORef(
                name="phase3_result",
                artifact_kind=ArtifactKind.PHASE3_RESULT,
                schema_ref=GenerateStructuredContentOutput.__name__,
            )
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.GENERATION_PROVIDER,
            OrchestrationFailureType.GENERATION_SCHEMA,
            OrchestrationFailureType.TIMEOUT,
        ],
        retry_policy=RetryPolicy(
            eligibility=RetryEligibility.RETRYABLE_WITH_BACKOFF,
            max_attempts=2,
            backoff_seconds=1.0,
            retryable_failure_types=[
                OrchestrationFailureType.GENERATION_PROVIDER,
                OrchestrationFailureType.GENERATION_SCHEMA,
                OrchestrationFailureType.TIMEOUT,
            ],
        ),
        fallback_policy=FallbackPolicy(
            eligibility=FallbackEligibility.ALLOWED,
            fallback_failure_types=[OrchestrationFailureType.GENERATION_SCHEMA],
            description="Use existing Phase 3 conservative source-grounded fallback validation when possible.",
        ),
        wraps_existing_modules=["resume_optimizer.services.phase3_service"],
    ),
    StageContract(
        stage_name=StageName.VERIFY_GENERATED_CONTENT,
        description="Verify Phase 3 generated content before any deterministic rendering.",
        input_schema=VerifyGeneratedContentInput.__name__,
        output_schema=VerifyGeneratedContentOutput.__name__,
        required_inputs=[
            StageIORef(
                name="phase3_result",
                artifact_kind=ArtifactKind.PHASE3_RESULT,
                schema_ref=GenerateStructuredContentOutput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="verification_report",
                artifact_kind=ArtifactKind.VERIFICATION_REPORT,
                schema_ref=VerifyGeneratedContentOutput.__name__,
            ),
            StageIORef(
                name="rendering_gate",
                artifact_kind=ArtifactKind.RENDERING_GATE,
                schema_ref=VerifyGeneratedContentOutput.__name__,
            ),
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.VERIFICATION_BLOCKED,
            OrchestrationFailureType.VERIFICATION_RETRYABLE,
        ],
        retry_policy=RetryPolicy(
            eligibility=RetryEligibility.RETRYABLE,
            max_attempts=2,
            retryable_failure_types=[OrchestrationFailureType.VERIFICATION_RETRYABLE],
        ),
        fallback_policy=FallbackPolicy(
            eligibility=FallbackEligibility.ALLOWED,
            fallback_failure_types=[OrchestrationFailureType.VERIFICATION_BLOCKED],
            description="Use verification fallback action only when the verification report marks content renderable.",
        ),
        wraps_existing_modules=["backend.app.services.verification.orchestrator"],
    ),
    StageContract(
        stage_name=StageName.RENDER_DETERMINISTIC_LATEX,
        description="Convert verified structured content into deterministic LaTeX.",
        input_schema=RenderDeterministicLatexInput.__name__,
        output_schema=RenderDeterministicLatexOutput.__name__,
        required_inputs=[
            StageIORef(
                name="rendering_gate",
                artifact_kind=ArtifactKind.RENDERING_GATE,
                schema_ref=VerifyGeneratedContentOutput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="latex_document",
                artifact_kind=ArtifactKind.LATEX_DOCUMENT,
                schema_ref=RenderDeterministicLatexOutput.__name__,
            )
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.RENDER_CONTRACT,
            OrchestrationFailureType.LATEX_RENDER,
        ],
        wraps_existing_modules=[
            "backend.app.models.render_models",
            "backend.app.services.template_registry",
            "backend.app.services.latex_mapper",
            "backend.app.services.layout_manager",
            "backend.app.services.document_assembler",
        ],
    ),
    StageContract(
        stage_name=StageName.COMPILE_PDF,
        description="Compile deterministic LaTeX into a PDF artifact.",
        input_schema=CompilePdfInput.__name__,
        output_schema=CompilePdfOutput.__name__,
        required_inputs=[
            StageIORef(
                name="latex_document",
                artifact_kind=ArtifactKind.LATEX_DOCUMENT,
                schema_ref=RenderDeterministicLatexOutput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="pdf",
                artifact_kind=ArtifactKind.PDF,
                schema_ref=CompilePdfOutput.__name__,
            ),
            StageIORef(
                name="compile_log",
                artifact_kind=ArtifactKind.COMPILE_LOG,
                schema_ref=CompilePdfOutput.__name__,
                required=False,
            ),
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.PDF_COMPILE,
            OrchestrationFailureType.TIMEOUT,
        ],
        retry_policy=RetryPolicy(
            eligibility=RetryEligibility.RETRYABLE,
            max_attempts=2,
            retryable_failure_types=[
                OrchestrationFailureType.PDF_COMPILE,
                OrchestrationFailureType.TIMEOUT,
            ],
        ),
        wraps_existing_modules=["backend.app.services.pdf_compiler"],
    ),
    StageContract(
        stage_name=StageName.PERSIST_ARTIFACTS,
        description="Persist final and requested intermediate artifacts and return a manifest.",
        input_schema=PersistArtifactsInput.__name__,
        output_schema=PersistArtifactsOutput.__name__,
        required_inputs=[
            StageIORef(
                name="stage_results",
                artifact_kind=ArtifactKind.PIPELINE_RESULT,
                schema_ref=PersistArtifactsInput.__name__,
            )
        ],
        produced_outputs=[
            StageIORef(
                name="artifact_manifest",
                artifact_kind=ArtifactKind.PIPELINE_RESULT,
                schema_ref=PersistArtifactsOutput.__name__,
            )
        ],
        possible_failure_types=[
            OrchestrationFailureType.INPUT_VALIDATION,
            OrchestrationFailureType.ARTIFACT_PERSISTENCE,
        ],
        retry_policy=RetryPolicy(
            eligibility=RetryEligibility.RETRYABLE_WITH_BACKOFF,
            max_attempts=3,
            backoff_seconds=1.0,
            retryable_failure_types=[OrchestrationFailureType.ARTIFACT_PERSISTENCE],
        ),
    ),
)


def get_stage_contract(stage_name: StageName) -> StageContract:
    """Return the canonical contract for a stage."""

    for contract in PIPELINE_STAGE_CONTRACTS:
        if contract.stage_name == stage_name:
            return contract
    raise ValueError(f"unknown stage contract: {stage_name}")
