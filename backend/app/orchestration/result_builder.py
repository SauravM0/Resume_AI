"""Build API-facing Phase 6 orchestration responses."""

from __future__ import annotations

from pydantic import Field

from backend.app.orchestration.enums import PipelineStatus
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel


class AvailableOutput(StrictModel):
    """Machine-readable generated output reference."""

    kind: NonEmptyStr
    storage_kind: NonEmptyStr
    reference: NonEmptyStr
    content_type: NonEmptyStr | None = None


class GenerateResumePipelineResponse(StrictModel):
    """API response for a Phase 6 end-to-end resume generation run."""

    run_id: StableId
    status: PipelineStatus
    available_outputs: list[AvailableOutput] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    final_file_reference: NonEmptyStr | None = None
    artifact_manifest: list[PipelineArtifactRef] = Field(default_factory=list)
    stage_events: list[dict[str, object]] = Field(default_factory=list)


def build_pipeline_response(
    *,
    run_id: str,
    status: PipelineStatus,
    artifact_manifest: list[PipelineArtifactRef],
    stage_events: list[dict[str, object]],
    warnings: list[str],
    final_file_reference: str | None,
) -> GenerateResumePipelineResponse:
    """Build the stable API response from orchestration state."""

    available_outputs = [
        AvailableOutput(
            kind=artifact.kind.value,
            storage_kind=artifact.storage_backend.value,
            reference=artifact.uri or artifact.artifact_id,
            content_type=artifact.content_type,
        )
        for artifact in artifact_manifest
        if artifact.kind.value in {"pdf", "latex_document", "compile_log"}
    ]
    return GenerateResumePipelineResponse(
        run_id=run_id,
        status=status,
        available_outputs=available_outputs,
        warnings=warnings,
        final_file_reference=final_file_reference,
        artifact_manifest=artifact_manifest,
        stage_events=stage_events,
    )
