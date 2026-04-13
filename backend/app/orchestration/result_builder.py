"""Build API-facing Phase 6 orchestration responses."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

from pydantic import Field

from backend.app.orchestration.enums import ArtifactKind, ArtifactStorageBackend, PipelineStatus
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel


class AvailableOutput(StrictModel):
    """Machine-readable generated output reference."""

    kind: NonEmptyStr
    storage_kind: NonEmptyStr
    reference: NonEmptyStr
    content_type: NonEmptyStr | None = None
    file_name: NonEmptyStr | None = None
    label: NonEmptyStr | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    preview_reference: NonEmptyStr | None = None


class GenerateResumePipelineResponse(StrictModel):
    """API response for a Phase 6 end-to-end resume generation run."""

    run_id: StableId
    status: PipelineStatus
    available_outputs: list[AvailableOutput] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    final_file_reference: NonEmptyStr | None = None
    artifact_manifest: list[PipelineArtifactRef] = Field(default_factory=list)
    stage_events: list[dict[str, object]] = Field(default_factory=list)
    completed_phases: list[NonEmptyStr] = Field(default_factory=list)
    run_metadata: dict[str, object] = Field(default_factory=dict)
    selected_experiences: list[dict[str, object]] = Field(default_factory=list)
    selected_projects: list[dict[str, object]] = Field(default_factory=list)
    selected_skills: list[dict[str, object]] = Field(default_factory=list)


def build_pipeline_response(
    *,
    run_id: str,
    status: PipelineStatus,
    artifact_manifest: list[PipelineArtifactRef],
    stage_events: list[dict[str, object]],
    warnings: list[str],
    final_file_reference: str | None,
    selected_experiences: list[dict[str, object]] | None = None,
    selected_projects: list[dict[str, object]] | None = None,
    selected_skills: list[dict[str, object]] | None = None,
    run_metadata: dict[str, object] | None = None,
) -> GenerateResumePipelineResponse:
    """Build the stable API response from orchestration state."""

    public_manifest = [_public_artifact_ref(run_id, artifact) for artifact in artifact_manifest]
    available_outputs = [
        AvailableOutput(
            kind=_output_kind_for_artifact(artifact.kind),
            storage_kind=artifact.storage_backend.value,
            reference=_artifact_reference(artifact),
            content_type=artifact.content_type,
            file_name=_artifact_file_name(artifact),
            label=_artifact_label(artifact.kind),
            size_bytes=artifact.size_bytes,
            preview_reference=_artifact_preview_reference(artifact),
        )
        for artifact in public_manifest
        if _is_downloadable_output(artifact.kind) and artifact.uri is not None
    ]
    experience_payload = list(selected_experiences or [])
    project_payload = list(selected_projects or [])
    skill_payload = list(selected_skills or [])
    completed_phases = _completed_phases(stage_events)
    final_reference = (
        next((output.reference for output in available_outputs if output.kind == "pdf"), None)
        or final_file_reference
    )
    response_run_metadata = {
        **(run_metadata or {}),
        "completed_phases": completed_phases,
        "selected_experience_count": len(experience_payload),
        "selected_project_count": len(project_payload),
        "selected_skill_count": len(skill_payload),
        "selected_evidence_summary": {
            "experience_count": len(experience_payload),
            "project_count": len(project_payload),
            "skill_count": len(skill_payload),
        },
        "artifact_count": len(public_manifest),
        "final_file_reference": final_reference,
        "resume_ready": any(output.kind == "pdf" for output in available_outputs),
    }
    return GenerateResumePipelineResponse(
        run_id=run_id,
        status=status,
        available_outputs=available_outputs,
        warnings=warnings,
        final_file_reference=final_reference,
        artifact_manifest=public_manifest,
        stage_events=stage_events,
        completed_phases=completed_phases,
        run_metadata=response_run_metadata,
        selected_experiences=experience_payload,
        selected_projects=project_payload,
        selected_skills=skill_payload,
    )


def _completed_phases(stage_events: Iterable[dict[str, object]]) -> list[str]:
    seen: set[str] = set()
    completed: list[str] = []
    for event in stage_events:
        if event.get("status") != "succeeded":
            continue
        stage_name = event.get("stage_name")
        if not isinstance(stage_name, str) or stage_name in seen:
            continue
        seen.add(stage_name)
        completed.append(stage_name)
    return completed


def _public_artifact_ref(run_id: str, artifact: PipelineArtifactRef) -> PipelineArtifactRef:
    if artifact.storage_backend != ArtifactStorageBackend.LOCAL_FILE or artifact.uri is None:
        return artifact
    return artifact.model_copy(
        update={
            "uri": (
                f"/api/pipeline-runs/{run_id}/artifacts/{artifact.artifact_id}"
                f"?path={quote(artifact.uri, safe='')}"
            )
        }
    )


def _is_downloadable_output(kind: ArtifactKind) -> bool:
    return kind in {
        ArtifactKind.PDF,
        ArtifactKind.LATEX_DOCUMENT,
        ArtifactKind.COMPILE_LOG,
        ArtifactKind.PHASE3_RESULT,
        ArtifactKind.PIPELINE_RESULT,
        ArtifactKind.VERIFICATION_REPORT,
    }


def _output_kind_for_artifact(kind: ArtifactKind) -> str:
    if kind in {ArtifactKind.PHASE3_RESULT, ArtifactKind.PIPELINE_RESULT}:
        return "structured_json"
    return kind.value


def _artifact_reference(artifact: PipelineArtifactRef) -> str:
    return artifact.uri or artifact.artifact_id


def _artifact_preview_reference(artifact: PipelineArtifactRef) -> str | None:
    if artifact.kind in {ArtifactKind.PDF, ArtifactKind.LATEX_DOCUMENT, ArtifactKind.PHASE3_RESULT, ArtifactKind.PIPELINE_RESULT}:
        return artifact.uri or artifact.artifact_id
    return None


def _artifact_file_name(artifact: PipelineArtifactRef) -> str | None:
    metadata_name = artifact.metadata.get("artifact_name")
    if isinstance(metadata_name, str) and metadata_name:
        return metadata_name
    defaults = {
        ArtifactKind.PDF: "resume.pdf",
        ArtifactKind.LATEX_DOCUMENT: "resume.tex",
        ArtifactKind.COMPILE_LOG: "compile.log",
        ArtifactKind.PHASE3_RESULT: "phase3-result.json",
        ArtifactKind.PIPELINE_RESULT: "result.json",
        ArtifactKind.VERIFICATION_REPORT: "verification-report.json",
    }
    return defaults.get(artifact.kind)


def _artifact_label(kind: ArtifactKind) -> str:
    labels = {
        ArtifactKind.PDF: "Resume PDF",
        ArtifactKind.LATEX_DOCUMENT: "LaTeX source",
        ArtifactKind.COMPILE_LOG: "Compile log",
        ArtifactKind.PHASE3_RESULT: "Structured JSON",
        ArtifactKind.PIPELINE_RESULT: "Structured JSON",
        ArtifactKind.VERIFICATION_REPORT: "Verification report",
    }
    return labels.get(kind, kind.value.replace("_", " "))
