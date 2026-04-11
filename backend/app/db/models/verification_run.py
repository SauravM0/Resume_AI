"""SQLAlchemy model for persisted verification run records."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base
from backend.app.db.models.types import JsonDict


class VerificationRunModel(Base):
    """Durable aggregate record for one Phase 4 verification execution."""

    __tablename__ = "verification_runs"
    __table_args__ = (
        Index("ix_verification_runs_status", "status"),
        Index("ix_verification_runs_generation_id", "generation_id"),
        Index("ix_verification_runs_pipeline_run_id", "pipeline_run_id"),
        Index("ix_verification_runs_candidate_id", "candidate_id"),
        Index("ix_verification_runs_job_id", "job_id"),
        Index("ix_verification_runs_jd_hash", "jd_hash"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    generation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    jd_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fallback_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_artifact_refs: Mapped[dict[str, object]] = mapped_column(
        JsonDict,
        nullable=False,
        default=dict,
    )

    items = relationship(
        "VerificationItemModel",
        back_populates="verification_run",
        cascade="all, delete-orphan",
        order_by="VerificationItemModel.created_at",
    )
