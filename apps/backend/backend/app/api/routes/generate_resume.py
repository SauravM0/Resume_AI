"""Thin FastAPI route for Phase 6 end-to-end resume generation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Response

from backend.app.api.idempotency import (
    ResumeGenerationIdempotencyRegistry,
    build_generation_request_fingerprint,
    build_in_flight_duplicate_response,
)
from backend.app.metrics.storage import record_stage_metric
from backend.app.observability import bind_run_id, log_event
from backend.app.orchestration.errors import OrchestrationError
from backend.app.orchestration.orchestrator import (
    DEFAULT_RESUME_GENERATION_ORCHESTRATOR,
)
from backend.app.schemas.orchestration import (
    GenerateResumePipelineResponse,
    PipelineInput,
)

router = APIRouter(prefix="/api", tags=["resume"])
logger = logging.getLogger(__name__)
DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY = ResumeGenerationIdempotencyRegistry()


@router.post("/generate-resume", response_model=GenerateResumePipelineResponse)
def generate_resume(
    request: PipelineInput,
    http_response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> GenerateResumePipelineResponse:
    """Run the full Phase 6 pipeline and return output artifact metadata."""

    validation_started_at = datetime.now(timezone.utc)
    canonical_key, immutable_input_hash = build_generation_request_fingerprint(
        request,
        idempotency_key=idempotency_key,
    )
    idempotency_decision = DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY.begin(
        canonical_key=canonical_key,
        immutable_input_hash=immutable_input_hash,
        requested_run_id=request.pipeline_run_id,
        idempotency_key=idempotency_key,
    )
    request = request.model_copy(
        update={"pipeline_run_id": idempotency_decision.run_id}
    )
    log_event(
        logger,
        service="resume_optimizer.api.generate_resume",
        event_name="request_validated",
        outcome="success",
        run_id=request.pipeline_run_id,
        metadata={
            "route": "/api/generate-resume",
            "template_id": request.template_id,
            "persist_intermediate_artifacts": request.persist_intermediate_artifacts,
            "has_frontend_correlation_id": request.frontend_correlation_id is not None,
            "idempotency_present": idempotency_key is not None,
            "idempotency_outcome": idempotency_decision.outcome,
        },
    )
    record_stage_metric(
        stage_name="request_validation",
        started_at=validation_started_at,
        ended_at=datetime.now(timezone.utc),
        success=True,
        run_id=request.pipeline_run_id,
        output_metadata={
            "route": "/api/generate-resume",
            "template_id": request.template_id,
            "idempotency_outcome": idempotency_decision.outcome,
        },
    )
    if idempotency_decision.outcome == "in_flight_duplicate":
        duplicate_response = build_in_flight_duplicate_response(
            run_id=idempotency_decision.run_id
        )
        http_response.status_code = 202
        http_response.headers["X-Idempotency-Status"] = "in_flight_duplicate"
        http_response.headers["X-Idempotency-Fingerprint"] = immutable_input_hash
        log_event(
            logger,
            service="resume_optimizer.api.generate_resume",
            event_name="duplicate_request_detected",
            outcome="success",
            run_id=idempotency_decision.run_id,
            metadata={
                "route": "/api/generate-resume",
                "duplicate_state": "in_flight",
            },
        )
        return duplicate_response
    if idempotency_decision.outcome == "completed_duplicate":
        assert idempotency_decision.response is not None
        http_response.headers["X-Idempotency-Status"] = "replayed_completed_result"
        http_response.headers["X-Idempotency-Fingerprint"] = immutable_input_hash
        log_event(
            logger,
            service="resume_optimizer.api.generate_resume",
            event_name="duplicate_request_detected",
            outcome="success",
            run_id=idempotency_decision.run_id,
            metadata={
                "route": "/api/generate-resume",
                "duplicate_state": "completed_recent",
            },
        )
        return idempotency_decision.response
    try:
        pipeline_response = DEFAULT_RESUME_GENERATION_ORCHESTRATOR.run(request)
        bind_run_id(pipeline_response.run_id)
        DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY.mark_completed(
            canonical_key=canonical_key,
            response=pipeline_response,
            idempotency_key=idempotency_key,
        )
        packaging_started_at = datetime.now(timezone.utc)
        record_stage_metric(
            stage_name="response_packaging",
            started_at=packaging_started_at,
            ended_at=datetime.now(timezone.utc),
            success=True,
            run_id=pipeline_response.run_id,
            output_metadata={
                "route": "/api/generate-resume",
                "status": pipeline_response.status.value,
                "available_outputs_count": len(pipeline_response.available_outputs),
            },
        )
        http_response.headers["X-Idempotency-Status"] = "new_execution"
        http_response.headers["X-Idempotency-Fingerprint"] = immutable_input_hash
        return pipeline_response
    except OrchestrationError as exc:
        DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY.release(canonical_key=canonical_key)
        bind_run_id(exc.run_id)
        log_event(
            logger,
            level=logging.ERROR,
            service="resume_optimizer.api.generate_resume",
            event_name="pipeline_request_failed",
            outcome="failure",
            run_id=exc.run_id,
            stage_name=exc.stage_name.value if exc.stage_name is not None else None,
            error_code=exc.failure_type.value,
            metadata={
                "route": "/api/generate-resume",
                "http_status_code": exc.http_status_code,
                "retryable": exc.retryable,
                "fallback_eligible": exc.fallback_eligible,
                "failure_category": exc.failure_category.value,
                "operator_diagnostic_message": exc.operator_diagnostic_message,
            },
        )
        record_stage_metric(
            stage_name="response_packaging",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            success=False,
            failure_type=exc.failure_type.value,
            run_id=exc.run_id,
            output_metadata={
                "route": "/api/generate-resume",
                "http_status_code": exc.http_status_code,
            },
        )
        raise HTTPException(
            status_code=exc.http_status_code,
            detail=exc.to_safe_api_detail(),
        ) from exc
    except Exception as exc:
        DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY.release(canonical_key=canonical_key)
        from backend.app.orchestration.enums import OrchestrationFailureType, StageName
        from backend.app.orchestration.errors import OrchestrationError

        fallback_error = OrchestrationError(
            message=str(exc),
            failure_type=OrchestrationFailureType.INTERNAL,
            stage_name=StageName.PERSIST_ARTIFACTS,
            http_status_code=500,
            user_safe_message="An unexpected error occurred during resume generation.",
            operator_diagnostic_message=f"Unhandled exception in /api/generate-resume: {exc}",
            root_cause=exc,
        )
        log_event(
            logger,
            level=logging.ERROR,
            service="resume_optimizer.api.generate_resume",
            event_name="pipeline_unhandled_exception",
            outcome="failure",
            stage_name=fallback_error.stage_name.value
            if fallback_error.stage_name
            else None,
            error_code=fallback_error.failure_type.value,
            metadata={
                "route": "/api/generate-resume",
                "http_status_code": fallback_error.http_status_code,
                "exception_type": type(exc).__name__,
                "operator_diagnostic_message": fallback_error.operator_diagnostic_message,
            },
        )
        raise HTTPException(
            status_code=fallback_error.http_status_code,
            detail=fallback_error.to_safe_api_detail(),
        ) from exc
