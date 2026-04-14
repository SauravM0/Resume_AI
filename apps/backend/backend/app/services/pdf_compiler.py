# Compilation is isolated as its own service because converting a complete .tex
# document into a PDF has operational failure modes that are different from
# mapping, sanitization, layout, and template assembly. This service owns
# filesystem workspace setup, pdflatex execution, timeout handling, log capture,
# and PDF existence validation. Later services and routes can persist artifacts,
# show warnings/errors to users, or schedule cleanup using these diagnostics
# without needing to parse subprocess output themselves.
"""LaTeX PDF compilation service for Phase 5 rendering."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

from pydantic import Field, model_validator

from backend.app.models.render_models import (
    ArtifactKind,
    CompileResult,
    LatexCompiler,
    RenderArtifactMetadata,
    RenderFailure,
    RenderFailureSeverity,
    RenderFailureStage,
)
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel

DEFAULT_COMPILE_TIMEOUT_SECONDS = 45
DEFAULT_TEX_FILENAME = "resume.tex"
PDFLATEX_COMMAND = "pdflatex"
MAX_OUTPUT_SUMMARY_CHARS = 4000
MAX_DETECTED_MESSAGES = 25


class WorkspaceCleanupPolicy(StrEnum):
    """Workspace cleanup behavior after compile execution."""

    KEEP = "keep"
    CLEAN_ON_SUCCESS = "clean_on_success"
    CLEAN_ALWAYS = "clean_always"


class RenderWorkspace(StrictModel):
    """Filesystem workspace used for one LaTeX compilation attempt."""

    render_job_id: StableId
    workspace_path: NonEmptyStr


class PdfCompileResult(StrictModel):
    """Detailed PDF compiler result with filesystem diagnostics."""

    compile_success: bool
    render_job_id: StableId
    workspace_path: NonEmptyStr
    tex_file_path: NonEmptyStr
    pdf_file_path: NonEmptyStr | None = None
    log_file_path: NonEmptyStr | None = None
    stdout_summary: NonEmptyStr | None = None
    stderr_summary: NonEmptyStr | None = None
    return_code: int | None = None
    elapsed_ms: int = Field(ge=0)
    warnings_detected: list[NonEmptyStr] = Field(default_factory=list)
    errors_detected: list[NonEmptyStr] = Field(default_factory=list)
    compile_result: CompileResult

    @model_validator(mode="after")
    def validate_pdf_presence_on_success(self) -> "PdfCompileResult":
        """Never report compile success without a concrete PDF path."""

        if self.compile_success and self.pdf_file_path is None:
            raise ValueError("compile_success requires pdf_file_path")
        if self.compile_success != self.compile_result.success:
            raise ValueError("compile_success must match compile_result.success")
        return self


class PdflatexExecutionResult(StrictModel):
    """Raw subprocess result before PDF artifact validation."""

    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    elapsed_ms: int = Field(ge=0)
    timed_out: bool = False
    executable_missing: bool = False


__all__ = [
    "DEFAULT_COMPILE_TIMEOUT_SECONDS",
    "PDFLATEX_COMMAND",
    "PdfCompileResult",
    "PdflatexExecutionResult",
    "RenderWorkspace",
    "WorkspaceCleanupPolicy",
    "build_compile_result",
    "cleanup_render_workspace",
    "compile_tex_document",
    "create_render_workspace",
    "run_pdflatex",
    "verify_pdf_output",
    "write_tex_file",
]


def compile_tex_document(
    *,
    tex_content: str,
    render_job_id: str,
    template_id: str,
    workspace_root: Path | None = None,
    timeout_seconds: int | None = None,
    cleanup_policy: WorkspaceCleanupPolicy | None = None,
) -> PdfCompileResult:
    """Compile final assembled LaTeX content into a PDF artifact."""

    resolved_timeout_seconds = timeout_seconds or DEFAULT_SETTINGS.timeouts.pdf_compile_seconds
    resolved_cleanup_policy = cleanup_policy or WorkspaceCleanupPolicy(
        DEFAULT_SETTINGS.artifacts.compile_workspace_cleanup_policy
    )
    workspace = create_render_workspace(render_job_id, workspace_root=workspace_root)
    tex_file_path = write_tex_file(workspace, tex_content)
    execution_result = run_pdflatex(
        workspace,
        tex_file_path=tex_file_path,
        timeout_seconds=resolved_timeout_seconds,
    )
    pdf_file_path = verify_pdf_output(workspace, tex_file_path=tex_file_path)
    result = build_compile_result(
        render_job_id=render_job_id,
        template_id=template_id,
        workspace=workspace,
        tex_file_path=tex_file_path,
        pdf_file_path=pdf_file_path,
        execution_result=execution_result,
    )
    cleanup_render_workspace(
        workspace,
        resolved_cleanup_policy,
        compile_success=result.compile_success,
    )
    return result


def create_render_workspace(
    render_job_id: str,
    *,
    workspace_root: Path | None = None,
) -> RenderWorkspace:
    """Create a collision-resistant temporary workspace for one render job."""

    safe_job_id = _safe_workspace_token(render_job_id)
    prefix = f"resume-render-{safe_job_id}-{uuid4().hex[:12]}-"
    if workspace_root is not None:
        workspace_root.mkdir(parents=True, exist_ok=True)
    workspace_path = Path(
        tempfile.mkdtemp(prefix=prefix, dir=str(workspace_root) if workspace_root else None)
    )
    return RenderWorkspace(
        render_job_id=render_job_id,
        workspace_path=str(workspace_path),
    )


def write_tex_file(
    workspace: RenderWorkspace,
    tex_content: str,
    *,
    filename: str = DEFAULT_TEX_FILENAME,
) -> Path:
    """Write assembled .tex content into the render workspace."""

    if not tex_content.strip():
        raise ValueError("tex_content must not be empty")
    if Path(filename).name != filename or not filename.endswith(".tex"):
        raise ValueError("filename must be a simple .tex filename")

    workspace_path = Path(workspace.workspace_path)
    workspace_path.mkdir(parents=True, exist_ok=True)
    tex_file_path = workspace_path / filename
    tex_file_path.write_text(tex_content, encoding="utf-8")
    return tex_file_path


def run_pdflatex(
    workspace: RenderWorkspace,
    *,
    tex_file_path: Path,
    timeout_seconds: int = DEFAULT_COMPILE_TIMEOUT_SECONDS,
) -> PdflatexExecutionResult:
    """Run pdflatex once in nonstop diagnostic mode."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    workspace_path = Path(workspace.workspace_path)
    command = [
        PDFLATEX_COMMAND,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        tex_file_path.name,
    ]
    start_time = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            cwd=workspace_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = _elapsed_ms(start_time)
        return PdflatexExecutionResult(
            return_code=None,
            stdout=_coerce_process_output(exc.stdout),
            stderr=_coerce_process_output(exc.stderr),
            elapsed_ms=elapsed_ms,
            timed_out=True,
        )
    except FileNotFoundError as exc:
        elapsed_ms = _elapsed_ms(start_time)
        return PdflatexExecutionResult(
            return_code=None,
            stdout="",
            stderr=str(exc),
            elapsed_ms=elapsed_ms,
            executable_missing=True,
        )

    return PdflatexExecutionResult(
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        elapsed_ms=_elapsed_ms(start_time),
    )


