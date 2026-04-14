"""Repository for Phase 6 orchestration runs, events, artifacts, and outputs."""

from __future__ import annotations

from collections.abc import Protocol
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.pipeline_artifact import PipelineArtifactModel
from backend.app.db.models.pipeline_output import PipelineOutputModel
from backend.app.db.models.pipeline_run import PipelineRunModel
from backend.app.db.models.pipeline_stage_event import PipelineStageEventModel
from backend.app.db.models.retry_attempt import RetryAttemptModel
from backend.app.db.models.verification_issue import VerificationIssueModel
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus


def _enum_value(value: object) -> str:
    """Return enum values while accepting plain strings from callers."""

    raw_value = getattr(value, "value", value)
    return str(raw_value)


@dataclass(frozen=True, slots=True)
class PipelineRunCreate:
    """Input payload for creating a pipeline run."""

    id: str | None = None
    status: PipelineStatus | str = PipelineStatus.PENDING
    requested_template: str | None = None
    requested_mode: str | None = None
    job_description_hash: str | None = None
    source_profile_id: str | None = None
    started_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PipelineRunUpdate:
    """Mutable fields for updating a pipeline run aggregate."""

    status: PipelineStatus | str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    final_error_code: str | None = None
    final_error_message: str | None = None


@dataclass(frozen=True, slots=True)
class StageEventCreate:
    """Input payload for appending a pipeline stage event."""

    run_id: str
    stage_name: StageName | str
    status: StageStatus | str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    attempt_number: int = 1
    message: str | None = None
    machine_payload_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PipelineArtifactCreate:
    """Input payload for a pipeline artifact manifest entry."""

    run_id: str
    stage_name: StageName | str
    artifact_type: ArtifactKind | str
    storage_kind: str
    storage_path_or_key: str | None = None
    inline_json: dict[str, Any] | None = None
    content_hash: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineOutputCreate:
    """Input payload for final pipeline output metadata."""

    run_id: str
    compile_status: str
    pdf_path_or_storage_key: str | None = None
    latex_path_or_storage_key: str | None = None
    page_count: int | None = None
    output_metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PipelineVerificationIssueCreate:
    """Run-level verification issue payload for Phase 6 traceability."""

    run_id: str
    issue_type: str
    severity: str
    description: str
    output_item_ref: str | None = None
    source_refs_json: dict[str, Any] | None = None
    resolution_status: str = "open"
    category: str | None = None
    message: str | None = None
    verification_item_id: str | None = None
    details_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetryAttemptCreate:
    """Input payload for recording one retry attempt."""

    run_id: str
    stage_name: StageName | str
    attempt_number: int
    reason: str
    retry_strategy: str
    result_status: StageStatus | str


class OrchestrationRepositoryProtocol(Protocol):
    """Typed persistence interface consumed by Phase 6 services."""

    def create_pipeline_run(self, payload: PipelineRunCreate) -> PipelineRunModel:
        """Create and flush a pipeline run."""

    def update_pipeline_run(self, run_id: str, payload: PipelineRunUpdate) -> PipelineRunModel:
        """Update and flush a pipeline run."""

    def add_stage_event(self, payload: StageEventCreate) -> PipelineStageEventModel:
        """Append and flush a stage event."""

    def add_artifact(self, payload: PipelineArtifactCreate) -> PipelineArtifactModel:
        """Append and flush an artifact manifest entry."""

    def add_output(self, payload: PipelineOutputCreate) -> PipelineOutputModel:
        """Create and flush a final output row."""

    def add_verification_issue(
        self,
        payload: PipelineVerificationIssueCreate,
    ) -> VerificationIssueModel:
        """Append and flush a run-level verification issue."""

    def add_retry_attempt(self, payload: RetryAttemptCreate) -> RetryAttemptModel:
        """Append and flush one retry attempt."""


