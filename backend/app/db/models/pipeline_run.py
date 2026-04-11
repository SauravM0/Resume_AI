"""SQLAlchemy model for Phase 6 end-to-end pipeline runs."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base


class PipelineRunModel(Base):
    """Durable aggregate record for one resume generation request."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index("ix_pipeline_runs_status", "status"),
        Index("ix_pipeline_runs_source_profile_id", "source_profile_id"),
        Index("ix_pipeline_runs_job_description_hash", "job_description_hash"),
        Index("ix_pipeline_runs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_template: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_description_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_profile_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    final_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    stage_events = relationship(
        "PipelineStageEventModel",
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        order_by="PipelineStageEventModel.created_at",
    )
    artifacts = relationship(
        "PipelineArtifactModel",
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        order_by="PipelineArtifactModel.created_at",
    )
    outputs = relationship(
        "PipelineOutputModel",
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        order_by="PipelineOutputModel.created_at",
    )
    retry_attempts = relationship(
        "RetryAttemptModel",
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        order_by="RetryAttemptModel.created_at",
    )
    verification_issues = relationship(
        "VerificationIssueModel",
        back_populates="pipeline_run",
        order_by="VerificationIssueModel.created_at",
    )
