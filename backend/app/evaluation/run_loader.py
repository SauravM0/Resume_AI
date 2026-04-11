"""Utilities for loading persisted evaluation runs from disk."""

from __future__ import annotations

from pathlib import Path
import json

from backend.app.evaluation.artifact_models import ArtifactManifest, ArtifactPayloadFormat, LoadedArtifactDocument, PersistedArtifactMetadata
from backend.app.evaluation.runtime_models import EvaluationRunManifest
from resume_optimizer.models import NonEmptyStr, StrictModel


class LoadedEvaluationRun(StrictModel):
    """Reconstructed persisted evaluation run from disk artifacts."""

    root_path: NonEmptyStr
    run_manifest: EvaluationRunManifest
    artifact_manifest: ArtifactManifest
    summary_markdown: str | None = None
    artifacts: list[LoadedArtifactDocument] = []


def load_saved_evaluation_run(run_root: Path) -> LoadedEvaluationRun:
    """Load a saved evaluation run from its filesystem root."""

    run_manifest = EvaluationRunManifest.model_validate_json(
        (run_root / "run_manifest.json").read_text(encoding="utf-8")
    )
    artifact_manifest = ArtifactManifest.model_validate_json(
        (run_root / "manifest.json").read_text(encoding="utf-8")
    )
    summary_path = run_root / "summary.md"
    artifacts = [_load_artifact_document(run_root, entry) for entry in artifact_manifest.entries]
    return LoadedEvaluationRun(
        root_path=str(run_root),
        run_manifest=run_manifest,
        artifact_manifest=artifact_manifest,
        summary_markdown=summary_path.read_text(encoding="utf-8") if summary_path.exists() else None,
        artifacts=artifacts,
    )


def render_loaded_run_summary(run: LoadedEvaluationRun) -> str:
    """Rebuild a concise markdown summary from a loaded run."""

    lines = [
        f"# Evaluation Run {run.run_manifest.run_id}",
        "",
        f"- Case: `{run.run_manifest.case_id}`",
        f"- Mode: `{run.run_manifest.execution_mode}`",
        f"- Run Status: `{run.run_manifest.run_status.value}`",
        f"- Pipeline Status: `{run.run_manifest.pipeline_status.value if run.run_manifest.pipeline_status is not None else 'n/a'}`",
        f"- Artifact Count: `{len(run.artifact_manifest.entries)}`",
        "",
        "## Stages",
    ]
    for record in run.run_manifest.stage_records:
        lines.append(
            f"- `{record.stage_name.value}`: `{record.status.value}` artifacts={record.artifact_count}"
        )
    return "\n".join(lines) + "\n"


def _load_artifact_document(run_root: Path, entry) -> LoadedArtifactDocument:
    if entry.metadata_path is None:
        raise ValueError(f"artifact entry is missing metadata_path: {entry.artifact_id}")
    metadata = PersistedArtifactMetadata.model_validate_json(
        Path(entry.metadata_path).read_text(encoding="utf-8")
    )
    payload = None
    payload_path = Path(entry.storage_path)
    if entry.payload_format == ArtifactPayloadFormat.JSON:
        document = json.loads(payload_path.read_text(encoding="utf-8"))
        payload = document.get("payload") if isinstance(document, dict) else document
    elif entry.payload_format == ArtifactPayloadFormat.TEXT:
        payload = payload_path.read_text(encoding="utf-8")
    return LoadedArtifactDocument(
        entry=entry,
        metadata=metadata,
        payload=payload,
    )
