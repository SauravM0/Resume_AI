"""SQLAlchemy model for generated items evaluated during verification."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base


class VerificationItemModel(Base):
    """Persisted verification result for one generated resume item."""

    __tablename__ = "verification_items"
    __table_args__ = (
        UniqueConstraint("verification_run_id", "item_key", name="uq_verification_items_run_item_key"),
        Index("ix_verification_items_run_id", "verification_run_id"),
        Index("ix_verification_items_status", "status"),
        Index("ix_verification_items_item_type", "item_type"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    verification_run_id: Mapped[str] = mapped_column(
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_type: Mapped[str] = mapped_column(String(64), nullable=False)
    item_key: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    fallback_action: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    verification_run = relationship("VerificationRunModel", back_populates="items")
    issues = relationship(
        "VerificationIssueModel",
        back_populates="verification_item",
        cascade="all, delete-orphan",
        order_by="VerificationIssueModel.created_at",
    )
    provenance_links = relationship(
        "ProvenanceLinkModel",
        back_populates="verification_item",
        cascade="all, delete-orphan",
        order_by="ProvenanceLinkModel.created_at",
    )