class OrchestrationRepository:
    """SQLAlchemy persistence API for Phase 6 orchestration records."""

    def __init__(self, session: Session) -> None:
        """Create a repository bound to a SQLAlchemy session."""

        self.session = session

    def create_pipeline_run(self, payload: PipelineRunCreate) -> PipelineRunModel:
        """Create and flush a new pipeline run."""

        values: dict[str, object | None] = {
            "status": _enum_value(payload.status),
            "requested_template": payload.requested_template,
            "requested_mode": payload.requested_mode,
            "job_description_hash": payload.job_description_hash,
            "source_profile_id": payload.source_profile_id,
            "started_at": payload.started_at,
        }
        if payload.id is not None:
            values["id"] = payload.id
        run = PipelineRunModel(**values)
        self.session.add(run)
        self.session.flush()
        return run

    def update_pipeline_run(self, run_id: str, payload: PipelineRunUpdate) -> PipelineRunModel:
        """Update aggregate run fields and flush."""

        run = self.get_pipeline_run_or_raise(run_id)
        if payload.status is not None:
            run.status = _enum_value(payload.status)
        if payload.started_at is not None:
            run.started_at = payload.started_at
        if payload.completed_at is not None:
            run.completed_at = payload.completed_at
        if payload.duration_ms is not None:
            run.duration_ms = payload.duration_ms
        if payload.final_error_code is not None:
            run.final_error_code = payload.final_error_code
        if payload.final_error_message is not None:
            run.final_error_message = payload.final_error_message
        self.session.flush()
        return run

    def add_stage_event(self, payload: StageEventCreate) -> PipelineStageEventModel:
        """Create and flush a stage lifecycle event."""

        self.get_pipeline_run_or_raise(payload.run_id)
        event = PipelineStageEventModel(
            run_id=payload.run_id,
            stage_name=_enum_value(payload.stage_name),
            status=_enum_value(payload.status),
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            duration_ms=payload.duration_ms,
            attempt_number=payload.attempt_number,
            message=payload.message,
            machine_payload_json=payload.machine_payload_json,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def add_artifact(self, payload: PipelineArtifactCreate) -> PipelineArtifactModel:
        """Create and flush an artifact manifest entry."""

        self.get_pipeline_run_or_raise(payload.run_id)
        artifact = PipelineArtifactModel(
            run_id=payload.run_id,
            stage_name=_enum_value(payload.stage_name),
            artifact_type=_enum_value(payload.artifact_type),
            storage_kind=payload.storage_kind,
            storage_path_or_key=payload.storage_path_or_key,
            inline_json=payload.inline_json,
            content_hash=payload.content_hash,
        )
        self.session.add(artifact)
        self.session.flush()
        return artifact

    def add_output(self, payload: PipelineOutputCreate) -> PipelineOutputModel:
        """Create and flush final output metadata for a run."""

        self.get_pipeline_run_or_raise(payload.run_id)
        output = PipelineOutputModel(
            run_id=payload.run_id,
            pdf_path_or_storage_key=payload.pdf_path_or_storage_key,
            latex_path_or_storage_key=payload.latex_path_or_storage_key,
            page_count=payload.page_count,
            compile_status=payload.compile_status,
            output_metadata_json=payload.output_metadata_json,
        )
        self.session.add(output)
        self.session.flush()
        return output

    def add_verification_issue(
        self,
        payload: PipelineVerificationIssueCreate,
    ) -> VerificationIssueModel:
        """Create and flush a run-level verification issue.

        The existing verification issue table remains compatible with Phase 4
        item-level issues while also carrying Phase 6 run-level trace fields.
        """

        self.get_pipeline_run_or_raise(payload.run_id)
        issue_type = payload.category or payload.issue_type
        description = payload.message or payload.description
        issue = VerificationIssueModel(
            verification_item_id=payload.verification_item_id,
            run_id=payload.run_id,
            category=issue_type,
            severity=payload.severity,
            message=description,
            output_item_ref=payload.output_item_ref,
            issue_type=payload.issue_type,
            description=payload.description,
            source_refs_json=payload.source_refs_json,
            resolution_status=payload.resolution_status,
            details_json=payload.details_json,
        )
        self.session.add(issue)
        self.session.flush()
        return issue

    def add_retry_attempt(self, payload: RetryAttemptCreate) -> RetryAttemptModel:
        """Create and flush one retry attempt record."""

        self.get_pipeline_run_or_raise(payload.run_id)
        retry = RetryAttemptModel(
            run_id=payload.run_id,
            stage_name=_enum_value(payload.stage_name),
            attempt_number=payload.attempt_number,
            reason=payload.reason,
            retry_strategy=payload.retry_strategy,
            result_status=_enum_value(payload.result_status),
        )
        self.session.add(retry)
        self.session.flush()
        return retry

    def get_pipeline_run(self, run_id: str) -> PipelineRunModel | None:
        """Return a pipeline run with core relationships loaded."""

        return self.session.scalar(
            select(PipelineRunModel)
            .where(PipelineRunModel.id == run_id)
            .options(
                selectinload(PipelineRunModel.stage_events),
                selectinload(PipelineRunModel.artifacts),
                selectinload(PipelineRunModel.outputs),
                selectinload(PipelineRunModel.retry_attempts),
                selectinload(PipelineRunModel.verification_issues),
            )
        )

    def get_pipeline_run_or_raise(self, run_id: str) -> PipelineRunModel:
        """Return a pipeline run by id or raise for invalid repository usage."""

        run = self.session.get(PipelineRunModel, run_id)
        if run is None:
            raise ValueError(f"pipeline run not found: {run_id}")
        return run
