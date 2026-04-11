"""SQLAlchemy model for Phase 6 retry attempts."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base


class RetryAttemptModel(Base):
    """Record of one retry decision and result for a pipeline stage."""

    __tablename__ = "retry_attempts"
    __table_args__ = (
        Index("ix_retry_attempts_run_id", "run_id"),
        Index("ix_retry_attempts_stage_name", "stage_name"),
        Index("ix_retry_attempts_run_stage_attempt", "run_id", "stage_name", "attempt_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    retry_strategy: Mapped[str] = mapped_column(String(128), nullable=False)
    result_status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pipeline_run = relationship("PipelineRunModel", back_populates="retry_attempts")
