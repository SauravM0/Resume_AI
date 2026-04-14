"""Verification-aware backend pipeline orchestration service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from backend.app.observability import bind_run_id, log_event
from backend.app.schemas.api_responses import (
    GenerateResumeVerificationResponse,
    api_status_from_verification,
)
from backend.app.schemas.verification import Phase3VerificationInput
from backend.app.services.verification.orchestrator import (
    VerificationOrchestrator,
    build_default_verification_orchestrator,
)
from backend.app.services.verification.types import VerificationStatus
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.phase3_generation_service import Phase3GenerationError
from resume_optimizer.phase3_models import Phase3AssemblerInput
from resume_optimizer.services.phase3_service import DEFAULT_PHASE3_SERVICE, Phase3Service

import logging

logger = logging.getLogger(__name__)


class VerificationPipelineError(RuntimeError):
    """Raised when the verification-aware pipeline cannot complete safely."""


RepositoryFactory = Callable[[], object | None]


@dataclass(slots=True)
class ResumePipelineService:
    """Run Phase 3 and the Phase 6 gate before downstream rendering acceptance."""

    phase3_service: Phase3Service = field(default_factory=lambda: DEFAULT_PHASE3_SERVICE)
    orchestrator_factory: Callable[..., VerificationOrchestrator] = build_default_verification_orchestrator
    repository_factory: RepositoryFactory | None = None

    def generate_resume_with_verification(
        self,
        request: Phase3AssemblerInput,
        *,
        pipeline_run_id: str | None = None,
    ) -> GenerateResumeVerificationResponse:
        """Generate structured content, verify it, and return a render gate response."""

        resolved_pipeline_run_id = pipeline_run_id or f"pipeline.{uuid4()}"
        bind_run_id(resolved_pipeline_run_id)
        log_event(
            logger,
            service="resume_optimizer.pipeline_service",
            event_name="pipeline_run_started",
            outcome="started",
            run_id=resolved_pipeline_run_id,
            metadata={"source_profile_id": request.source_profile.id},
        )
        phase3_result = self.phase3_service.run(
            request.job_analysis,
            phase1_final_analysis=None,
            phase2_selection=request.phase2_selection,
            phase2_ranking=request.phase2_ranking,
            source_profile=request.source_profile,
            generation_preferences=request.generation_preferences,
        )
        repository = self.repository_factory() if self.repository_factory is not None else None
        orchestrator = self.orchestrator_factory(repository=repository)
        verification_result = orchestrator.run(
            Phase3VerificationInput(
                source_profile_id=request.source_profile.id,
                job_analysis=request.job_analysis,
                source_profile=request.source_profile,
                generation_payload=phase3_result.generation_payload,
                phase3_result=phase3_result.phase3_result,
                phase3_validation_report=phase3_result.validation_report,
            ),
            generation_id=phase3_result.result_record.profile_id,
            pipeline_run_id=resolved_pipeline_run_id,
        )
        if repository is not None:
            _commit_repository(repository)

        response_status = api_status_from_verification(verification_result.report.status)
        warnings = [
            issue.message
            for item in verification_result.report.item_results
            for issue in item.issues
        ]
        log_event(
            logger,
            service="resume_optimizer.pipeline_service",
            event_name="pipeline_run_completed",
            outcome="success" if verification_result.report.renderable else "failure",
            run_id=resolved_pipeline_run_id,
            metadata={
                "verification_run_id": verification_result.verification_run_id,
                "verification_status": verification_result.report.status.value,
                "api_status": response_status,
            },
        )
        return GenerateResumeVerificationResponse(
            status=response_status,
            pipeline_run_id=resolved_pipeline_run_id,
            verification_run_id=verification_result.verification_run_id,
            phase3_result=verification_result.rendering_output.verified_result,
            verification_report=verification_result.report,
            rendering_output=verification_result.rendering_output,
            warnings=warnings,
        )


def build_default_repository() -> object | None:
    """Create a verification repository when DATABASE_URL is configured."""

    database_url = DEFAULT_SETTINGS.get_database_url()
    if not database_url:
        return None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from backend.app.db.repositories.verification_repository import VerificationRepository
    except ImportError as exc:
        raise VerificationPipelineError(
            "DATABASE_URL is configured but SQLAlchemy verification persistence dependencies are unavailable."
        ) from exc

    engine = create_engine(database_url)
    session = Session(engine)
    return VerificationRepository(session)


def _commit_repository(repository: object) -> None:
    """Commit repository session when available without coupling the interface."""

    session = getattr(repository, "session", None)
    if session is not None:
        session.commit()


DEFAULT_RESUME_PIPELINE_SERVICE = ResumePipelineService(
    repository_factory=build_default_repository,
)
