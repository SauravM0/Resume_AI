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
from backend.app.orchestration.artifacts.models import ArtifactWriteResult
from backend.app.orchestration.enums import ArtifactKind, StageName
from backend.app.orchestration.fallbacks import (
    FallbackClass,
    should_use_deterministic_parse_fallback,
)
from backend.app.orchestration.orchestrator import ResumeGenerationOrchestrator
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.services.pdf_compiler import PdfCompileResult
from resume_optimizer.phase3_output_validation import (
    Phase3FallbackAction,
    Phase3FallbackActionType,
    Phase3ValidationReport,
)


def _recorder(run_id: str = "run.safe-fallbacks-test") -> PipelineRunRecorder:
    recorder = PipelineRunRecorder(event_emitter=None)
    recorder.create_run(
        run_id=run_id,
        requested_template="ats_standard",
        requested_mode="resume_pdf",
        job_description_hash="sha256:fallbacks",
        source_profile_id="profile.safe-fallbacks",
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
        render_job_id="render.fallback",
        kind=RenderArtifactKind.PDF,
        template_id="ats_standard",
        content_type="application/pdf",
        path=str(pdf_path),
    )
    return PdfCompileResult(
        compile_success=True,
        render_job_id="render.fallback",
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


class _PdfFirstFailOptionalBackend:
    storage_kind = "local_file"

    def __init__(self, root: Path) -> None:
        self.root = root

    def write_json(self, *, run_id: str, relative_name: str, payload: dict[str, object]) -> ArtifactWriteResult:
        raise NotImplementedError

    def write_text(self, *, run_id: str, relative_name: str, content: str, content_type: str) -> ArtifactWriteResult:
        raise NotImplementedError

    def copy_file(self, *, run_id: str, relative_name: str, source_path: Path, content_type: str) -> ArtifactWriteResult:
        destination = self.root / run_id / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative_name == "outputs/resume.pdf":
            destination.write_bytes(source_path.read_bytes())
            return ArtifactWriteResult(
                storage_kind=self.storage_kind,
                storage_path_or_key=str(destination),
                content_hash="sha256:test",
                size_bytes=len(source_path.read_bytes()),
                content_type=content_type,
            )
        raise OSError(f"simulated write failure for {relative_name}")


class _PdfFailureBackend(_PdfFirstFailOptionalBackend):
    def copy_file(self, *, run_id: str, relative_name: str, source_path: Path, content_type: str) -> ArtifactWriteResult:
        raise OSError("pdf storage unavailable")


def test_should_use_deterministic_parse_fallback_only_for_weak_confidence() -> None:
    assert should_use_deterministic_parse_fallback(
        parser_confidence=0.64,
        has_deterministic_extraction=True,
    ) is True
    assert should_use_deterministic_parse_fallback(
        parser_confidence=0.65,
        has_deterministic_extraction=True,
    ) is False
    assert should_use_deterministic_parse_fallback(
        parser_confidence=0.20,
        has_deterministic_extraction=False,
    ) is False


def test_recorder_safe_fallback_updates_run_diagnostics() -> None:
    recorder = _recorder()

    recorder.record_safe_fallback(
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        fallback_class=FallbackClass.REDUCE_SUMMARY_TO_SAFE_SHORT_FORM,
        reason="Summary contained unsupported claims and was reduced.",
        final_output_downgraded=True,
        machine_payload_json={"source_item_id": "summary"},
    )

    assert recorder.quality_downgraded is True
    diagnostics = recorder.run_diagnostics()
    assert diagnostics["fallback_count"] == 1
    assert diagnostics["fallback_classes"] == [FallbackClass.REDUCE_SUMMARY_TO_SAFE_SHORT_FORM]
    assert diagnostics["quality_status"] == "degraded"
    assert diagnostics["final_confidence_level"] == "degraded"
    assert diagnostics["confidence_assessment"] is None
    assert recorder.fallback_audits[0]["machine_payload_json"]["fallback_class"] == (
        FallbackClass.REDUCE_SUMMARY_TO_SAFE_SHORT_FORM
    )


def test_artifact_manager_skips_only_optional_artifacts_after_pdf_success(tmp_path: Path) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="resume-render-safe-fallback-"))
    recorder = _recorder("run.compile-fallback")
    manager = ArtifactManager(_PdfFirstFailOptionalBackend(tmp_path / "artifacts"))

    result = manager.persist_compile_result(
        recorder=recorder,
        result=_compile_result(workspace),
        cleanup_workspace=True,
    )

    assert result.durable_pdf_path is not None
    assert Path(result.durable_pdf_path).exists()
    assert result.durable_latex_path is None
    assert result.durable_log_path is None
    assert result.skipped_optional_artifacts == [
        ArtifactKind.LATEX_DOCUMENT,
        ArtifactKind.COMPILE_LOG,
    ]
    assert [artifact.kind for artifact in result.artifact_refs] == [ArtifactKind.PDF]
    assert not recorder.fallback_audits
    assert recorder.quality_downgraded is False


def test_artifact_manager_does_not_hide_core_pdf_persistence_failure(tmp_path: Path) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="resume-render-safe-fallback-fail-"))
    recorder = _recorder("run.compile-pdf-failure")
    manager = ArtifactManager(_PdfFailureBackend(tmp_path / "artifacts"))

    with pytest.raises(OSError):
        manager.persist_compile_result(
            recorder=recorder,
            result=_compile_result(workspace),
            cleanup_workspace=True,
        )

    assert not recorder.fallback_audits


def test_pipeline_result_artifact_records_fallback_usage_metadata() -> None:
    recorder = _recorder("run.pipeline-result-fallback")
    orchestrator = ResumeGenerationOrchestrator()
    recorder.record_safe_fallback(
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
        fallback_class=FallbackClass.USE_DETERMINISTIC_PARSE_SIGNALS,
        reason="Weak parser confidence required deterministic signals.",
        final_output_downgraded=True,
        machine_payload_json={"parser_confidence": 0.42},
    )

    persisted = orchestrator._persist_artifacts(recorder)
    pipeline_result = recorder.artifacts[-1]

    assert persisted["fallback_count"] == 1
    assert persisted["quality_status"] == "degraded"
    assert pipeline_result.kind == ArtifactKind.PIPELINE_RESULT
    assert pipeline_result.metadata["fallback_count"] == 1
    assert pipeline_result.metadata["quality_status"] == "degraded"
    assert pipeline_result.metadata["fallback_classes"] == [
        FallbackClass.USE_DETERMINISTIC_PARSE_SIGNALS
    ]


def test_generation_fallback_audit_records_supported_phase3_actions() -> None:
    recorder = _recorder("run.phase3-fallback-audit")
    orchestrator = ResumeGenerationOrchestrator()
    report = Phase3ValidationReport(
        applied_fallbacks=[
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.BULLET_SOURCE_FALLBACK,
                message="Bullet was replaced with source text.",
                source_item_id="exp-1",
            ),
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.METADATA_REBUILT,
                message="Metadata was rebuilt from validated content.",
            ),
        ]
    )

    orchestrator._record_generation_fallbacks(recorder, report)

    assert [audit["fallback_class"] for audit in recorder.fallback_audits] == [
        FallbackClass.USE_ORIGINAL_SOURCE_BULLET,
        FallbackClass.REBUILD_GENERATION_METADATA,
    ]
    assert recorder.quality_downgraded is True
    assert recorder.fallback_audits[1]["final_output_downgraded"] is False
