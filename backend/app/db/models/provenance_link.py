"""SQLAlchemy model for verification provenance links."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base
from backend.app.db.models.types import JsonList


class ProvenanceLinkModel(Base):
    """Persisted source-evidence link for one verified generated item."""

    __tablename__ = "provenance_links"
    __table_args__ = (
        Index("ix_provenance_links_item_id", "verification_item_id"),
        Index("ix_provenance_links_source_entity", "source_entity_type", "source_entity_id"),
        Index("ix_provenance_links_evidence_strength", "evidence_strength"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    verification_item_id: Mapped[str] = mapped_column(
        ForeignKey("verification_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_bullet_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(64), nullable=False)
    matched_tokens_json: Mapped[list[str]] = mapped_column(JsonList, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    verification_item = relationship("VerificationItemModel", back_populates="provenance_links")
