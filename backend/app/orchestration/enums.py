"""Stable enum values for Phase 6 pipeline orchestration contracts."""

from __future__ import annotations

from enum import StrEnum


class StageName(StrEnum):
    """Canonical end-to-end stage order for resume generation."""

    LOAD_SOURCE_PROFILE = "load_source_profile"
    NORMALIZE_SOURCE_DATA = "normalize_source_data"
    INGEST_JOB_DESCRIPTION = "ingest_job_description"
    PARSE_JOB_DESCRIPTION = "parse_job_description"
    RANK_SELECT_EVIDENCE = "rank_select_evidence"
    GENERATE_STRUCTURED_CONTENT = "generate_structured_content"
    VERIFY_GENERATED_CONTENT = "verify_generated_content"
    RENDER_DETERMINISTIC_LATEX = "render_deterministic_latex"
    COMPILE_PDF = "compile_pdf"
    PERSIST_ARTIFACTS = "persist_artifacts"


class StageStatus(StrEnum):
    """Lifecycle status for one pipeline stage attempt."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"
    FALLBACK_APPLIED = "fallback_applied"
    BLOCKED = "blocked"


class PipelineStatus(StrEnum):
    """Aggregate status for the full Phase 6 pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_WITH_WARNINGS = "succeeded_with_warnings"
    FAILED = "failed"
    BLOCKED = "blocked"


class OrchestrationFailureType(StrEnum):
    """Failure taxonomy used by contracts and retry/fallback policy."""

    INPUT_VALIDATION = "input_validation"
    SOURCE_PROFILE_LOAD = "source_profile_load"
    SOURCE_PROFILE_NORMALIZATION = "source_profile_normalization"
    JOB_DESCRIPTION_INGESTION = "job_description_ingestion"
    JOB_DESCRIPTION_PARSE = "job_description_parse"
    RANKING_SELECTION = "ranking_selection"
    GENERATION_PROVIDER = "generation_provider"
    GENERATION_SCHEMA = "generation_schema"
    VERIFICATION_BLOCKED = "verification_blocked"
    VERIFICATION_RETRYABLE = "verification_retryable"
    RENDER_CONTRACT = "render_contract"
    LATEX_RENDER = "latex_render"
    PDF_COMPILE = "pdf_compile"
    ARTIFACT_PERSISTENCE = "artifact_persistence"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


class FailureCategory(StrEnum):
    """User-safe failure taxonomy for deterministic handling and messaging."""

    INPUT_VALIDATION_ERROR = "input_validation_error"
    CONFIGURATION_ERROR = "configuration_error"
    UPSTREAM_AI_ERROR = "upstream_ai_error"
    MALFORMED_MODEL_OUTPUT_ERROR = "malformed_model_output_error"
    PARSING_ERROR = "parsing_error"
    RANKING_ERROR = "ranking_error"
    GENERATION_ERROR = "generation_error"
    VERIFICATION_ERROR = "verification_error"
    RENDER_ERROR = "render_error"
    LATEX_COMPILE_ERROR = "latex_compile_error"
    FILESYSTEM_ERROR = "filesystem_error"
    TIMEOUT_ERROR = "timeout_error"
    UNEXPECTED_INTERNAL_ERROR = "unexpected_internal_error"


class ArtifactKind(StrEnum):
    """Persistence-oriented artifact categories emitted by Phase 6."""

    SOURCE_PROFILE = "source_profile"
    NORMALIZED_PROFILE = "normalized_profile"
    RAW_JOB_DESCRIPTION = "raw_job_description"
    JOB_ANALYSIS = "job_analysis"
    PHASE1_DETERMINISTIC_EXTRACTION = "phase1_deterministic_extraction"
    PHASE1_LLM_ENRICHMENT = "phase1_llm_enrichment"
    PHASE1_FINAL_ANALYSIS = "phase1_final_analysis"
    PHASE2_SELECTION = "phase2_selection"
    PHASE2_RANKING = "phase2_ranking"
    PHASE3_REQUEST = "phase3_request"
    PHASE3_PAYLOAD = "phase3_payload"
    PHASE3_SECTION_PLAN = "phase3_section_plan"
    PHASE3_RESULT = "phase3_result"
    PHASE3_VALIDATION_REPORT = "phase3_validation_report"
    VERIFICATION_REPORT = "verification_report"
    VERIFICATION_AUDIT = "verification_audit"
    RENDERING_GATE = "rendering_gate"
    RENDER_INPUT = "render_input"
    LATEX_DOCUMENT = "latex_document"
    PDF = "pdf"
    COMPILE_LOG = "compile_log"
    STAGE_LOG = "stage_log"
    PIPELINE_RESULT = "pipeline_result"


class ArtifactStorageBackend(StrEnum):
    """Where an artifact reference is expected to resolve."""

    INLINE = "inline"
    LOCAL_FILE = "local_file"
    POSTGRES = "postgres"
    SUPABASE_STORAGE = "supabase_storage"
    EXTERNAL = "external"


class FallbackEligibility(StrEnum):
    """Whether a stage can continue through a deterministic fallback."""

    NOT_ALLOWED = "not_allowed"
    ALLOWED = "allowed"
    REQUIRED_ON_FAILURE = "required_on_failure"


class RetryEligibility(StrEnum):
    """Whether a stage failure can be retried by the orchestrator."""

    NOT_RETRYABLE = "not_retryable"
    RETRYABLE = "retryable"
    RETRYABLE_WITH_BACKOFF = "retryable_with_backoff"
