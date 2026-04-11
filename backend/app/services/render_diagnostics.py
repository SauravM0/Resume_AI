# Render diagnostics matter because Phase 5 failures can come from templates,
# layout decisions, LaTeX compilation, or artifact handling, and those failures
# need to be debuggable after the request finishes. Artifact metadata should be
# persisted so later routes and operators can find PDFs, .tex files, and logs
# without storing large binary content in database rows. Privacy-aware logging is
# important for resumes because source content can contain sensitive employment
# and contact data; this module stores counts, statuses, references, and bounded
# diagnostic summaries instead of raw resume or job-description text.
"""Privacy-aware render diagnostics and artifact metadata persistence."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field
from sqlalchemy.orm import Session

from backend.app.db.models.render_job import RenderJobModel
from backend.app.db.repositories.render_repository import RenderDiagnosticsRepository
from backend.app.models.render_models import (
    CompileResult,
    RenderFailure,
    RenderOutputStatus,
    RenderSectionStats,
    TargetPagePolicy,
)
from backend.app.services.document_assembler import AssembledDocument
from backend.app.services.layout_manager import LayoutPlanResult
from backend.app.services.pdf_compiler import PdfCompileResult
from backend.app.privacy import fingerprint_text
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel

MAX_DIAGNOSTIC_TEXT_CHARS = 2000


class RenderDiagnosticStatus(StrEnum):
    """Persisted lifecycle status for render diagnostics records."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class ArtifactReferences(StrictModel):
    """Privacy-safe references to generated render artifacts."""

    pdf: NonEmptyStr | None = None
    tex: NonEmptyStr | None = None
    log: NonEmptyStr | None = None


class RenderDiagnosticsPayload(StrictModel):
    """Persistence-ready diagnostics payload with no raw resume content."""

    render_job_id: StableId
    template_id: NonEmptyStr
    template_version: NonEmptyStr | None = None
    compile_success: bool = False
    render_status: RenderDiagnosticStatus = RenderDiagnosticStatus.STARTED
    warnings_count: int = Field(default=0, ge=0)
    errors_count: int = Field(default=0, ge=0)
    page_policy: NonEmptyStr | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    artifact_references: ArtifactReferences = Field(default_factory=ArtifactReferences)
    section_stats: list[dict[str, Any]] = Field(default_factory=list)
    truncation_decisions: list[dict[str, Any]] = Field(default_factory=list)
    compile_diagnostics_summary: dict[str, Any] = Field(default_factory=dict)
    placeholder_fill_info: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ArtifactReferences",
    "RenderDiagnosticStatus",
    "RenderDiagnosticsPayload",
    "build_render_diagnostics_payload",
    "record_render_failure",
    "record_render_job_result",
    "record_render_job_start",
]


def record_render_job_start(
    session: Session,
    *,
    render_job_id: str,
    template_id: str,
    template_version: str | None = None,
    page_policy: TargetPagePolicy | str | None = None,
    artifact_references: ArtifactReferences | None = None,
) -> RenderJobModel:
    """Persist a render job start record with metadata only."""

    repository = RenderDiagnosticsRepository(session)
    refs = artifact_references or ArtifactReferences()
    return repository.create_render_job(
        render_job_id=render_job_id,
        template_id=template_id,
        template_version=template_version,
        render_status=RenderDiagnosticStatus.STARTED.value,
        page_policy=_enum_value(page_policy),
        artifact_refs_json=refs.model_dump(exclude_none=True),
    )


def record_render_job_result(
    session: Session,
    payload: RenderDiagnosticsPayload,
) -> RenderJobModel:
    """Persist the final render job result and diagnostic metadata."""

    repository = RenderDiagnosticsRepository(session)
    return repository.update_render_job(
        render_job_id=payload.render_job_id,
        render_status=payload.render_status.value,
        compile_success=payload.compile_success,
        warnings_count=payload.warnings_count,
        errors_count=payload.errors_count,
        elapsed_ms=payload.elapsed_ms,
        output_pdf_reference=payload.artifact_references.pdf,
        output_tex_reference=payload.artifact_references.tex,
        output_log_reference=payload.artifact_references.log,
        section_stats_json=payload.section_stats,
        truncation_decisions_json=payload.truncation_decisions,
        compile_diagnostics_json=payload.compile_diagnostics_summary,
        placeholder_fill_json=payload.placeholder_fill_info,
        artifact_refs_json=payload.artifact_references.model_dump(exclude_none=True),
    )


