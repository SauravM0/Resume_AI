"""Typed artifact manager models for Phase 6 orchestration."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from backend.app.orchestration.enums import ArtifactKind, StageName
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.models import NonEmptyStr, StrictModel


class ArtifactWriteResult(StrictModel):
    """Result of writing or copying one artifact to durable storage."""

    storage_kind: NonEmptyStr
    storage_path_or_key: NonEmptyStr
    content_hash: NonEmptyStr
    size_bytes: int = Field(ge=0)
    content_type: NonEmptyStr


class ArtifactPersistenceResult(StrictModel):
    """Artifact references and durable paths created from one stage output."""

    stage_name: StageName
    artifact_refs: list[PipelineArtifactRef] = Field(default_factory=list)
    durable_pdf_path: NonEmptyStr | None = None
    durable_latex_path: NonEmptyStr | None = None
    durable_log_path: NonEmptyStr | None = None
    skipped_optional_artifacts: list[ArtifactKind] = Field(default_factory=list)
    cleanup_paths: list[NonEmptyStr] = Field(default_factory=list)


class ArtifactFileRequest(StrictModel):
    """Request to persist one local file artifact."""

    run_id: NonEmptyStr
    stage_name: StageName
    artifact_type: ArtifactKind
    source_path: Path
    filename: NonEmptyStr
    content_type: NonEmptyStr
