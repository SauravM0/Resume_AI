"""Central failure taxonomy and handling metadata."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.orchestration.enums import FailureCategory, OrchestrationFailureType


@dataclass(frozen=True, slots=True)
class FailureHandlingDefinition:
    """Deterministic handling metadata for one internal failure type."""

    failure_type: OrchestrationFailureType
    category: FailureCategory
    retryable: bool
    max_retry_count: int
    retry_strategy: str
    backoff_seconds: float
    allowed_fallback: str
    user_safe_message: str
    operator_message: str
    default_http_status: int


FAILURE_HANDLING: dict[OrchestrationFailureType, FailureHandlingDefinition] = {
    OrchestrationFailureType.INPUT_VALIDATION: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.INPUT_VALIDATION,
        category=FailureCategory.INPUT_VALIDATION_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="The request input is invalid. Review the provided data and try again.",
        operator_message="Input validation failed before the stage could complete.",
        default_http_status=400,
    ),
    OrchestrationFailureType.SOURCE_PROFILE_LOAD: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.SOURCE_PROFILE_LOAD,
        category=FailureCategory.FILESYSTEM_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="The source profile could not be loaded.",
        operator_message="Source profile loading failed due to a filesystem or path issue.",
        default_http_status=400,
    ),
    OrchestrationFailureType.SOURCE_PROFILE_NORMALIZATION: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.SOURCE_PROFILE_NORMALIZATION,
        category=FailureCategory.CONFIGURATION_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="The source profile configuration is invalid.",
        operator_message="Source profile normalization or validation failed.",
        default_http_status=400,
    ),
    OrchestrationFailureType.JOB_DESCRIPTION_INGESTION: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.JOB_DESCRIPTION_INGESTION,
        category=FailureCategory.INPUT_VALIDATION_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="The job description input is invalid.",
        operator_message="Job description ingestion rejected invalid request data.",
        default_http_status=422,
    ),
    OrchestrationFailureType.JOB_DESCRIPTION_PARSE: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.JOB_DESCRIPTION_PARSE,
        category=FailureCategory.PARSING_ERROR,
        retryable=True,
        max_retry_count=1,
        retry_strategy="stricter_instruction_path",
        backoff_seconds=1.0,
        allowed_fallback="none",
        user_safe_message="The job description could not be parsed reliably.",
        operator_message="Job description parsing failed or returned unusable analysis.",
        default_http_status=502,
    ),
    OrchestrationFailureType.RANKING_SELECTION: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.RANKING_SELECTION,
        category=FailureCategory.RANKING_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="deterministic_best_match_subset",
        user_safe_message="Relevant resume evidence could not be selected safely.",
        operator_message="Ranking or evidence selection failed.",
        default_http_status=500,
    ),
    OrchestrationFailureType.GENERATION_PROVIDER: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.GENERATION_PROVIDER,
        category=FailureCategory.UPSTREAM_AI_ERROR,
        retryable=True,
        max_retry_count=1,
        retry_strategy="fixed_backoff",
        backoff_seconds=1.0,
        allowed_fallback="none",
        user_safe_message="Structured resume generation is temporarily unavailable.",
        operator_message="Upstream AI provider failed during structured generation.",
        default_http_status=502,
    ),
    OrchestrationFailureType.GENERATION_SCHEMA: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.GENERATION_SCHEMA,
        category=FailureCategory.MALFORMED_MODEL_OUTPUT_ERROR,
        retryable=True,
        max_retry_count=1,
        retry_strategy="stricter_instruction_path",
        backoff_seconds=1.0,
        allowed_fallback="none",
        user_safe_message="Structured resume generation returned an invalid format.",
        operator_message="Model output was malformed or failed schema validation.",
        default_http_status=502,
    ),
    OrchestrationFailureType.VERIFICATION_BLOCKED: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.VERIFICATION_BLOCKED,
        category=FailureCategory.VERIFICATION_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="source_bullet_or_safer_rewrite",
        user_safe_message="Generated content failed verification and could not be finalized safely.",
        operator_message="Verification hard-failed the generated content.",
        default_http_status=409,
    ),
    OrchestrationFailureType.VERIFICATION_RETRYABLE: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.VERIFICATION_RETRYABLE,
        category=FailureCategory.VERIFICATION_ERROR,
        retryable=True,
        max_retry_count=1,
        retry_strategy="immediate",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="Content verification could not complete. Please try again.",
        operator_message="Verification execution failed in a retryable way.",
        default_http_status=500,
    ),
    OrchestrationFailureType.RENDER_CONTRACT: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.RENDER_CONTRACT,
        category=FailureCategory.RENDER_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="The verified resume content could not be prepared for rendering.",
        operator_message="Render contract construction failed before LaTeX rendering.",
        default_http_status=500,
    ),
    OrchestrationFailureType.LATEX_RENDER: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.LATEX_RENDER,
        category=FailureCategory.RENDER_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="latex_render_correction",
        user_safe_message="The resume document could not be rendered safely.",
        operator_message="LaTeX rendering failed before PDF compilation.",
        default_http_status=500,
    ),
    OrchestrationFailureType.PDF_COMPILE: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.PDF_COMPILE,
        category=FailureCategory.LATEX_COMPILE_ERROR,
        retryable=True,
        max_retry_count=1,
        retry_strategy="local_render_correction",
        backoff_seconds=0.0,
        allowed_fallback="latex_render_correction",
        user_safe_message="The resume PDF could not be compiled.",
        operator_message="PDF compilation failed after rendering.",
        default_http_status=500,
    ),
    OrchestrationFailureType.ARTIFACT_PERSISTENCE: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.ARTIFACT_PERSISTENCE,
        category=FailureCategory.FILESYSTEM_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="The resume output could not be stored safely.",
        operator_message="Artifact persistence failed after stage execution.",
        default_http_status=500,
    ),
    OrchestrationFailureType.TIMEOUT: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.TIMEOUT,
        category=FailureCategory.TIMEOUT_ERROR,
        retryable=True,
        max_retry_count=1,
        retry_strategy="fixed_backoff",
        backoff_seconds=1.0,
        allowed_fallback="none",
        user_safe_message="The request took too long to complete.",
        operator_message="Stage execution exceeded its allowed timeout window.",
        default_http_status=504,
    ),
    OrchestrationFailureType.INTERNAL: FailureHandlingDefinition(
        failure_type=OrchestrationFailureType.INTERNAL,
        category=FailureCategory.UNEXPECTED_INTERNAL_ERROR,
        retryable=False,
        max_retry_count=0,
        retry_strategy="none",
        backoff_seconds=0.0,
        allowed_fallback="none",
        user_safe_message="The resume pipeline encountered an unexpected internal error.",
        operator_message="An unexpected internal failure escaped stage-specific classification.",
        default_http_status=500,
    ),
}


def get_failure_definition(failure_type: OrchestrationFailureType) -> FailureHandlingDefinition:
    """Return the handling definition for one failure type."""

    return FAILURE_HANDLING[failure_type]
