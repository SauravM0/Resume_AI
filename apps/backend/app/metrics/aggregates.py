"""Aggregate summaries for recorded stage metrics."""

from __future__ import annotations

from collections import defaultdict
from math import ceil

from backend.app.metrics.models import StageMetricRecord


def summarize_stage_metrics(records: list[StageMetricRecord]) -> dict[str, object]:
    """Compute per-stage percentiles and request latency summaries."""

    stage_groups: dict[str, list[StageMetricRecord]] = defaultdict(list)
    request_groups: dict[str, list[StageMetricRecord]] = defaultdict(list)
    for record in records:
        stage_groups[record.stage_name].append(record)
        if record.request_id is not None:
            request_groups[record.request_id].append(record)

    return {
        "record_count": len(records),
        "request_count": len(request_groups),
        "stage_summaries": {
            stage_name: _stage_summary(stage_records)
            for stage_name, stage_records in sorted(stage_groups.items())
        },
        "request_latency_ms": _request_latency_summary(request_groups),
    }


def _stage_summary(records: list[StageMetricRecord]) -> dict[str, object]:
    durations = [record.duration_ms for record in records]
    total = len(records)
    failures = sum(1 for record in records if not record.success)
    retries = sum(1 for record in records if record.retry_count > 0)
    fallbacks = sum(1 for record in records if record.fallback_used)
    return {
        "count": total,
        "p50_duration_ms": _percentile(durations, 50),
        "p95_duration_ms": _percentile(durations, 95),
        "p99_duration_ms": _percentile(durations, 99),
        "failure_rate": failures / total if total else 0.0,
        "retry_rate": retries / total if total else 0.0,
        "fallback_rate": fallbacks / total if total else 0.0,
    }


def _request_latency_summary(grouped_records: dict[str, list[StageMetricRecord]]) -> dict[str, object]:
    latencies: list[int] = []
    for records in grouped_records.values():
        started_at = min(record.started_at for record in records)
        ended_at = max(record.ended_at for record in records)
        latencies.append(max(0, int((ended_at - started_at).total_seconds() * 1000)))
    return {
        "p50": _percentile(latencies, 50),
        "p95": _percentile(latencies, 95),
        "p99": _percentile(latencies, 99),
    }


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, ceil((percentile / 100) * len(ordered)) - 1)
    return ordered[index]
