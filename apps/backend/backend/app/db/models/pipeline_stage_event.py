"""SQLAlchemy model for Phase 6 stage lifecycle events."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base
from backend.app.db.models.types import JsonDict


class PipelineStageEventModel(Base):
    """Persisted status event for one stage attempt within a pipeline run."""

    __tablename__ = "pipeline_stage_events"
    __table_args__ = (
        Index("ix_pipeline_stage_events_run_id", "run_id"),
        Index("ix_pipeline_stage_events_stage_name", "stage_name"),
        Index("ix_pipeline_stage_events_status", "status"),
        Index("ix_pipeline_stage_events_run_stage_attempt", "run_id", "stage_name", "attempt_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    machine_payload_json: Mapped[dict[str, object]] = mapped_column(
        JsonDict,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pipeline_run = relationship("PipelineRunModel", back_populates="stage_events")
