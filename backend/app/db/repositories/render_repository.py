"""Repository for Phase 5 render diagnostics persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.models.render_job import RenderJobModel


class RenderDiagnosticsRepository:
    """Persistence API for render job metadata and diagnostics."""

    def __init__(self, session: Session) -> None:
        """Create a repository bound to a SQLAlchemy session."""

        self.session = session

    def create_render_job(
        self,
        *,
        render_job_id: str,
        template_id: str,
        template_version: str | None = None,
        render_status: str = "started",
        page_policy: str | None = None,
        artifact_refs_json: dict[str, Any] | None = None,
    ) -> RenderJobModel:
        """Create and flush a render job metadata record."""

        render_job = RenderJobModel(
            render_job_id=render_job_id,
            template_id=template_id,
            template_version=template_version,
            render_status=render_status,
            page_policy=page_policy,
            artifact_refs_json=artifact_refs_json or {},
        )
        self.session.add(render_job)
        self.session.flush()
        return render_job

    def update_render_job(
        self,
        *,
        render_job_id: str,
        render_status: str,
        compile_success: bool,
        warnings_count: int,
        errors_count: int,
        elapsed_ms: int | None = None,
        output_pdf_reference: str | None = None,
        output_tex_reference: str | None = None,
        output_log_reference: str | None = None,
        section_stats_json: list[dict[str, Any]] | None = None,
        truncation_decisions_json: list[dict[str, Any]] | None = None,
        compile_diagnostics_json: dict[str, Any] | None = None,
        placeholder_fill_json: dict[str, Any] | None = None,
        artifact_refs_json: dict[str, Any] | None = None,
    ) -> RenderJobModel:
        """Update and flush render job result metadata."""

        render_job = self.get_render_job_or_raise(render_job_id)
        render_job.render_status = render_status
        render_job.compile_success = compile_success
        render_job.warnings_count = warnings_count
        render_job.errors_count = errors_count
        render_job.elapsed_ms = elapsed_ms
        render_job.output_pdf_reference = output_pdf_reference
        render_job.output_tex_reference = output_tex_reference
        render_job.output_log_reference = output_log_reference
        render_job.section_stats_json = section_stats_json or []
        render_job.truncation_decisions_json = truncation_decisions_json or []
        render_job.compile_diagnostics_json = compile_diagnostics_json or {}
        render_job.placeholder_fill_json = placeholder_fill_json or {}
        render_job.artifact_refs_json = artifact_refs_json or {}
        self.session.flush()
        return render_job

    def get_render_job_or_raise(self, render_job_id: str) -> RenderJobModel:
        """Return a render job by id or raise for invalid repository usage."""

        render_job = self.session.get(RenderJobModel, render_job_id)
        if render_job is None:
            raise ValueError(f"render job not found: {render_job_id}")
        return render_job
