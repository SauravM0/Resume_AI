"""Stage-aware artifact persistence and cleanup manager."""

from __future__ import annotations
from pathlib import Path
from typing import Any

from backend.app.orchestration.artifacts.cleanup import cleanup_compile_workspace
from backend.app.orchestration.artifacts.models import ArtifactPersistenceResult
from backend.app.orchestration.artifacts.storage_backends import (
    ArtifactStorageBackend,
    LocalArtifactStorageBackend,
)
from backend.app.orchestration.enums import ArtifactKind, StageName
from backend.app.orchestration.fallbacks import (
    FallbackClass,
    optional_artifact_fallback_metadata,
)
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.services.pdf_compiler import PdfCompileResult
from resume_optimizer.config import DEFAULT_SETTINGS

DEFAULT_LOCAL_ARTIFACT_ROOT = Path("data/pipeline_artifacts")
ARTIFACT_SCHEMA_VERSION = "phase6.artifact.v1"


class ArtifactManager:
    """Persist meaningful stage artifacts and cleanup temporary workspaces."""

    def __init__(self, storage_backend: ArtifactStorageBackend) -> None:
        self.storage_backend = storage_backend

    def persist_inline_json(
        self,
        *,
        recorder: PipelineRunRecorder,
        stage_name: StageName,
        artifact_type: ArtifactKind,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        schema_version: str = ARTIFACT_SCHEMA_VERSION,
        content_hash: str | None = None,
    ):
        """Record a structured JSON artifact inline in the metadata store."""

        return recorder.record_artifact(
            stage_name=stage_name,
            artifact_type=artifact_type,
            storage_kind="inline",
            schema_version=schema_version,
            inline_json=payload,
            metadata=metadata,
            content_hash=content_hash,
        )

    def persist_text_artifact(
        self,
        *,
        recorder: PipelineRunRecorder,
        stage_name: StageName,
        artifact_type: ArtifactKind,
        relative_name: str,
        content: str,
        content_type: str,
    ):
        """Persist text content to durable storage and record a reference."""

        assert recorder.run_id is not None
        write_result = self.storage_backend.write_text(
            run_id=recorder.run_id,
            relative_name=relative_name,
            content=content,
            content_type=content_type,
        )
        return recorder.record_artifact(
            stage_name=stage_name,
            artifact_type=artifact_type,
            storage_kind=write_result.storage_kind,
            storage_path_or_key=write_result.storage_path_or_key,
            schema_version=ARTIFACT_SCHEMA_VERSION,
            content_hash=write_result.content_hash,
            content_type=write_result.content_type,
        )

    def persist_compile_result(
        self,
        *,
        recorder: PipelineRunRecorder,
        result: PdfCompileResult,
        cleanup_workspace: bool = True,
    ) -> ArtifactPersistenceResult:
        """Persist compile outputs before safely deleting the temp workspace."""

        assert recorder.run_id is not None
        artifact_refs = []
        durable_pdf_path = None
        durable_latex_path = None
        durable_log_path = None
        skipped_optional_artifacts: list[ArtifactKind] = []
        persist_sensitive_debug_artifacts = DEFAULT_SETTINGS.artifacts.persist_sensitive_debug_artifacts

        if result.pdf_file_path is not None:
            pdf_write = self.storage_backend.copy_file(
                run_id=recorder.run_id,
                relative_name="outputs/resume.pdf",
                source_path=Path(result.pdf_file_path),
                content_type="application/pdf",
            )
            durable_pdf_path = pdf_write.storage_path_or_key
            artifact_refs.append(
                recorder.record_artifact(
                    stage_name=StageName.COMPILE_PDF,
                    artifact_type=ArtifactKind.PDF,
                    storage_kind=pdf_write.storage_kind,
                    storage_path_or_key=pdf_write.storage_path_or_key,
                    schema_version=ARTIFACT_SCHEMA_VERSION,
                    content_hash=pdf_write.content_hash,
                    content_type=pdf_write.content_type,
                    metadata={"artifact_name": "resume.pdf"},
                )
            )

        if result.tex_file_path is not None and persist_sensitive_debug_artifacts:
            try:
                latex_write = self.storage_backend.copy_file(
                    run_id=recorder.run_id,
                    relative_name="outputs/resume.tex",
                    source_path=Path(result.tex_file_path),
                    content_type="application/x-tex",
                )
                durable_latex_path = latex_write.storage_path_or_key
                artifact_refs.append(
                    recorder.record_artifact(
                        stage_name=StageName.COMPILE_PDF,
                        artifact_type=ArtifactKind.LATEX_DOCUMENT,
                        storage_kind=latex_write.storage_kind,
                        storage_path_or_key=latex_write.storage_path_or_key,
                        schema_version=ARTIFACT_SCHEMA_VERSION,
                        content_hash=latex_write.content_hash,
                        content_type=latex_write.content_type,
                        metadata={"artifact_name": "resume.tex"},
                    )
                )
            except Exception as exc:
                if durable_pdf_path is None:
                    raise
                skipped_optional_artifacts.append(ArtifactKind.LATEX_DOCUMENT)
                recorder.record_safe_fallback(
                    stage_name=StageName.COMPILE_PDF,
                    fallback_class=FallbackClass.SKIP_OPTIONAL_ARTIFACT_GENERATION,
                    reason="Optional LaTeX artifact persistence failed after PDF persistence succeeded.",
                    final_output_downgraded=False,
                    machine_payload_json=optional_artifact_fallback_metadata(
                        ArtifactKind.LATEX_DOCUMENT,
                        artifact_name="resume.tex",
                        error_message=str(exc),
                    ),
                )
        elif result.tex_file_path is not None:
            skipped_optional_artifacts.append(ArtifactKind.LATEX_DOCUMENT)

        if result.log_file_path is not None and persist_sensitive_debug_artifacts:
            try:
                log_write = self.storage_backend.copy_file(
                    run_id=recorder.run_id,
                    relative_name="outputs/compile.log",
                    source_path=Path(result.log_file_path),
                    content_type="text/plain",
                )
                durable_log_path = log_write.storage_path_or_key
                artifact_refs.append(
                    recorder.record_artifact(
                        stage_name=StageName.COMPILE_PDF,
                        artifact_type=ArtifactKind.COMPILE_LOG,
                        storage_kind=log_write.storage_kind,
                        storage_path_or_key=log_write.storage_path_or_key,
                        schema_version=ARTIFACT_SCHEMA_VERSION,
                        content_hash=log_write.content_hash,
                        content_type=log_write.content_type,
                        metadata={"artifact_name": "compile.log"},
                    )
                )
            except Exception as exc:
                if durable_pdf_path is None:
                    raise
                skipped_optional_artifacts.append(ArtifactKind.COMPILE_LOG)
                recorder.record_safe_fallback(
                    stage_name=StageName.COMPILE_PDF,
                    fallback_class=FallbackClass.SKIP_OPTIONAL_ARTIFACT_GENERATION,
                    reason="Optional compile log persistence failed after PDF persistence succeeded.",
                    final_output_downgraded=False,
                    machine_payload_json=optional_artifact_fallback_metadata(
                        ArtifactKind.COMPILE_LOG,
                        artifact_name="compile.log",
                        error_message=str(exc),
                    ),
                )
        elif result.log_file_path is not None:
            skipped_optional_artifacts.append(ArtifactKind.COMPILE_LOG)

        cleanup_paths: list[str] = []
        if cleanup_workspace:
            cleanup_compile_workspace(result.workspace_path)
            cleanup_paths.append(result.workspace_path)

        return ArtifactPersistenceResult(
            stage_name=StageName.COMPILE_PDF,
            artifact_refs=artifact_refs,
            durable_pdf_path=durable_pdf_path,
            durable_latex_path=durable_latex_path,
            durable_log_path=durable_log_path,
            skipped_optional_artifacts=skipped_optional_artifacts,
            cleanup_paths=cleanup_paths,
        )


def build_default_artifact_manager() -> ArtifactManager:
    """Build the default storage-agnostic artifact manager."""

    root = DEFAULT_SETTINGS.artifacts.artifact_root or DEFAULT_LOCAL_ARTIFACT_ROOT
    return ArtifactManager(LocalArtifactStorageBackend(root))
