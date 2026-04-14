"""Serializable stage metrics records."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from resume_optimizer.models import StrictModel


class StageMetricRecord(StrictModel):
    """One terminal timing record for one request stage."""

    request_id: str | None = None
    run_id: str | None = None
    stage_name: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    success: bool
    failure_type: str | None = None
    retry_count: int = 0
    fallback_used: bool = False
    output_metadata: dict[str, object] = Field(default_factory=dict)
