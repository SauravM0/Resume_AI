"""Adapter for Phase 5 PDF compilation."""

from __future__ import annotations

from collections.abc import Callable

from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.artifacts.artifact_manager import ArtifactManager, build_default_artifact_manager
from backend.app.orchestration.enums import ArtifactKind, OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.pipeline_models import CompilePdfInput, CompilePdfOutput
from backend.app.orchestration.types import PipelineArtifactRef
from backend.app.services.pdf_compiler import PdfCompileResult, compile_tex_document


class PdfCompileAdapter:
    """Wrap pdflatex compilation and artifact extraction."""

    stage_name = StageName.COMPILE_PDF

    def __init__(
        self,
        *,
        compile_func: Callable[..., PdfCompileResult] = compile_tex_document,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        self._compile_func = compile_func
        self._artifact_manager = artifact_manager or build_default_artifact_manager()

    def execute(
        self,
        stage_input: CompilePdfInput,
        context: StageExecutionContext,
    ) -> CompilePdfOutput:
        """Compile assembled LaTeX and expose PDF/log artifact references."""

        try:
            result = self._compile_func(
                tex_content=stage_input.assembled_document.tex_content,
                render_job_id=stage_input.render_job_id,
                template_id=stage_input.template_id,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"PDF compilation failed: {exc}",
                failure_type=OrchestrationFailureType.PDF_COMPILE,
                stage_name=self.stage_name,
                retryable=True,
            ) from exc

        pdf_ref = None
        log_ref = None
        durable_pdf_path = result.pdf_file_path
        durable_latex_path = result.tex_file_path
        if context.recorder is not None:
            try:
                persisted = self._artifact_manager.persist_compile_result(
                    recorder=context.recorder,
                    result=result,
                    cleanup_workspace=True,
                )
            except Exception as exc:
                if result.compile_success:
                    raise StageExecutionError(
                        f"artifact persistence failed after PDF compilation: {exc}",
                        failure_type=OrchestrationFailureType.ARTIFACT_PERSISTENCE,
                        stage_name=self.stage_name,
                    ) from exc
                raise StageExecutionError(
                    "PDF compilation failed before durable output persistence completed.",
                    failure_type=OrchestrationFailureType.PDF_COMPILE,
                    stage_name=self.stage_name,
                    retryable=True,
                ) from exc
            pdf_ref = next((artifact for artifact in persisted.artifact_refs if artifact.kind == ArtifactKind.PDF), None)
            log_ref = next((artifact for artifact in persisted.artifact_refs if artifact.kind == ArtifactKind.COMPILE_LOG), None)
            durable_pdf_path = persisted.durable_pdf_path or durable_pdf_path
            durable_latex_path = persisted.durable_latex_path or durable_latex_path

        if not result.compile_success:
            raise StageExecutionError(
                "PDF compilation failed.",
                failure_type=OrchestrationFailureType.PDF_COMPILE,
                stage_name=self.stage_name,
                retryable=True,
            )

        if context.recorder is not None:
            context.recorder.record_output(
                compile_status="succeeded",
                pdf_path_or_storage_key=durable_pdf_path,
                latex_path_or_storage_key=durable_latex_path,
                page_count=None,
                output_metadata_json={
                    "return_code": result.return_code,
                    "warnings_count": len(result.warnings_detected),
                    "errors_count": len(result.errors_detected),
                    "skipped_optional_artifacts": [
                        artifact.value for artifact in persisted.skipped_optional_artifacts
                    ],
                },
            )

        return CompilePdfOutput(
            compile_result=result,
            pdf_artifact_ref=pdf_ref,
            log_artifact_ref=log_ref,
        )

    def extract_artifacts(
        self,
        stage_output: CompilePdfOutput,
        context: StageExecutionContext,
    ) -> list[PipelineArtifactRef]:
        return [
            artifact
            for artifact in (stage_output.pdf_artifact_ref, stage_output.log_artifact_ref)
            if artifact is not None
        ]
