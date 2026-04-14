"""SQLAlchemy model for Phase 6 persisted artifact references."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base
from backend.app.db.models.types import JsonDict


class PipelineArtifactModel(Base):
    """Artifact manifest entry for a stage output or final result."""

    __tablename__ = "pipeline_artifacts"
    __table_args__ = (
        Index("ix_pipeline_artifacts_run_id", "run_id"),
        Index("ix_pipeline_artifacts_stage_name", "stage_name"),
        Index("ix_pipeline_artifacts_artifact_type", "artifact_type"),
        Index("ix_pipeline_artifacts_storage_kind", "storage_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path_or_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    inline_json: Mapped[dict[str, object] | None] = mapped_column(JsonDict, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pipeline_run = relationship("PipelineRunModel", back_populates="artifacts")
