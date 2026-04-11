"""Local cache metrics recording and aggregation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from backend.app.cache.models import CacheMetricRecord
from resume_optimizer.config import DEFAULT_SETTINGS

DEFAULT_CACHE_METRICS_PATH = Path("data/metrics/cache_metrics.jsonl")


class JsonlCacheMetricsStore:
    """Append-only JSONL cache metrics store."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: CacheMetricRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), separators=(",", ":")))
            handle.write("\n")

    def load(self, *, limit: int | None = None) -> list[CacheMetricRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if limit is not None:
            lines = lines[-limit:]
        records: list[CacheMetricRecord] = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                records.append(CacheMetricRecord.model_validate_json(stripped))
        return records


def build_default_cache_metrics_store() -> JsonlCacheMetricsStore:
    configured = DEFAULT_SETTINGS.metrics.cache_metrics_path
    return JsonlCacheMetricsStore(Path(configured) if configured else DEFAULT_CACHE_METRICS_PATH)


DEFAULT_CACHE_METRICS_STORE = build_default_cache_metrics_store()


def record_cache_metric(
    *,
    namespace: str,
    event: str,
    hit: bool = False,
    stale_invalidation: bool = False,
    latency_saved_estimate_ms: int = 0,
    metadata: dict[str, object] | None = None,
    store: JsonlCacheMetricsStore | None = None,
) -> CacheMetricRecord:
    """Persist one cache metric event."""

    record = CacheMetricRecord(
        timestamp=datetime.now(timezone.utc),
        namespace=namespace,
        event=event,
        hit=hit,
        stale_invalidation=stale_invalidation,
        latency_saved_estimate_ms=max(0, latency_saved_estimate_ms),
        metadata=metadata or {},
    )
    (store or DEFAULT_CACHE_METRICS_STORE).append(record)
    return record


def summarize_cache_metrics(records: list[CacheMetricRecord]) -> dict[str, object]:
    """Compute hit/miss and stale invalidation summaries."""

    accesses = [record for record in records if record.event in {"hit", "miss"}]
    hit_count = sum(1 for record in accesses if record.hit)
    miss_count = sum(1 for record in accesses if not record.hit)
    stale_invalidation_count = sum(1 for record in records if record.stale_invalidation)
    total_latency_saved_ms = sum(record.latency_saved_estimate_ms for record in records)
    by_namespace: dict[str, dict[str, object]] = {}
    for namespace in sorted({record.namespace for record in records}):
        namespace_records = [record for record in records if record.namespace == namespace]
        namespace_accesses = [record for record in namespace_records if record.event in {"hit", "miss"}]
        namespace_hits = sum(1 for record in namespace_accesses if record.hit)
        namespace_misses = sum(1 for record in namespace_accesses if not record.hit)
        total = namespace_hits + namespace_misses
        by_namespace[namespace] = {
            "hits": namespace_hits,
            "misses": namespace_misses,
            "hit_rate": round(namespace_hits / total, 4) if total else 0.0,
            "stale_invalidations": sum(1 for record in namespace_records if record.stale_invalidation),
            "latency_saved_estimate_ms": sum(record.latency_saved_estimate_ms for record in namespace_records),
        }
    total_accesses = hit_count + miss_count
    return {
        "hits": hit_count,
        "misses": miss_count,
        "hit_rate": round(hit_count / total_accesses, 4) if total_accesses else 0.0,
        "stale_invalidations": stale_invalidation_count,
        "latency_saved_estimate_ms": total_latency_saved_ms,
        "namespaces": by_namespace,
    }
