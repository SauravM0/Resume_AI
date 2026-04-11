"""SQLAlchemy model for Phase 6 final pipeline outputs."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base
from backend.app.db.models.types import JsonDict


class PipelineOutputModel(Base):
    """Final generated output record for a completed or partially completed run."""

    __tablename__ = "pipeline_outputs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_pipeline_outputs_run_id"),
        Index("ix_pipeline_outputs_run_id", "run_id"),
        Index("ix_pipeline_outputs_compile_status", "compile_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    pdf_path_or_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    latex_path_or_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compile_status: Mapped[str] = mapped_column(String(64), nullable=False)
    output_metadata_json: Mapped[dict[str, object]] = mapped_column(
        JsonDict,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pipeline_run = relationship("PipelineRunModel", back_populates="outputs")
