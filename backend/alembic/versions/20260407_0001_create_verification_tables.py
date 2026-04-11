"""create verification persistence tables

Revision ID: 20260407_0001
Revises:
Create Date: 2026-04-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260407_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create normalized verification tables and supporting indexes."""

    op.create_table(
        "verification_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("generation_id", sa.String(length=128), nullable=True),
        sa.Column("pipeline_run_id", sa.String(length=128), nullable=True),
        sa.Column("candidate_id", sa.String(length=128), nullable=True),
        sa.Column("job_id", sa.String(length=128), nullable=True),
        sa.Column("jd_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("overall_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fallback_applied", sa.Boolean(), nullable=False),
        sa.Column("summary_status", sa.String(length=64), nullable=True),
        sa.Column("raw_artifact_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_runs_status", "verification_runs", ["status"])
    op.create_index("ix_verification_runs_generation_id", "verification_runs", ["generation_id"])
    op.create_index("ix_verification_runs_pipeline_run_id", "verification_runs", ["pipeline_run_id"])
    op.create_index("ix_verification_runs_candidate_id", "verification_runs", ["candidate_id"])
    op.create_index("ix_verification_runs_job_id", "verification_runs", ["job_id"])
    op.create_index("ix_verification_runs_jd_hash", "verification_runs", ["jd_hash"])

    op.create_table(
        "verification_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("verification_run_id", sa.String(length=64), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("item_key", sa.String(length=128), nullable=False),
        sa.Column("generated_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("fallback_action", sa.String(length=64), nullable=False),
        sa.Column("evidence_strength", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["verification_run_id"], ["verification_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verification_run_id", "item_key", name="uq_verification_items_run_item_key"),
    )
    op.create_index("ix_verification_items_run_id", "verification_items", ["verification_run_id"])
    op.create_index("ix_verification_items_status", "verification_items", ["status"])
    op.create_index("ix_verification_items_item_type", "verification_items", ["item_type"])

    op.create_table(
        "verification_issues",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("verification_item_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_span_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generated_span_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["verification_item_id"], ["verification_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_issues_item_id", "verification_issues", ["verification_item_id"])
    op.create_index("ix_verification_issues_category", "verification_issues", ["category"])
    op.create_index("ix_verification_issues_severity", "verification_issues", ["severity"])

    op.create_table(
        "provenance_links",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("verification_item_id", sa.String(length=64), nullable=False),
        sa.Column("source_entity_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=128), nullable=False),
        sa.Column("source_bullet_id", sa.String(length=128), nullable=True),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_strength", sa.String(length=64), nullable=False),
        sa.Column("matched_tokens_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["verification_item_id"], ["verification_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provenance_links_item_id", "provenance_links", ["verification_item_id"])
    op.create_index(
        "ix_provenance_links_source_entity",
        "provenance_links",
        ["source_entity_type", "source_entity_id"],
    )
    op.create_index("ix_provenance_links_evidence_strength", "provenance_links", ["evidence_strength"])


def downgrade() -> None:
    """Drop verification persistence tables in dependency order."""

    op.drop_index("ix_provenance_links_evidence_strength", table_name="provenance_links")
    op.drop_index("ix_provenance_links_source_entity", table_name="provenance_links")
    op.drop_index("ix_provenance_links_item_id", table_name="provenance_links")
    op.drop_table("provenance_links")

    op.drop_index("ix_verification_issues_severity", table_name="verification_issues")
    op.drop_index("ix_verification_issues_category", table_name="verification_issues")
    op.drop_index("ix_verification_issues_item_id", table_name="verification_issues")
    op.drop_table("verification_issues")

    op.drop_index("ix_verification_items_item_type", table_name="verification_items")
    op.drop_index("ix_verification_items_status", table_name="verification_items")
    op.drop_index("ix_verification_items_run_id", table_name="verification_items")
    op.drop_table("verification_items")

    op.drop_index("ix_verification_runs_jd_hash", table_name="verification_runs")
    op.drop_index("ix_verification_runs_job_id", table_name="verification_runs")
    op.drop_index("ix_verification_runs_candidate_id", table_name="verification_runs")
    op.drop_index("ix_verification_runs_pipeline_run_id", table_name="verification_runs")
    op.drop_index("ix_verification_runs_generation_id", table_name="verification_runs")
    op.drop_index("ix_verification_runs_status", table_name="verification_runs")
    op.drop_table("verification_runs")
