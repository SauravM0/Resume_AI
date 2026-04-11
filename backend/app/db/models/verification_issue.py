"""SQLAlchemy model for item-level verification issues."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base
from backend.app.db.models.types import JsonDict


class VerificationIssueModel(Base):
    """Persisted verifier finding tied to a generated item."""

    __tablename__ = "verification_issues"
    __table_args__ = (
        Index("ix_verification_issues_item_id", "verification_item_id"),
        Index("ix_verification_issues_run_id", "run_id"),
        Index("ix_verification_issues_category", "category"),
        Index("ix_verification_issues_severity", "severity"),
        Index("ix_verification_issues_resolution_status", "resolution_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    verification_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("verification_items.id", ondelete="CASCADE"),
        nullable=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    output_item_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    issue_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_refs_json: Mapped[dict[str, object] | None] = mapped_column(JsonDict, nullable=True)
    resolution_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_span_json: Mapped[dict[str, object] | None] = mapped_column(JsonDict, nullable=True)
    generated_span_json: Mapped[dict[str, object] | None] = mapped_column(JsonDict, nullable=True)
    details_json: Mapped[dict[str, object]] = mapped_column(JsonDict, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    verification_item = relationship("VerificationItemModel", back_populates="issues")
    pipeline_run = relationship("PipelineRunModel", back_populates="verification_issues")