def record_render_failure(
    session: Session,
    *,
    render_job_id: str,
    template_id: str,
    template_version: str | None = None,
    page_policy: TargetPagePolicy | str | None = None,
    failures: list[RenderFailure] | None = None,
    warnings: list[str] | None = None,
    elapsed_ms: int | None = None,
) -> RenderJobModel:
    """Persist a failed render attempt with bounded diagnostic summaries."""

    failure_items = failures or []
    warning_items = warnings or []
    payload = RenderDiagnosticsPayload(
        render_job_id=render_job_id,
        template_id=template_id,
        template_version=template_version,
        compile_success=False,
        render_status=RenderDiagnosticStatus.FAILED,
        warnings_count=len(warning_items),
        errors_count=len(failure_items),
        page_policy=_enum_value(page_policy),
        elapsed_ms=elapsed_ms,
        compile_diagnostics_summary={
            "warnings": [_redacted_diagnostic_item(warning) for warning in warning_items],
            "failures": [_failure_to_dict(failure) for failure in failure_items],
        },
    )
    _ensure_render_job_exists(session, payload)
    return record_render_job_result(session, payload)


def build_render_diagnostics_payload(
    *,
    render_job_id: str,
    template_id: str,
    template_version: str | None = None,
    page_policy: TargetPagePolicy | str | None = None,
    compile_result: PdfCompileResult | CompileResult | None = None,
    assembled_document: AssembledDocument | None = None,
    layout_result: LayoutPlanResult | None = None,
    section_stats: list[RenderSectionStats] | None = None,
    render_status: RenderOutputStatus | RenderDiagnosticStatus | str | None = None,
    artifact_references: ArtifactReferences | None = None,
) -> RenderDiagnosticsPayload:
    """Build a privacy-aware persistence payload from Phase 5 diagnostics."""

    refs = artifact_references or _artifact_refs_from_compile_result(compile_result)
    compile_success = _compile_success(compile_result)
    warnings = _warnings_from_compile_result(compile_result)
    errors = _errors_from_compile_result(compile_result)
    layout_warnings = layout_result.warnings if layout_result is not None else []
    placeholder_info = _placeholder_info(assembled_document)
    diagnostics_summary = _compile_diagnostics_summary(compile_result)

    all_warnings = [*warnings, *layout_warnings, *placeholder_info.get("warnings", [])]
    status = _resolve_render_status(render_status, compile_success, errors)
    effective_template_version = template_version
    if assembled_document is not None:
        effective_template_version = assembled_document.template_version

    return RenderDiagnosticsPayload(
        render_job_id=render_job_id,
        template_id=template_id,
        template_version=effective_template_version,
        compile_success=compile_success,
        render_status=status,
        warnings_count=len(all_warnings),
        errors_count=len(errors),
        page_policy=_enum_value(page_policy),
        elapsed_ms=_elapsed_ms_from_compile_result(compile_result),
        artifact_references=refs,
        section_stats=_section_stats_payload(section_stats, layout_result),
        truncation_decisions=_truncation_decisions_payload(layout_result),
        compile_diagnostics_summary=diagnostics_summary,
        placeholder_fill_info=placeholder_info,
    )


def _ensure_render_job_exists(
    session: Session,
    payload: RenderDiagnosticsPayload,
) -> None:
    """Create a start record if failure recording is called first."""

    repository = RenderDiagnosticsRepository(session)
    if session.get(RenderJobModel, payload.render_job_id) is not None:
        return
    repository.create_render_job(
        render_job_id=payload.render_job_id,
        template_id=payload.template_id,
        template_version=payload.template_version,
        render_status=RenderDiagnosticStatus.STARTED.value,
        page_policy=payload.page_policy,
        artifact_refs_json=payload.artifact_references.model_dump(exclude_none=True),
    )


