"""Safe operator support helpers built on existing metrics and cleanup paths."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
import tempfile
from typing import Any

from backend.app.cache.metrics import summarize_cache_metrics
from backend.app.cache.models import CacheMetricRecord
from backend.app.metrics.models import StageMetricRecord
from backend.app.orchestration.artifacts.cleanup import cleanup_compile_workspace, is_safe_compile_workspace
from backend.app.privacy import sanitize_value
from resume_optimizer.config import DEFAULT_SETTINGS


def build_health_snapshot() -> dict[str, object]:
    """Return an operator-safe health snapshot of active runtime paths and flags."""

    metrics_path = Path(DEFAULT_SETTINGS.metrics.stage_metrics_path)
    cache_metrics_path = Path(DEFAULT_SETTINGS.metrics.cache_metrics_path)
    artifact_root = Path(DEFAULT_SETTINGS.artifacts.artifact_root)
    compile_root = (
        Path(DEFAULT_SETTINGS.artifacts.compile_workspace_root)
        if DEFAULT_SETTINGS.artifacts.compile_workspace_root is not None
        else Path(tempfile.gettempdir())
    )
    return {
        "environment": DEFAULT_SETTINGS.environment.value,
        "metrics_enabled": DEFAULT_SETTINGS.metrics.enabled,
        "diagnostics_enabled": DEFAULT_SETTINGS.diagnostics.metrics_cli_enabled,
        "stage_metrics": {
            "path": str(metrics_path),
            "exists": metrics_path.exists(),
            "parent_exists": metrics_path.parent.exists(),
        },
        "cache_metrics": {
            "path": str(cache_metrics_path),
            "exists": cache_metrics_path.exists(),
            "parent_exists": cache_metrics_path.parent.exists(),
        },
        "artifacts": {
            "artifact_root": str(artifact_root),
            "artifact_root_exists": artifact_root.exists(),
            "compile_workspace_root": str(compile_root),
            "compile_workspace_cleanup_policy": DEFAULT_SETTINGS.artifacts.compile_workspace_cleanup_policy,
            "persist_sensitive_debug_artifacts": DEFAULT_SETTINGS.artifacts.persist_sensitive_debug_artifacts,
        },
        "privacy": {
            "safe_logging_enabled": DEFAULT_SETTINGS.privacy.safe_logging_enabled,
            "expose_internal_diagnostics": DEFAULT_SETTINGS.privacy.expose_internal_diagnostics,
        },
        "secret_status": DEFAULT_SETTINGS.secret_status_summary(),
    }


def build_run_summaries(records: list[StageMetricRecord], *, limit: int = 20) -> list[dict[str, object]]:
    """Aggregate stage metrics into recent run summaries."""

    grouped: dict[str, list[StageMetricRecord]] = defaultdict(list)
    for record in records:
        grouped[_run_key(record)].append(record)

    summaries: list[dict[str, object]] = []
    for run_key, run_records in grouped.items():
        ordered = sorted(run_records, key=lambda record: record.ended_at)
        started_at = min(record.started_at for record in ordered)
        ended_at = max(record.ended_at for record in ordered)
        failure_types = sorted({record.failure_type for record in ordered if record.failure_type})
        total_retries = sum(max(0, record.retry_count) for record in ordered)
        fallback_stage_count = sum(1 for record in ordered if record.fallback_used)
        failed_stage_count = sum(1 for record in ordered if not record.success)
        summaries.append(
            {
                "run_id": run_key if ordered[0].run_id is not None else None,
                "request_id": ordered[0].request_id,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "total_latency_ms": max(0, int((ended_at - started_at).total_seconds() * 1000)),
                "stage_count": len(ordered),
                "failed_stage_count": failed_stage_count,
                "status": "failed" if failed_stage_count else "completed",
                "failure_categories": failure_types,
                "retry_count": total_retries,
                "fallback_stage_count": fallback_stage_count,
                "last_stage": ordered[-1].stage_name,
            }
        )

    summaries.sort(key=lambda summary: str(summary["ended_at"]), reverse=True)
    return summaries[:limit]


def build_run_detail(records: list[StageMetricRecord], *, run_id: str) -> dict[str, object] | None:
    """Return one sanitized run view built only from stage metrics."""

    run_records = [record for record in records if _run_key(record) == run_id]
    if not run_records:
        return None

    summaries = build_run_summaries(run_records, limit=1)
    summary = summaries[0]
    ordered = sorted(run_records, key=lambda record: record.started_at)
    return {
        "run": summary,
        "stages": [
            {
                "stage_name": record.stage_name,
                "started_at": record.started_at.isoformat(),
                "ended_at": record.ended_at.isoformat(),
                "duration_ms": record.duration_ms,
                "success": record.success,
                "failure_type": record.failure_type,
                "retry_count": record.retry_count,
                "fallback_used": record.fallback_used,
                "output_metadata": sanitize_value(record.output_metadata),
            }
            for record in ordered
        ],
    }


def count_failure_categories(records: list[StageMetricRecord]) -> dict[str, int]:
    """Count stage failure categories across recent records."""

    failures = Counter(record.failure_type for record in records if record.failure_type)
    return dict(sorted(failures.items()))


def summarize_fallback_frequency(records: list[StageMetricRecord]) -> dict[str, object]:
    """Summarize fallback usage by stage and overall."""

    stage_totals: dict[str, int] = Counter(record.stage_name for record in records)
    fallback_totals: dict[str, int] = Counter(record.stage_name for record in records if record.fallback_used)
    by_stage: dict[str, dict[str, object]] = {}
    for stage_name in sorted(stage_totals):
        total = stage_totals[stage_name]
        fallbacks = fallback_totals.get(stage_name, 0)
        by_stage[stage_name] = {
            "fallbacks": fallbacks,
            "records": total,
            "fallback_rate": round(fallbacks / total, 4) if total else 0.0,
        }
    total_records = len(records)
    total_fallbacks = sum(fallback_totals.values())
    return {
        "fallbacks": total_fallbacks,
        "records": total_records,
        "fallback_rate": round(total_fallbacks / total_records, 4) if total_records else 0.0,
        "by_stage": by_stage,
    }


def summarize_retry_storms(records: list[StageMetricRecord], *, threshold: int = 3) -> dict[str, object]:
    """Identify runs with suspiciously high retry counts."""

    grouped: dict[str, list[StageMetricRecord]] = defaultdict(list)
    for record in records:
        grouped[_run_key(record)].append(record)

    flagged_runs: list[dict[str, object]] = []
    for run_key, run_records in grouped.items():
        retry_count = sum(max(0, record.retry_count) for record in run_records)
        if retry_count < threshold:
            continue
        ordered = sorted(run_records, key=lambda record: record.ended_at)
        flagged_runs.append(
            {
                "run_id": run_key if ordered[0].run_id is not None else None,
                "request_id": ordered[0].request_id,
                "retry_count": retry_count,
                "failed_stage_count": sum(1 for record in ordered if not record.success),
                "stages_with_retries": sorted(
                    {
                        record.stage_name
                        for record in ordered
                        if record.retry_count > 0
                    }
                ),
                "last_stage": ordered[-1].stage_name,
                "ended_at": ordered[-1].ended_at.isoformat(),
            }
        )
    flagged_runs.sort(key=lambda item: (item["retry_count"], str(item["ended_at"])), reverse=True)
    return {
        "threshold": threshold,
        "flagged_run_count": len(flagged_runs),
        "flagged_runs": flagged_runs,
    }


def summarize_cache_health(records: list[CacheMetricRecord]) -> dict[str, object]:
    """Return a cache operator summary with a coarse health status."""

    summary = summarize_cache_metrics(records)
    hit_rate = float(summary["hit_rate"])
    stale_invalidations = int(summary["stale_invalidations"])
    status = "healthy"
    if stale_invalidations > 0:
        status = "investigate"
    if hit_rate == 0.0 and (int(summary["hits"]) + int(summary["misses"])) > 0:
        status = "cold_or_misconfigured"
    return {
        **summary,
        "status": status,
    }


def list_safe_temp_workspaces(
    *,
    temp_root: Path | None = None,
    older_than_hours: float | None = None,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """List compiler temp workspaces that match the safe cleanup policy."""

    resolved_root = (temp_root or Path(tempfile.gettempdir())).resolve()
    current_time = now or datetime.now(UTC)
    workspaces: list[dict[str, object]] = []
    if not resolved_root.exists():
        return workspaces

    for path in sorted(resolved_root.iterdir()):
        if not path.is_dir() or not is_safe_compile_workspace(path):
            continue
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        age_hours = round((current_time - modified_at).total_seconds() / 3600, 2)
        if older_than_hours is not None and age_hours < older_than_hours:
            continue
        workspaces.append(
            {
                "path": str(path),
                "name": path.name,
                "modified_at": modified_at.isoformat(),
                "age_hours": age_hours,
            }
        )
    return workspaces


def purge_safe_temp_workspaces(
    *,
    temp_root: Path | None = None,
    older_than_hours: float = 24.0,
    now: datetime | None = None,
) -> dict[str, object]:
    """Delete only safe compile temp workspaces older than the given threshold."""

    candidates = list_safe_temp_workspaces(temp_root=temp_root, older_than_hours=older_than_hours, now=now)
    deleted: list[str] = []
    for workspace in candidates:
        cleanup_compile_workspace(str(workspace["path"]))
        deleted.append(str(workspace["path"]))
    return {
        "purged_count": len(deleted),
        "older_than_hours": older_than_hours,
        "purged_paths": deleted,
    }


def _run_key(record: StageMetricRecord) -> str:
    return record.run_id or record.request_id or "unknown"
