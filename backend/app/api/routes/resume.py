"""Verification-aware resume pipeline routes."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, HTTPException

from backend.app.metrics.storage import record_stage_metric
from backend.app.observability import bind_run_id, log_event
from backend.app.schemas.api_responses import GenerateResumeVerificationResponse
from backend.app.services.pipeline_service import (
    DEFAULT_RESUME_PIPELINE_SERVICE,
    VerificationPipelineError,
)
from resume_optimizer.phase3_generation_service import Phase3GenerationError
from resume_optimizer.phase3_models import Phase3AssemblerInput

router = APIRouter(prefix="/api", tags=["resume"])
logger = logging.getLogger(__name__)


@router.post(
    "/generate-resume-with-verification",
    response_model=GenerateResumeVerificationResponse,
)
def generate_resume_with_verification(
    request: Phase3AssemblerInput,
) -> GenerateResumeVerificationResponse:
    """Run Phase 3 generation and Phase 4 verification before render acceptance."""

    validation_started_at = datetime.now(timezone.utc)
    log_event(
        logger,
        service="resume_optimizer.api.generate_resume_with_verification",
        event_name="request_validated",
        outcome="success",
        metadata={
            "route": "/api/generate-resume-with-verification",
            "source_profile_id": request.source_profile.id,
            "phase2_status": request.phase2_selection.diagnostics.status.value,
        },
    )
    record_stage_metric(
        stage_name="request_validation",
        started_at=validation_started_at,
        ended_at=datetime.now(timezone.utc),
        success=True,
        output_metadata={
            "route": "/api/generate-resume-with-verification",
            "source_profile_id": request.source_profile.id,
        },
    )
    try:
        response = DEFAULT_RESUME_PIPELINE_SERVICE.generate_resume_with_verification(request)
    except Phase3GenerationError as exc:
        log_event(
            logger,
            level=logging.ERROR,
            service="resume_optimizer.api.generate_resume_with_verification",
            event_name="pipeline_request_failed",
            outcome="failure",
            error_code="phase3_generation_error",
            metadata={"route": "/api/generate-resume-with-verification"},
        )
        record_stage_metric(
            stage_name="response_packaging",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            success=False,
            failure_type="phase3_generation_error",
            output_metadata={"route": "/api/generate-resume-with-verification"},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except VerificationPipelineError as exc:
        log_event(
            logger,
            level=logging.ERROR,
            service="resume_optimizer.api.generate_resume_with_verification",
            event_name="pipeline_request_failed",
            outcome="failure",
            error_code="verification_pipeline_error",
            metadata={"route": "/api/generate-resume-with-verification"},
        )
        record_stage_metric(
            stage_name="response_packaging",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            success=False,
            failure_type="verification_pipeline_error",
            output_metadata={"route": "/api/generate-resume-with-verification"},
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        log_event(
            logger,
            level=logging.ERROR,
            service="resume_optimizer.api.generate_resume_with_verification",
            event_name="pipeline_request_failed",
            outcome="failure",
            error_code="value_error",
            metadata={"route": "/api/generate-resume-with-verification"},
        )
        record_stage_metric(
            stage_name="response_packaging",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            success=False,
            failure_type="value_error",
            output_metadata={"route": "/api/generate-resume-with-verification"},
        )
        raise HTTPException(status_code=500, detail=f"Resume pipeline validation failed: {exc}") from exc
    except TypeError as exc:
        log_event(
            logger,
            level=logging.ERROR,
            service="resume_optimizer.api.generate_resume_with_verification",
            event_name="pipeline_request_failed",
            outcome="failure",
            error_code="type_error",
            metadata={"route": "/api/generate-resume-with-verification"},
        )
        record_stage_metric(
            stage_name="response_packaging",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            success=False,
            failure_type="type_error",
            output_metadata={"route": "/api/generate-resume-with-verification"},
        )
        raise HTTPException(status_code=500, detail=f"Resume pipeline validation failed: {exc}") from exc
    except RuntimeError as exc:
        log_event(
            logger,
            level=logging.ERROR,
            service="resume_optimizer.api.generate_resume_with_verification",
            event_name="pipeline_request_failed",
            outcome="failure",
            error_code="runtime_error",
            metadata={"route": "/api/generate-resume-with-verification"},
        )
        record_stage_metric(
            stage_name="response_packaging",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            success=False,
            failure_type="runtime_error",
            output_metadata={"route": "/api/generate-resume-with-verification"},
        )
        raise HTTPException(status_code=500, detail=f"Resume pipeline execution failed: {exc}") from exc

    bind_run_id(response.pipeline_run_id)
    record_stage_metric(
        stage_name="response_packaging",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        success=response.status != "verification_failed",
        failure_type=None if response.status != "verification_failed" else "verification_failed",
        run_id=response.pipeline_run_id,
        output_metadata={
            "route": "/api/generate-resume-with-verification",
            "status": response.status,
            "warnings_count": len(response.warnings),
        },
    )
    if response.status == "verification_failed":
        raise HTTPException(
            status_code=409,
            detail=response.model_dump(mode="json", exclude_none=True),
        )
    return response
