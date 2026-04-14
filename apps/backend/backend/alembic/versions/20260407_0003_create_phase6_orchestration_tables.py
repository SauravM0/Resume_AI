"""create phase 6 orchestration tables

Revision ID: 20260407_0003
Revises: 20260407_0002
Create Date: 2026-04-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260407_0003"
down_revision: str | None = "20260407_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create orchestration tables and extend verification issues for run tracing."""

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("requested_template", sa.String(length=128), nullable=True),
        sa.Column("requested_mode", sa.String(length=64), nullable=True),
        sa.Column("job_description_hash", sa.String(length=128), nullable=True),
        sa.Column("source_profile_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("final_error_code", sa.String(length=128), nullable=True),
        sa.Column("final_error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])
    op.create_index("ix_pipeline_runs_source_profile_id", "pipeline_runs", ["source_profile_id"])
    op.create_index("ix_pipeline_runs_job_description_hash", "pipeline_runs", ["job_description_hash"])
    op.create_index("ix_pipeline_runs_created_at", "pipeline_runs", ["created_at"])

    op.create_table(
        "pipeline_stage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("stage_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "machine_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_stage_events_run_id", "pipeline_stage_events", ["run_id"])
    op.create_index("ix_pipeline_stage_events_stage_name", "pipeline_stage_events", ["stage_name"])
    op.create_index("ix_pipeline_stage_events_status", "pipeline_stage_events", ["status"])
    op.create_index(
        "ix_pipeline_stage_events_run_stage_attempt",
        "pipeline_stage_events",
        ["run_id", "stage_name", "attempt_number"],
    )

    op.create_table(
        "pipeline_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("stage_name", sa.String(length=128), nullable=False),
        sa.Column("artifact_type", sa.String(length=128), nullable=False),
        sa.Column("storage_kind", sa.String(length=64), nullable=False),
        sa.Column("storage_path_or_key", sa.String(length=1024), nullable=True),
        sa.Column("inline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_artifacts_run_id", "pipeline_artifacts", ["run_id"])
    op.create_index("ix_pipeline_artifacts_stage_name", "pipeline_artifacts", ["stage_name"])
    op.create_index("ix_pipeline_artifacts_artifact_type", "pipeline_artifacts", ["artifact_type"])
    op.create_index("ix_pipeline_artifacts_storage_kind", "pipeline_artifacts", ["storage_kind"])

    op.create_table(
        "pipeline_outputs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("pdf_path_or_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("latex_path_or_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("compile_status", sa.String(length=64), nullable=False),
        sa.Column(
            "output_metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_pipeline_outputs_run_id"),
    )
    op.create_index("ix_pipeline_outputs_run_id", "pipeline_outputs", ["run_id"])
    op.create_index("ix_pipeline_outputs_compile_status", "pipeline_outputs", ["compile_status"])

    op.create_table(
        "retry_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("stage_name", sa.String(length=128), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("retry_strategy", sa.String(length=128), nullable=False),
        sa.Column("result_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retry_attempts_run_id", "retry_attempts", ["run_id"])
    op.create_index("ix_retry_attempts_stage_name", "retry_attempts", ["stage_name"])
    op.create_index(
        "ix_retry_attempts_run_stage_attempt",
        "retry_attempts",
        ["run_id", "stage_name", "attempt_number"],
    )

    op.alter_column("verification_issues", "verification_item_id", nullable=True)
    op.add_column("verification_issues", sa.Column("run_id", sa.String(length=36), nullable=True))
    op.add_column("verification_issues", sa.Column("output_item_ref", sa.String(length=256), nullable=True))
    op.add_column("verification_issues", sa.Column("issue_type", sa.String(length=128), nullable=True))
    op.add_column("verification_issues", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "verification_issues",
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("verification_issues", sa.Column("resolution_status", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_verification_issues_run_id_pipeline_runs",
        "verification_issues",
        "pipeline_runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_verification_issues_run_id", "verification_issues", ["run_id"])
    op.create_index(
        "ix_verification_issues_resolution_status",
        "verification_issues",
        ["resolution_status"],
    )


def downgrade() -> None:
    """Drop orchestration tables and remove run-level issue extensions."""

    op.drop_index("ix_verification_issues_resolution_status", table_name="verification_issues")
    op.drop_index("ix_verification_issues_run_id", table_name="verification_issues")
    op.drop_constraint(
        "fk_verification_issues_run_id_pipeline_runs",
        "verification_issues",
        type_="foreignkey",
    )
    op.drop_column("verification_issues", "resolution_status")
    op.drop_column("verification_issues", "source_refs_json")
    op.drop_column("verification_issues", "description")
    op.drop_column("verification_issues", "issue_type")
    op.drop_column("verification_issues", "output_item_ref")
    op.drop_column("verification_issues", "run_id")
    op.alter_column("verification_issues", "verification_item_id", nullable=False)

    op.drop_index("ix_retry_attempts_run_stage_attempt", table_name="retry_attempts")
    op.drop_index("ix_retry_attempts_stage_name", table_name="retry_attempts")
    op.drop_index("ix_retry_attempts_run_id", table_name="retry_attempts")
    op.drop_table("retry_attempts")

    op.drop_index("ix_pipeline_outputs_compile_status", table_name="pipeline_outputs")
    op.drop_index("ix_pipeline_outputs_run_id", table_name="pipeline_outputs")
    op.drop_table("pipeline_outputs")

    op.drop_index("ix_pipeline_artifacts_storage_kind", table_name="pipeline_artifacts")
    op.drop_index("ix_pipeline_artifacts_artifact_type", table_name="pipeline_artifacts")
    op.drop_index("ix_pipeline_artifacts_stage_name", table_name="pipeline_artifacts")
    op.drop_index("ix_pipeline_artifacts_run_id", table_name="pipeline_artifacts")
    op.drop_table("pipeline_artifacts")

    op.drop_index("ix_pipeline_stage_events_run_stage_attempt", table_name="pipeline_stage_events")
    op.drop_index("ix_pipeline_stage_events_status", table_name="pipeline_stage_events")
    op.drop_index("ix_pipeline_stage_events_stage_name", table_name="pipeline_stage_events")
    op.drop_index("ix_pipeline_stage_events_run_id", table_name="pipeline_stage_events")
    op.drop_table("pipeline_stage_events")

    op.drop_index("ix_pipeline_runs_created_at", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_job_description_hash", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_source_profile_id", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