def verify_pdf_output(
    workspace: RenderWorkspace,
    *,
    tex_file_path: Path,
) -> Path | None:
    """Return the expected PDF path only if pdflatex produced a non-empty PDF."""

    pdf_file_path = Path(workspace.workspace_path) / f"{tex_file_path.stem}.pdf"
    if not pdf_file_path.exists() or not pdf_file_path.is_file():
        return None
    if pdf_file_path.stat().st_size <= 0:
        return None
    return pdf_file_path


def build_compile_result(
    *,
    render_job_id: str,
    template_id: str,
    workspace: RenderWorkspace,
    tex_file_path: Path,
    pdf_file_path: Path | None,
    execution_result: PdflatexExecutionResult,
) -> PdfCompileResult:
    """Build structured compile metadata from execution and artifact state."""

    log_file_path = _log_file_path(workspace, tex_file_path)
    log_text = _read_text_if_exists(log_file_path)
    combined_diagnostics = "\n".join(
        part for part in [execution_result.stdout, execution_result.stderr, log_text] if part
    )
    warnings_detected = _detect_warning_lines(combined_diagnostics)
    errors_detected = _detect_error_lines(combined_diagnostics)
    compile_success = (
        execution_result.return_code == 0
        and pdf_file_path is not None
        and not execution_result.timed_out
        and not execution_result.executable_missing
    )

    failures = _build_failures(
        compile_success=compile_success,
        execution_result=execution_result,
        pdf_file_path=pdf_file_path,
        errors_detected=errors_detected,
    )
    pdf_artifact = (
        _build_artifact_metadata(
            artifact_id=f"{render_job_id}:pdf",
            render_job_id=render_job_id,
            template_id=template_id,
            kind=ArtifactKind.PDF,
            content_type="application/pdf",
            path=pdf_file_path,
        )
        if pdf_file_path is not None
        else None
    )
    log_artifact = (
        _build_artifact_metadata(
            artifact_id=f"{render_job_id}:log",
            render_job_id=render_job_id,
            template_id=template_id,
            kind=ArtifactKind.LOG,
            content_type="text/plain",
            path=log_file_path,
        )
        if log_file_path is not None and log_file_path.exists()
        else None
    )
    core_compile_result = CompileResult(
        success=compile_success,
        compiler=LatexCompiler.PDFLATEX,
        exit_code=execution_result.return_code,
        pdf_artifact=pdf_artifact,
        log_artifact=log_artifact,
        stdout_excerpt=_summarize_output(execution_result.stdout),
        stderr_excerpt=_summarize_output(execution_result.stderr),
        warnings=warnings_detected,
        failures=failures,
    )

    return PdfCompileResult(
        compile_success=compile_success,
        render_job_id=render_job_id,
        workspace_path=workspace.workspace_path,
        tex_file_path=str(tex_file_path),
        pdf_file_path=str(pdf_file_path) if pdf_file_path is not None else None,
        log_file_path=(
            str(log_file_path)
            if log_file_path is not None and log_file_path.exists()
            else None
        ),
        stdout_summary=_summarize_output(execution_result.stdout),
        stderr_summary=_summarize_output(execution_result.stderr),
        return_code=execution_result.return_code,
        elapsed_ms=execution_result.elapsed_ms,
        warnings_detected=warnings_detected,
        errors_detected=errors_detected,
        compile_result=core_compile_result,
    )


