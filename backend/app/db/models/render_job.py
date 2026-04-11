"""SQLAlchemy model for Phase 5 render job diagnostics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.models.base import Base
from backend.app.db.models.types import JsonDict, JsonList


class RenderJobModel(Base):
    """Durable metadata record for one Phase 5 render execution."""

    __tablename__ = "render_jobs"
    __table_args__ = (
        Index("ix_render_jobs_status", "render_status"),
        Index("ix_render_jobs_template", "template_id", "template_version"),
        Index("ix_render_jobs_created_at", "created_at"),
    )

    render_job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    template_id: Mapped[str] = mapped_column(String(128), nullable=False)
    template_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    compile_success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    render_status: Mapped[str] = mapped_column(String(64), nullable=False)
    warnings_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    errors_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    page_policy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_pdf_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_tex_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_log_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    section_stats_json: Mapped[list[dict[str, object]]] = mapped_column(
        JsonList,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    truncation_decisions_json: Mapped[list[dict[str, object]]] = mapped_column(
        JsonList,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    compile_diagnostics_json: Mapped[dict[str, object]] = mapped_column(
        JsonDict,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    placeholder_fill_json: Mapped[dict[str, object]] = mapped_column(
        JsonDict,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    artifact_refs_json: Mapped[dict[str, object]] = mapped_column(
        JsonDict,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
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