def _resolve_render_status(
    render_status: RenderOutputStatus | RenderDiagnosticStatus | str | None,
    compile_success: bool,
    errors: list[str],
) -> RenderDiagnosticStatus:
    """Resolve diagnostic status from explicit status or compile state."""

    if render_status is not None:
        raw_status = _enum_value(render_status)
        if raw_status == RenderOutputStatus.SUCCEEDED.value:
            return RenderDiagnosticStatus.SUCCEEDED
        if raw_status == RenderOutputStatus.PARTIAL.value:
            return RenderDiagnosticStatus.PARTIAL
        if raw_status == RenderOutputStatus.FAILED.value:
            return RenderDiagnosticStatus.FAILED
        return RenderDiagnosticStatus(raw_status)
    if compile_success:
        return RenderDiagnosticStatus.SUCCEEDED
    if errors:
        return RenderDiagnosticStatus.FAILED
    return RenderDiagnosticStatus.PARTIAL


def _artifact_refs_from_compile_result(
    compile_result: PdfCompileResult | CompileResult | None,
) -> ArtifactReferences:
    """Extract artifact references without storing artifact content."""

    if compile_result is None:
        return ArtifactReferences()
    if isinstance(compile_result, PdfCompileResult):
        return ArtifactReferences(
            pdf=compile_result.pdf_file_path,
            tex=compile_result.tex_file_path,
            log=compile_result.log_file_path,
        )
    pdf_ref = _artifact_reference(compile_result.pdf_artifact)
    log_ref = _artifact_reference(compile_result.log_artifact)
    return ArtifactReferences(pdf=pdf_ref, log=log_ref)


def _compile_success(compile_result: PdfCompileResult | CompileResult | None) -> bool:
    """Return compile success from either compiler result type."""

    if compile_result is None:
        return False
    if isinstance(compile_result, PdfCompileResult):
        return compile_result.compile_success
    return compile_result.success


def _warnings_from_compile_result(
    compile_result: PdfCompileResult | CompileResult | None,
) -> list[dict[str, Any]]:
    """Extract bounded compiler warnings."""

    if compile_result is None:
        return []
    if isinstance(compile_result, PdfCompileResult):
        return [_redacted_diagnostic_item(warning) for warning in compile_result.warnings_detected]
    return [_redacted_diagnostic_item(warning) for warning in compile_result.warnings]


def _errors_from_compile_result(
    compile_result: PdfCompileResult | CompileResult | None,
) -> list[dict[str, Any]]:
    """Extract bounded compiler errors/failures."""

    if compile_result is None:
        return []
    if isinstance(compile_result, PdfCompileResult):
        if compile_result.errors_detected:
            return [_redacted_diagnostic_item(error) for error in compile_result.errors_detected]
        return [
            _redacted_diagnostic_item(failure.message)
            for failure in compile_result.compile_result.failures
        ]
    return [_redacted_diagnostic_item(failure.message) for failure in compile_result.failures]


def _compile_diagnostics_summary(
    compile_result: PdfCompileResult | CompileResult | None,
) -> dict[str, Any]:
    """Build a compile diagnostics JSON payload without raw document content."""

    if compile_result is None:
        return {}
    if isinstance(compile_result, PdfCompileResult):
        return {
            "return_code": compile_result.return_code,
            "elapsed_ms": compile_result.elapsed_ms,
            "stdout_available": compile_result.stdout_summary is not None,
            "stderr_available": compile_result.stderr_summary is not None,
            "stdout_char_count": _text_length(compile_result.stdout_summary),
            "stderr_char_count": _text_length(compile_result.stderr_summary),
            "warning_count": len(compile_result.warnings_detected),
            "error_count": len(compile_result.errors_detected),
            "warnings": [_redacted_diagnostic_item(warning) for warning in compile_result.warnings_detected],
            "errors": [_redacted_diagnostic_item(error) for error in compile_result.errors_detected],
            "failures": [
                _failure_to_dict(failure)
                for failure in compile_result.compile_result.failures
            ],
        }
    return {
        "return_code": compile_result.exit_code,
        "stdout_available": compile_result.stdout_excerpt is not None,
        "stderr_available": compile_result.stderr_excerpt is not None,
        "stdout_char_count": _text_length(compile_result.stdout_excerpt),
        "stderr_char_count": _text_length(compile_result.stderr_excerpt),
        "warning_count": len(compile_result.warnings),
        "warnings": [_redacted_diagnostic_item(warning) for warning in compile_result.warnings],
        "failures": [_failure_to_dict(failure) for failure in compile_result.failures],
    }


