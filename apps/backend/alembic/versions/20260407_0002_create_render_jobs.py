"""create render job diagnostics table

Revision ID: 20260407_0002
Revises: 20260407_0001
Create Date: 2026-04-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260407_0002"
down_revision: str | None = "20260407_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create render job diagnostics table."""

    op.create_table(
        "render_jobs",
        sa.Column("render_job_id", sa.String(length=128), nullable=False),
        sa.Column("template_id", sa.String(length=128), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=True),
        sa.Column(
            "compile_success",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("render_status", sa.String(length=64), nullable=False),
        sa.Column("warnings_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("errors_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("page_policy", sa.String(length=64), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("output_pdf_reference", sa.String(length=512), nullable=True),
        sa.Column("output_tex_reference", sa.String(length=512), nullable=True),
        sa.Column("output_log_reference", sa.String(length=512), nullable=True),
        sa.Column(
            "section_stats_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "truncation_decisions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "compile_diagnostics_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "placeholder_fill_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "artifact_refs_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("render_job_id"),
    )
    op.create_index("ix_render_jobs_status", "render_jobs", ["render_status"])
    op.create_index(
        "ix_render_jobs_template",
        "render_jobs",
        ["template_id", "template_version"],
    )
    op.create_index("ix_render_jobs_created_at", "render_jobs", ["created_at"])


def downgrade() -> None:
    """Drop render job diagnostics table."""

    op.drop_index("ix_render_jobs_created_at", table_name="render_jobs")
    op.drop_index("ix_render_jobs_template", table_name="render_jobs")
    op.drop_index("ix_render_jobs_status", table_name="render_jobs")
    op.drop_table("render_jobs")
