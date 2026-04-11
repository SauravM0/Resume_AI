"""Pipeline run recorder and repository factory for Phase 6 orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from uuid import uuid4

from backend.app.observability import log_event
from backend.app.orchestration.confidence import RunConfidenceAssessment
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus
from backend.app.orchestration.event_emitter import DEFAULT_PIPELINE_EVENT_EMITTER, PipelineEventEmitter
from backend.app.orchestration.errors import OrchestrationError
from backend.app.orchestration.fallbacks import build_fallback_audit_payload
from backend.app.privacy import sanitize_diagnostic_text, sanitize_value
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.config import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)


class PipelineRunRecorder:
    """Persist run state when a repository is configured, otherwise keep in memory."""

    def __init__(
        self,
        repository: object | None = None,
        event_emitter: PipelineEventEmitter | None = DEFAULT_PIPELINE_EVENT_EMITTER,
    ) -> None:
        self.repository = repository
        self.event_emitter = event_emitter
        self.run_id: str | None = None
        self.stage_events: list[dict[str, Any]] = []
        self.artifacts: list[PipelineArtifactRef] = []
        self.outputs: list[dict[str, Any]] = []
        self.retry_attempts: list[dict[str, Any]] = []
        self.fallback_decisions: list[dict[str, Any]] = []
        self.fallback_audits: list[dict[str, Any]] = []
        self.confidence_assessment: RunConfidenceAssessment | None = None
        self.quality_downgraded = False
        self.warnings: list[str] = []
        if repository is None:
            self.warnings.append("Pipeline persistence repository is not configured; using in-memory run tracking.")

    def create_run(
        self,
        *,
        run_id: str | None,
        requested_template: str,
        requested_mode: str,
        job_description_hash: str,
        source_profile_id: str | None,
    ) -> str:
        """Create a pipeline run record and return its id."""

        resolved_run_id = run_id or str(uuid4())
        self.run_id = resolved_run_id
        if self.repository is not None:
            from backend.app.db.repositories.orchestration_repository import PipelineRunCreate

            row = self.repository.create_pipeline_run(
                PipelineRunCreate(
                    id=resolved_run_id,
                    status=PipelineStatus.RUNNING,
                    requested_template=requested_template,
                    requested_mode=requested_mode,
                    job_description_hash=job_description_hash,
                    source_profile_id=source_profile_id,
                    started_at=datetime.now(timezone.utc),
                )
            )
            self.run_id = row.id
        if self.event_emitter is not None:
            self.event_emitter.emit_run_started(run_id=self.run_id)
        return self.run_id

    def record_stage_event(
        self,
        *,
        stage_name: StageName,
        status: StageStatus,
        attempt_number: int,
        message: str,
        machine_payload_json: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Persist or buffer a stage event."""

        assert self.run_id is not None
        payload = {
            "run_id": self.run_id,
            "stage_name": stage_name.value,
            "status": status.value,
            "attempt_number": attempt_number,
            "message": sanitize_diagnostic_text(message, default=f"{stage_name.value} {status.value}."),
            "machine_payload_json": sanitize_value(machine_payload_json or {}),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
        }
        self.stage_events.append(payload)
        if self.event_emitter is not None:
            self.event_emitter.emit_stage_event(
                run_id=self.run_id,
                stage_name=stage_name,
                status=status,
                attempt_number=attempt_number,
                message=payload["message"],
                machine_payload_json=payload["machine_payload_json"],
            )
        if self.repository is not None:
            from backend.app.db.repositories.orchestration_repository import StageEventCreate

            self.repository.add_stage_event(
                StageEventCreate(
                    run_id=self.run_id,
                    stage_name=stage_name,
                    status=status,
                    attempt_number=attempt_number,
                    message=payload["message"],
                    machine_payload_json=payload["machine_payload_json"],
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                )
            )

    def record_artifact(
        self,
        *,
        stage_name: StageName,
        artifact_type: ArtifactKind,
        storage_kind: str,
        schema_version: str,
        storage_path_or_key: str | None = None,
        inline_json: dict[str, Any] | None = None,
        content_hash: str | None = None,
        content_type: str = "application/json",
        metadata: dict[str, Any] | None = None,
    ) -> PipelineArtifactRef:
        """Persist or buffer an artifact reference."""

        assert self.run_id is not None
        artifact_ref = PipelineArtifactRef(
            artifact_id=f"artifact.{uuid4()}",
            kind=artifact_type,
            stage_name=stage_name,
            storage_backend=storage_kind,
            schema_version=schema_version,
            uri=storage_path_or_key,
            sha256=content_hash,
            content_type=content_type,
            metadata=metadata or {},
        )
        self.artifacts.append(artifact_ref)
        if self.repository is not None:
            from backend.app.db.repositories.orchestration_repository import PipelineArtifactCreate

            self.repository.add_artifact(
                PipelineArtifactCreate(
                    run_id=self.run_id,
                    stage_name=stage_name,
                    artifact_type=artifact_type,
                    storage_kind=storage_kind,
                    storage_path_or_key=storage_path_or_key,
                    inline_json=inline_json,
                    content_hash=content_hash,
                )
            )
        return artifact_ref

    def record_output(
        self,
        *,
        compile_status: str,
        pdf_path_or_storage_key: str | None,
        latex_path_or_storage_key: str | None,
        page_count: int | None,
        output_metadata_json: dict[str, Any],
    ) -> None:
        """Persist or buffer final output metadata."""

        assert self.run_id is not None
        payload = {
            "compile_status": compile_status,
            "pdf_path_or_storage_key": pdf_path_or_storage_key,
            "latex_path_or_storage_key": latex_path_or_storage_key,
            "page_count": page_count,
            "output_metadata_json": output_metadata_json,
        }
        self.outputs.append(payload)
        if self.repository is not None:
            from backend.app.db.repositories.orchestration_repository import PipelineOutputCreate

            self.repository.add_output(
                PipelineOutputCreate(
                    run_id=self.run_id,
                    compile_status=compile_status,
                    pdf_path_or_storage_key=pdf_path_or_storage_key,
                    latex_path_or_storage_key=latex_path_or_storage_key,
                    page_count=page_count,
                    output_metadata_json=output_metadata_json,
                )
            )

    def record_retry(
        self,
        *,
        stage_name: StageName,
        attempt_number: int,
        reason: str,
        retry_strategy: str,
        result_status: StageStatus,
    ) -> None:
        """Persist or buffer a retry attempt."""

        assert self.run_id is not None
        payload = {
            "stage_name": stage_name.value,
            "attempt_number": attempt_number,
            "reason": sanitize_diagnostic_text(reason),
            "retry_strategy": retry_strategy,
            "result_status": result_status.value,
        }
        self.retry_attempts.append(payload)
        if self.repository is not None:
            from backend.app.db.repositories.orchestration_repository import RetryAttemptCreate

            self.repository.add_retry_attempt(
                RetryAttemptCreate(
                    run_id=self.run_id,
                    stage_name=stage_name,
                    attempt_number=attempt_number,
                    reason=payload["reason"],
                    retry_strategy=retry_strategy,
                    result_status=result_status,
                )
            )

    def record_fallback_decision(
        self,
        *,
        stage_name: StageName,
        attempt_number: int,
        reason: str,
        fallback_strategy: str,
        applied: bool,
        escalation_note: str,
        machine_payload_json: dict[str, Any] | None = None,
    ) -> None:
        """Persist or buffer a fallback policy decision as a stage event."""

        assert self.run_id is not None
        payload = {
            "stage_name": stage_name.value,
            "attempt_number": attempt_number,
            "reason": sanitize_diagnostic_text(reason),
            "fallback_strategy": fallback_strategy,
            "applied": applied,
            "escalation_note": sanitize_diagnostic_text(escalation_note),
            "machine_payload_json": sanitize_value(machine_payload_json or {}),
        }
        self.fallback_decisions.append(payload)
        self.record_stage_event(
            stage_name=stage_name,
            status=StageStatus.FALLBACK_APPLIED if applied else StageStatus.SKIPPED,
            attempt_number=attempt_number,
            message=(
                f"Fallback decision for {stage_name.value}: "
                f"{fallback_strategy}; applied={applied}."
            ),
            machine_payload_json={
                **(machine_payload_json or {}),
                "reason": reason,
                "fallback_strategy": fallback_strategy,
                "applied": applied,
                "escalation_note": escalation_note,
            },
        )

    def finalize_run(
        self,
        *,
        status: PipelineStatus,
        duration_ms: int | None,
        final_error_code: str | None = None,
        final_error_message: str | None = None,
    ) -> None:
        """Finalize a pipeline run aggregate."""

        assert self.run_id is not None
        if self.repository is not None:
            from backend.app.db.repositories.orchestration_repository import PipelineRunUpdate

            self.repository.update_pipeline_run(
                self.run_id,
                PipelineRunUpdate(
                    status=status,
                    completed_at=datetime.now(timezone.utc),
                    duration_ms=duration_ms,
                    final_error_code=final_error_code,
                    final_error_message=(
                        sanitize_diagnostic_text(final_error_message)
                        if final_error_message is not None
                        else None
                    ),
                ),
            )
        if self.event_emitter is not None:
            self.event_emitter.emit_run_finished(
                run_id=self.run_id,
                status=status,
                final_error_code=final_error_code,
            )

    def record_safe_fallback(
        self,
        *,
        stage_name: StageName,
        fallback_class: str,
        reason: str,
        final_output_downgraded: bool,
        attempt_number: int = 1,
        machine_payload_json: dict[str, Any] | None = None,
    ) -> None:
        """Record one explicit fallback execution with internal downgrade state."""

        assert self.run_id is not None
        payload = {
            "run_id": self.run_id,
            "stage_name": stage_name.value,
            "attempt_number": attempt_number,
            "fallback_class": fallback_class,
            "reason": sanitize_diagnostic_text(reason),
            "final_output_downgraded": final_output_downgraded,
            "machine_payload_json": build_fallback_audit_payload(
                fallback_class=fallback_class,
                reason=sanitize_diagnostic_text(reason),
                final_output_downgraded=final_output_downgraded,
                extra_metadata=sanitize_value(machine_payload_json or {}),
            ),
        }
        self.fallback_audits.append(payload)
        self.quality_downgraded = self.quality_downgraded or final_output_downgraded
        self.record_stage_event(
            stage_name=stage_name,
            status=StageStatus.FALLBACK_APPLIED,
            attempt_number=attempt_number,
            message=f"Safe fallback applied: {fallback_class}.",
            machine_payload_json=payload["machine_payload_json"],
        )
        log_event(
            logger,
            service="resume_optimizer.fallbacks",
            event_name="fallback_applied",
            outcome="success",
            run_id=self.run_id,
            stage_name=stage_name.value,
            metadata=payload["machine_payload_json"],
        )

    def run_diagnostics(self) -> dict[str, Any]:
        """Return concise internal diagnostics for the full pipeline run."""

        confidence_payload = (
            self.confidence_assessment.model_dump(mode="json")
            if self.confidence_assessment is not None
            else None
        )
        return {
            "fallback_count": len(self.fallback_audits),
            "fallback_classes": [item["fallback_class"] for item in self.fallback_audits],
            "quality_status": (
                self.confidence_assessment.final_confidence_level.value
                if self.confidence_assessment is not None
                else ("degraded" if self.quality_downgraded else "acceptable")
            ),
            "final_confidence_level": (
                self.confidence_assessment.final_confidence_level.value
                if self.confidence_assessment is not None
                else ("degraded" if self.quality_downgraded else "acceptable")
            ),
            "confidence_assessment": confidence_payload,
        }

    def set_confidence_assessment(self, assessment: RunConfidenceAssessment) -> None:
        """Persist the final internal confidence assessment for this run."""

        self.confidence_assessment = assessment
        self.quality_downgraded = assessment.final_confidence_level.value in {"degraded", "unsafe"}

    def commit(self) -> None:
        """Commit repository session when one is available."""

        if self.repository is None:
            return
        session = getattr(self.repository, "session", None)
        if session is not None:
            session.commit()

    def rollback(self) -> None:
        """Rollback repository session when one is available."""

        if self.repository is None:
            return
        session = getattr(self.repository, "session", None)
        if session is not None:
            session.rollback()


def build_default_pipeline_recorder() -> PipelineRunRecorder:
    """Create a recorder backed by DATABASE_URL when configured."""

    database_url = DEFAULT_SETTINGS.get_database_url()
    if not database_url:
        return PipelineRunRecorder(event_emitter=DEFAULT_PIPELINE_EVENT_EMITTER)
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from backend.app.db.repositories.orchestration_repository import OrchestrationRepository
    except ImportError as exc:
        raise OrchestrationError(
            "DATABASE_URL is configured but SQLAlchemy orchestration persistence is unavailable."
        ) from exc

    engine = create_engine(database_url)
    return PipelineRunRecorder(
        repository=OrchestrationRepository(Session(engine)),
        event_emitter=DEFAULT_PIPELINE_EVENT_EMITTER,
    )