def cleanup_render_workspace(
    workspace: RenderWorkspace,
    cleanup_policy: WorkspaceCleanupPolicy,
    *,
    compile_success: bool,
) -> None:
    """Apply the caller-selected cleanup policy to the render workspace."""

    should_cleanup = cleanup_policy == WorkspaceCleanupPolicy.CLEAN_ALWAYS or (
        cleanup_policy == WorkspaceCleanupPolicy.CLEAN_ON_SUCCESS and compile_success
    )
    if should_cleanup:
        shutil.rmtree(workspace.workspace_path, ignore_errors=True)


def _build_failures(
    *,
    compile_success: bool,
    execution_result: PdflatexExecutionResult,
    pdf_file_path: Path | None,
    errors_detected: list[str],
) -> list[RenderFailure]:
    """Convert compiler failure conditions into render failures."""

    if compile_success:
        return []
    if execution_result.executable_missing:
        return [
            _failure(
                code="pdflatex-executable-missing",
                message="pdflatex executable was not found in PATH.",
                retryable=True,
            )
        ]
    if execution_result.timed_out:
        return [
            _failure(
                code="pdflatex-timeout",
                message="pdflatex timed out before producing a complete result.",
                retryable=True,
            )
        ]
    if pdf_file_path is None and execution_result.return_code == 0:
        return [
            _failure(
                code="pdf-output-missing",
                message="pdflatex exited successfully but no non-empty PDF was produced.",
            )
        ]
    message = errors_detected[0] if errors_detected else "pdflatex compilation failed."
    return [
        _failure(
            code="pdflatex-compile-failed",
            message=message,
            retryable=False,
        )
    ]


def _failure(*, code: str, message: str, retryable: bool = False) -> RenderFailure:
    """Build a LaTeX compile-stage failure object."""

    return RenderFailure(
        code=code,
        message=message,
        severity=RenderFailureSeverity.ERROR,
        stage=RenderFailureStage.LATEX_COMPILE,
        retryable=retryable,
    )


def _build_artifact_metadata(
    *,
    artifact_id: str,
    render_job_id: str,
    template_id: str,
    kind: ArtifactKind,
    content_type: str,
    path: Path,
) -> RenderArtifactMetadata:
    """Build artifact metadata for a generated compiler artifact."""

    return RenderArtifactMetadata(
        artifact_id=artifact_id,
        render_job_id=render_job_id,
        kind=kind,
        template_id=template_id,
        content_type=content_type,
        path=str(path),
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _log_file_path(workspace: RenderWorkspace, tex_file_path: Path) -> Path:
    """Return the expected pdflatex log file path."""

    return Path(workspace.workspace_path) / f"{tex_file_path.stem}.log"


def _read_text_if_exists(path: Path | None) -> str:
    """Read a diagnostics file when present."""

    if path is None or not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _detect_warning_lines(output: str) -> list[str]:
    """Extract a bounded list of warning lines from compiler output."""

    return _matching_output_lines(output, ("warning",))


def _detect_error_lines(output: str) -> list[str]:
    """Extract a bounded list of error lines from compiler output."""

    return _matching_output_lines(
        output,
        ("! ", "error", "fatal", "emergency stop", "undefined control sequence"),
    )


def _matching_output_lines(output: str, needles: tuple[str, ...]) -> list[str]:
    """Return unique output lines containing diagnostic markers."""

    matches: list[str] = []
    seen: set[str] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if not any(needle in lowered for needle in needles):
            continue
        if line in seen:
            continue
        matches.append(line)
        seen.add(line)
        if len(matches) >= MAX_DETECTED_MESSAGES:
            break
    return matches


def _summarize_output(output: str) -> str | None:
    """Return a bounded stdout/stderr summary suitable for diagnostics."""

    cleaned = output.strip()
    if not cleaned:
        return None
    if len(cleaned) <= MAX_OUTPUT_SUMMARY_CHARS:
        return cleaned
    return cleaned[-MAX_OUTPUT_SUMMARY_CHARS:]


def _sha256_file(path: Path) -> str:
    """Return a stable SHA-256 digest for an artifact file."""

    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _elapsed_ms(start_time: float) -> int:
    """Return elapsed wall time in milliseconds."""

    return max(0, round((time.perf_counter() - start_time) * 1000))


def _coerce_process_output(output: str | bytes | None) -> str:
    """Normalize subprocess timeout output to text."""

    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _safe_workspace_token(value: str) -> str:
    """Return a filesystem-safe token for workspace prefixes."""

    safe = "".join(character if character.isalnum() else "-" for character in value)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe[:48] or "render"
