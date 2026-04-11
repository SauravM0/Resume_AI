"""Lightweight local storage for stage metrics."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol

from backend.app.metrics.models import StageMetricRecord
from backend.app.observability import get_request_id, get_run_id
from backend.app.privacy import sanitize_value
from resume_optimizer.config import DEFAULT_SETTINGS

DEFAULT_STAGE_METRICS_PATH = Path("data/metrics/stage_metrics.jsonl")
_SENSITIVE_OUTPUT_KEYS = {
    "candidate_data",
    "generated_summary",
    "job_description",
    "job_description_text",
    "raw_job_description",
    "resume",
    "resume_text",
    "source_profile",
    "summary",
}


class StageMetricsStore(Protocol):
    """Storage interface for stage timing records."""

    def append(self, record: StageMetricRecord) -> None:
        """Persist one stage record."""

    def load(self, *, limit: int | None = None) -> list[StageMetricRecord]:
        """Load recent records."""


class JsonlStageMetricsStore:
    """Append-only JSONL metrics store."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: StageMetricRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), separators=(",", ":")))
            handle.write("\n")

    def load(self, *, limit: int | None = None) -> list[StageMetricRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if limit is not None:
            lines = lines[-limit:]
        records: list[StageMetricRecord] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            records.append(StageMetricRecord.model_validate_json(stripped))
        return records


def build_default_stage_metrics_store() -> JsonlStageMetricsStore:
    """Build the default local stage metrics store."""

    configured = DEFAULT_SETTINGS.metrics.stage_metrics_path
    return JsonlStageMetricsStore(Path(configured) if configured else DEFAULT_STAGE_METRICS_PATH)


DEFAULT_STAGE_METRICS_STORE = build_default_stage_metrics_store()


def record_stage_metric(
    *,
    stage_name: str,
    started_at: datetime,
    ended_at: datetime,
    success: bool,
    failure_type: str | None = None,
    retry_count: int = 0,
    fallback_used: bool = False,
    output_metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
    run_id: str | None = None,
    store: StageMetricsStore | None = None,
) -> StageMetricRecord:
    """Persist one finalized stage metrics record."""

    record = StageMetricRecord(
        request_id=request_id or get_request_id(),
        run_id=run_id or get_run_id(),
        stage_name=stage_name,
        started_at=_ensure_utc(started_at),
        ended_at=_ensure_utc(ended_at),
        duration_ms=max(0, int((_ensure_utc(ended_at) - _ensure_utc(started_at)).total_seconds() * 1000)),
        success=success,
        failure_type=failure_type,
        retry_count=retry_count,
        fallback_used=fallback_used,
        output_metadata=summarize_output_metadata(output_metadata or {}),
    )
    resolved_store = store or DEFAULT_STAGE_METRICS_STORE
    resolved_store.append(record)
    return record


def summarize_output_metadata(output_metadata: dict[str, Any]) -> dict[str, object]:
    """Keep only safe compact metadata summaries."""

    summary: dict[str, object] = {}
    for key, value in output_metadata.items():
        if key.lower() in _SENSITIVE_OUTPUT_KEYS:
            summary[key] = sanitize_value(value, key=key)
            continue
        if value is None:
            continue
        if isinstance(value, bool):
            summary[key] = value
        elif isinstance(value, (int, float)):
            summary[key] = value
        elif isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            summary[f"{key}_count"] = len(value)
        elif key.endswith("_id") or key in {"status", "output_type", "loaded_from"}:
            summary[key] = str(value)
        elif isinstance(value, str):
            summary[key] = sanitize_value(value, key=key)
        else:
            summary[key] = str(value)
    return summary


def summarize_stage_output(output: object) -> dict[str, object]:
    """Build safe stage output metadata without persisting raw content."""

    summary: dict[str, object] = {"output_type": type(output).__name__}
    model_dump = getattr(output, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="python", exclude_none=True)
        if isinstance(payload, dict):
            summary["field_count"] = len(payload)
            for key, value in payload.items():
                if isinstance(value, list):
                    summary[f"{key}_count"] = len(value)
                elif isinstance(value, dict):
                    summary[f"{key}_count"] = len(value)
                elif isinstance(value, bool):
                    summary[key] = value
                elif isinstance(value, (int, float)):
                    summary[key] = value
                elif key.endswith("_id") or key in {"status", "loaded_from"}:
                    summary[key] = str(value)
                elif isinstance(value, str):
                    summary[key] = sanitize_value(value, key=key)
    elif isinstance(output, dict):
        summary["field_count"] = len(output)
    elif output is not None:
        summary["value_type"] = type(output).__name__
    return summarize_output_metadata(summary)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
