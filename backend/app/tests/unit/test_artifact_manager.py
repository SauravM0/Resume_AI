from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.models.render_models import (
    ArtifactKind as RenderArtifactKind,
    CompileResult,
    LatexCompiler,
    RenderArtifactMetadata,
)
from backend.app.orchestration.artifacts.artifact_manager import ArtifactManager
from backend.app.orchestration.artifacts.cleanup import UnsafeCleanupPathError, cleanup_compile_workspace
from backend.app.orchestration.artifacts.storage_backends import LocalArtifactStorageBackend
from backend.app.orchestration.enums import ArtifactKind
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.services.pdf_compiler import PdfCompileResult


def _recorder(run_id: str = "run.artifact-manager-test") -> PipelineRunRecorder:
    recorder = PipelineRunRecorder(event_emitter=None)
    recorder.create_run(
        run_id=run_id,
        requested_template="ats_standard",
        requested_mode="resume_pdf",
        job_description_hash="sha256:artifact",
        source_profile_id="profile.artifact",
    )
    return recorder


def _compile_result(workspace: Path) -> PdfCompileResult:
    tex_path = workspace / "resume.tex"
    pdf_path = workspace / "resume.pdf"
    log_path = workspace / "resume.log"
    tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-1.4\n")
    log_path.write_text("compile ok", encoding="utf-8")
    pdf_artifact = RenderArtifactMetadata(
        artifact_id="render.artifact.pdf",
        render_job_id="render.artifact",
        kind=RenderArtifactKind.PDF,
        template_id="ats_standard",
        content_type="application/pdf",
        path=str(pdf_path),
    )
    return PdfCompileResult(
        compile_success=True,
        render_job_id="render.artifact",
        workspace_path=str(workspace),
        tex_file_path=str(tex_path),
        pdf_file_path=str(pdf_path),
        log_file_path=str(log_path),
        return_code=0,
        elapsed_ms=1,
        compile_result=CompileResult(
            success=True,
            compiler=LatexCompiler.PDFLATEX,
            exit_code=0,
            pdf_artifact=pdf_artifact,
        ),
    )


def test_artifact_manager_persists_compile_outputs_before_cleanup(tmp_path: Path) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="resume-render-artifact-test-"))
    recorder = _recorder()
    manager = ArtifactManager(LocalArtifactStorageBackend(tmp_path / "artifacts"))

    result = manager.persist_compile_result(
        recorder=recorder,
        result=_compile_result(workspace),
        cleanup_workspace=True,
    )

    assert not workspace.exists()
    assert result.durable_pdf_path is not None
    assert Path(result.durable_pdf_path).exists()
    assert result.durable_latex_path is None
    assert result.durable_log_path is None
    assert {artifact.kind for artifact in result.artifact_refs} == {ArtifactKind.PDF}
    assert result.skipped_optional_artifacts == [
        ArtifactKind.LATEX_DOCUMENT,
        ArtifactKind.COMPILE_LOG,
    ]
    assert len(recorder.artifacts) == 1


def test_artifact_manager_can_explicitly_persist_sensitive_debug_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="resume-render-artifact-debug-"))
    recorder = _recorder("run.artifact-manager-debug")
    manager = ArtifactManager(LocalArtifactStorageBackend(tmp_path / "artifacts"))
    monkeypatch.setattr(
        "backend.app.orchestration.artifacts.artifact_manager.DEFAULT_SETTINGS.artifacts.persist_sensitive_debug_artifacts",
        True,
    )

    result = manager.persist_compile_result(
        recorder=recorder,
        result=_compile_result(workspace),
        cleanup_workspace=True,
    )

    assert result.durable_pdf_path is not None
    assert result.durable_latex_path is not None
    assert Path(result.durable_latex_path).exists()
    assert result.durable_log_path is not None
    assert Path(result.durable_log_path).exists()
    assert {artifact.kind for artifact in result.artifact_refs} == {
        ArtifactKind.PDF,
        ArtifactKind.LATEX_DOCUMENT,
        ArtifactKind.COMPILE_LOG,
    }


def test_cleanup_refuses_non_compile_workspace(tmp_path: Path) -> None:
    unsafe_path = tmp_path / "not-a-compile-workspace"
    unsafe_path.mkdir()

    with pytest.raises(UnsafeCleanupPathError):
        cleanup_compile_workspace(str(unsafe_path))

    assert unsafe_path.exists()
