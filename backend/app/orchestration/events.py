"""Serializable progress events for Phase 6 orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import Field

from backend.app.orchestration.enums import StageName
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel


class PipelineProgressEventType(StrEnum):
    """Frontend-visible orchestration progress event types."""

    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    STAGE_PROGRESS = "stage_progress"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    RETRY_SCHEDULED = "retry_scheduled"
    FALLBACK_APPLIED = "fallback_applied"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class PipelineProgressEvent(StrictModel):
    """Safe event payload for logs, SSE, and frontend progress state."""

    event_id: StableId = Field(default_factory=lambda: f"event.{uuid4()}")
    run_id: StableId
    event_type: PipelineProgressEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stage_name: StageName | None = None
    human_message: NonEmptyStr
    machine_status: NonEmptyStr
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_log_payload(self) -> dict[str, Any]:
        """Return a structured log payload without sensitive stage content."""

        return self.model_dump(mode="json", exclude_none=True)