def _placeholder_info(
    assembled_document: AssembledDocument | None,
) -> dict[str, Any]:
    """Build placeholder fill diagnostics without document content."""

    if assembled_document is None:
        return {}
    diagnostics = assembled_document.diagnostics
    return {
        "template_id": diagnostics.template_id,
        "template_version": diagnostics.template_version,
        "placeholders_filled": [
            placeholder.value for placeholder in diagnostics.placeholders_filled
        ],
        "sections_omitted": [
            placeholder.value for placeholder in diagnostics.sections_omitted
        ],
        "warning_count": len(diagnostics.warnings),
        "warnings": [_redacted_diagnostic_item(warning) for warning in diagnostics.warnings],
    }


def _section_stats_payload(
    section_stats: list[RenderSectionStats] | None,
    layout_result: LayoutPlanResult | None,
) -> list[dict[str, Any]]:
    """Build section stats JSON from render stats or layout trim metadata."""

    if section_stats is not None:
        return [
            stat.model_dump(mode="json", exclude_none=True)
            for stat in section_stats
        ]
    if layout_result is None:
        return []
    return [
        metadata.model_dump(mode="json", exclude_none=True)
        for metadata in layout_result.section_trim_metadata
    ]


def _truncation_decisions_payload(
    layout_result: LayoutPlanResult | None,
) -> list[dict[str, Any]]:
    """Build truncation decision JSON from layout diagnostics."""

    if layout_result is None:
        return []
    return [
        decision.model_dump(mode="json", exclude_none=True)
        for decision in layout_result.truncation_decisions
    ]


def _failure_to_dict(failure: RenderFailure) -> dict[str, Any]:
    """Convert a render failure to a privacy-safe JSON object."""

    return {
        "code": failure.code,
        "message": _redacted_diagnostic_item(failure.message),
        "severity": failure.severity.value,
        "stage": failure.stage.value,
        "section_id": failure.section_id,
        "section_type": failure.section_type.value if failure.section_type else None,
        "item_id": failure.item_id,
        "retryable": failure.retryable,
    }


def _artifact_reference(artifact) -> str | None:
    """Return storage reference or local path for artifact metadata."""

    if artifact is None:
        return None
    return artifact.storage_ref or artifact.path


def _elapsed_ms_from_compile_result(
    compile_result: PdfCompileResult | CompileResult | None,
) -> int | None:
    """Return elapsed milliseconds when available."""

    if isinstance(compile_result, PdfCompileResult):
        return compile_result.elapsed_ms
    return None


def _enum_value(value) -> str | None:
    """Return enum value or string for persistence."""

    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _text_length(value: str | None) -> int:
    """Return optional text length without persisting the text itself."""

    if value is None:
        return 0
    return len(value)


def _truncate_text(value: str) -> str:
    """Bound diagnostic text size to avoid persisting raw content."""

    if len(value) <= MAX_DIAGNOSTIC_TEXT_CHARS:
        return value
    return value[:MAX_DIAGNOSTIC_TEXT_CHARS] + "...[truncated]"


def _redacted_diagnostic_item(value: str) -> dict[str, Any]:
    text = _truncate_text(value)
    return {
        "redacted": True,
        "char_count": len(text),
        "sha256_prefix": fingerprint_text(text).removeprefix("sha256:")[:12],
    }
