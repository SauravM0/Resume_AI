"""Concrete evaluation artifact persistence for Phase 7 runs."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re

from backend.app.evaluation.artifact_models import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactPayloadFormat,
    PersistedArtifactMetadata,
)
from backend.app.evaluation.contracts import ArtifactStore
from backend.app.evaluation.paths import DEFAULT_EVALUATION_OUTPUT_ROOT
from backend.app.evaluation.runtime_models import EvaluationRunManifest
from backend.app.orchestration.enums import ArtifactKind, StageName
from resume_optimizer.models import StableId

SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|authorization|password|email|phone|address)",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\+?\d[\d().\-\s]{6,}\d")
SECRET_VALUE_PATTERN = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+)\b")


class LocalFileArtifactStore(ArtifactStore):
    """Persist evaluation artifacts in a stable local filesystem layout."""

    def __init__(self, root_path: Path = DEFAULT_EVALUATION_OUTPUT_ROOT) -> None:
        self.root_path = root_path
        self._entries_by_run: dict[tuple[str, str], list[ArtifactManifestEntry]] = {}

    def persist_stage_artifact(
        self,
        *,
        run_id: StableId,
        case_id: StableId,
        stage_name: StageName,
        artifact_name: str,
        payload: bytes | str | dict[str, object] | list[object],
        content_type: str,
        schema_version: str = "phase7.eval.artifact.v1",
    ) -> ArtifactManifestEntry:
        persisted_at = datetime.now(timezone.utc)
        relative_name = Path("stages") / stage_name.value / _safe_name(artifact_name)
        destination = self.root_path / _safe_name(run_id) / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload_format = _payload_format_for(content_type=content_type, payload=payload, artifact_name=artifact_name)
        sanitized_payload, redacted = _sanitize_payload(payload)
        metadata_path = destination.parent / f"{destination.name}.metadata.json"

        if payload_format == ArtifactPayloadFormat.JSON:
            document = {
                "artifact_metadata": {
                    "run_id": run_id,
                    "case_id": case_id,
                    "stage_name": stage_name.value,
                    "schema_version": schema_version,
                    "persisted_at": persisted_at.isoformat(),
                    "artifact_name": artifact_name,
                },
                "payload": sanitized_payload,
            }
            destination.write_text(
                json.dumps(document, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        elif payload_format == ArtifactPayloadFormat.TEXT:
            assert isinstance(sanitized_payload, str)
            destination.write_text(sanitized_payload, encoding="utf-8")
        else:
            assert isinstance(sanitized_payload, bytes)
            destination.write_bytes(sanitized_payload)

        file_bytes = destination.read_bytes()
        entry = ArtifactManifestEntry(
            artifact_id=f"{run_id}.{stage_name.value}.{_artifact_token(artifact_name)}",
            run_id=run_id,
            case_id=case_id,
            stage_name=stage_name,
            artifact_kind=_artifact_kind_for_name(stage_name=stage_name, artifact_name=artifact_name),
            schema_version=schema_version,
            storage_path=str(destination),
            relative_path=str(relative_name),
            content_type=content_type,
            payload_format=payload_format,
            metadata_path=str(metadata_path),
            content_hash="sha256:" + sha256(file_bytes).hexdigest(),
            size_bytes=len(file_bytes),
            created_at=persisted_at,
            redacted=redacted,
        )
        metadata = PersistedArtifactMetadata(
            artifact_id=entry.artifact_id,
            run_id=run_id,
            case_id=case_id,
            stage_name=stage_name,
            artifact_kind=entry.artifact_kind,
            schema_version=schema_version,
            persisted_at=persisted_at,
            content_type=content_type,
            content_hash=entry.content_hash,
            redacted=redacted,
            payload_format=payload_format,
            size_bytes=entry.size_bytes,
        )
        metadata_path.write_text(
            json.dumps(metadata.model_dump(mode="json", exclude_none=True), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._entries_by_run.setdefault((run_id, case_id), []).append(entry)
        return entry

    def build_manifest(self, *, run_id: StableId, case_id: StableId) -> ArtifactManifest:
        entries = sorted(
            self._entries_by_run.get((run_id, case_id), []),
            key=lambda item: (item.stage_name.value, item.relative_path),
        )
        return ArtifactManifest(
            run_id=run_id,
            case_id=case_id,
            generated_at=datetime.now(timezone.utc),
            entries=entries,
        )

    def write_manifest(self, manifest: ArtifactManifest) -> Path:
        return self.write_json_document(
            run_id=manifest.run_id,
            relative_name="manifest.json",
            payload=manifest.model_dump(mode="json", exclude_none=True),
        )

    def write_summary(self, run_manifest: EvaluationRunManifest, artifact_manifest: ArtifactManifest) -> Path:
        destination = self.root_path / _safe_name(run_manifest.run_id) / "summary.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            _build_summary_markdown(run_manifest=run_manifest, artifact_manifest=artifact_manifest),
            encoding="utf-8",
        )
        return destination

    def write_json_document(
        self,
        *,
        run_id: StableId,
        relative_name: str,
        payload: dict[str, object],
    ) -> Path:
        destination = self.root_path / _safe_name(run_id) / Path(relative_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return destination


def _build_summary_markdown(
    *,
    run_manifest: EvaluationRunManifest,
    artifact_manifest: ArtifactManifest,
) -> str:
    lines = [
        f"# Evaluation Run `{run_manifest.run_id}`",
        "",
        f"- Case ID: `{run_manifest.case_id}`",
        f"- Execution Mode: `{run_manifest.execution_mode}`",
        f"- Run Status: `{run_manifest.run_status.value}`",
        f"- Pipeline Status: `{run_manifest.pipeline_status.value if run_manifest.pipeline_status is not None else 'n/a'}`",
        f"- Artifact Count: `{len(artifact_manifest.entries)}`",
        "",
        "## Stages",
    ]
    for record in run_manifest.stage_records:
        lines.append(
            f"- `{record.stage_name.value}`: `{record.status.value}` artifacts=`{record.artifact_count}` {record.message}"
        )
    if run_manifest.missing_dependencies:
        lines.extend(["", "## Missing Dependencies"])
        for dependency in run_manifest.missing_dependencies:
            lines.append(f"- `{dependency.dependency_name}`: {dependency.message}")
    lines.extend(["", "## Artifacts"])
    for entry in artifact_manifest.entries:
        lines.append(
            f"- `{entry.stage_name.value}` `{entry.artifact_kind.value}` [{entry.relative_path}]"
        )
    return "\n".join(lines) + "\n"


def _artifact_kind_for_name(*, stage_name: StageName, artifact_name: str) -> ArtifactKind:
    lowered = artifact_name.casefold()
    mapping = {
        "source_profile.json": ArtifactKind.SOURCE_PROFILE,
        "normalized_profile.json": ArtifactKind.NORMALIZED_PROFILE,
        "raw_job_description.json": ArtifactKind.RAW_JOB_DESCRIPTION,
        "parse_output.json": ArtifactKind.JOB_ANALYSIS,
        "deterministic_extraction.json": ArtifactKind.PHASE1_DETERMINISTIC_EXTRACTION,
        "llm_enrichment.json": ArtifactKind.PHASE1_LLM_ENRICHMENT,
        "final_analysis.json": ArtifactKind.PHASE1_FINAL_ANALYSIS,
        "evidence_graph.json": ArtifactKind.PHASE2_SELECTION,
        "coverage_map.json": ArtifactKind.PHASE2_SELECTION,
        "selection_output.json": ArtifactKind.PHASE2_SELECTION,
        "ranking_output.json": ArtifactKind.PHASE2_RANKING,
        "phase3_request.json": ArtifactKind.PHASE3_REQUEST,
        "generation_payload.json": ArtifactKind.PHASE3_PAYLOAD,
        "section_plan.json": ArtifactKind.PHASE3_SECTION_PLAN,
        "phase3_result.json": ArtifactKind.PHASE3_RESULT,
        "validation_report.json": ArtifactKind.PHASE3_VALIDATION_REPORT,
        "verification_report.json": ArtifactKind.VERIFICATION_REPORT,
        "verification_audit.json": ArtifactKind.VERIFICATION_AUDIT,
        "rendering_output.json": ArtifactKind.RENDERING_GATE,
        "render_input.json": ArtifactKind.RENDER_INPUT,
        "assembled_document.json": ArtifactKind.LATEX_DOCUMENT,
        "compile_result.json": ArtifactKind.COMPILE_LOG,
        "compile_metadata.json": ArtifactKind.PDF,
        "resume.pdf": ArtifactKind.PDF,
        "compile.log": ArtifactKind.COMPILE_LOG,
        "resume.tex": ArtifactKind.LATEX_DOCUMENT,
        "pipeline_result.json": ArtifactKind.PIPELINE_RESULT,
    }
    return mapping.get(
        lowered,
        ArtifactKind.STAGE_LOG if stage_name == StageName.PERSIST_ARTIFACTS else ArtifactKind.PIPELINE_RESULT,
    )


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in value)[:160]


def _artifact_token(value: str) -> str:
    token = _safe_name(value)
    return token[:-5] if token.endswith(".json") else token


def _payload_format_for(
    *,
    content_type: str,
    payload: bytes | str | dict[str, object] | list[object],
    artifact_name: str,
) -> ArtifactPayloadFormat:
    if isinstance(payload, (dict, list)) or artifact_name.endswith(".json") or content_type == "application/json":
        return ArtifactPayloadFormat.JSON
    if isinstance(payload, bytes):
        return ArtifactPayloadFormat.BINARY
    return ArtifactPayloadFormat.TEXT


def _sanitize_payload(
    payload: bytes | str | dict[str, object] | list[object],
) -> tuple[bytes | str | dict[str, object] | list[object], bool]:
    if isinstance(payload, bytes):
        return payload, False
    if isinstance(payload, list):
        redacted = False
        values: list[object] = []
        for item in payload:
            sanitized, item_redacted = _sanitize_value(item, key_name=None)
            values.append(sanitized)
            redacted = redacted or item_redacted
        return values, redacted
    if isinstance(payload, dict):
        redacted = False
        sanitized_dict: dict[str, object] = {}
        for key, value in payload.items():
            sanitized, value_redacted = _sanitize_value(value, key_name=key)
            sanitized_dict[key] = sanitized
            redacted = redacted or value_redacted
        return sanitized_dict, redacted
    return _sanitize_text(payload)


def _sanitize_value(value: object, *, key_name: str | None) -> tuple[object, bool]:
    if isinstance(value, dict):
        sanitized, redacted = _sanitize_payload(value)
        return sanitized, redacted
    if isinstance(value, list):
        sanitized, redacted = _sanitize_payload(value)
        return sanitized, redacted
    if isinstance(value, str):
        if key_name is not None and SENSITIVE_KEY_PATTERN.search(key_name):
            return "[REDACTED]", True
        return _sanitize_text(value)
    return value, False


def _sanitize_text(value: str) -> tuple[str, bool]:
    redacted = False
    sanitized = value
    updated = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)
    redacted = redacted or updated != sanitized
    sanitized = updated
    updated = PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    redacted = redacted or updated != sanitized
    sanitized = updated
    updated = SECRET_VALUE_PATTERN.sub("[REDACTED_SECRET]", sanitized)
    redacted = redacted or updated != sanitized
    sanitized = updated
    return sanitized, redacted
