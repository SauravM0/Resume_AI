"""Filesystem-backed cache for safe deterministic intermediate artifacts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from typing import TypeVar

from backend.app.cache.metrics import record_cache_metric
from backend.app.cache.models import CacheEntryRecord
from backend.app.observability import log_event
from resume_optimizer.config import DEFAULT_SETTINGS

T = TypeVar("T")
logger = logging.getLogger(__name__)

DEFAULT_CACHE_ROOT = Path("data/cache")
DEFAULT_CACHE_MAX_ENTRIES = 256


class LocalJsonCache:
    """Small local JSON cache with TTL, bounded size, and explicit invalidation."""

    def __init__(self, root: Path, *, max_entries: int = DEFAULT_CACHE_MAX_ENTRIES) -> None:
        self.root = root
        self.max_entries = max_entries

    def get_entry(self, *, namespace: str, key: str) -> tuple[str, CacheEntryRecord | None]:
        path = self._entry_path(namespace=namespace, key=key)
        if not path.exists():
            return "miss", None
        try:
            entry = CacheEntryRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            path.unlink(missing_ok=True)
            return "miss", None
        if entry.expires_at is not None and entry.expires_at <= datetime.now(timezone.utc):
            path.unlink(missing_ok=True)
            return "stale", None
        return "hit", entry

    def set_entry(
        self,
        *,
        namespace: str,
        key: str,
        payload: dict[str, object],
        ttl_seconds: int | None,
        compute_duration_ms: int,
        metadata: dict[str, object] | None = None,
    ) -> CacheEntryRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        entry = CacheEntryRecord(
            namespace=namespace,
            key=key,
            created_at=now,
            expires_at=(now + timedelta(seconds=ttl_seconds)) if ttl_seconds else None,
            compute_duration_ms=max(0, compute_duration_ms),
            payload=payload,
            metadata=metadata or {},
        )
        path = self._entry_path(namespace=namespace, key=key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(entry.model_dump(mode="json"), separators=(",", ":")),
            encoding="utf-8",
        )
        self._prune()
        return entry

    def invalidate(self, *, namespace: str, key: str) -> bool:
        path = self._entry_path(namespace=namespace, key=key)
        if not path.exists():
            return False
        path.unlink()
        record_cache_metric(namespace=namespace, event="invalidate", metadata={"key": key})
        return True

    def clear_namespace(self, namespace: str) -> int:
        namespace_root = self.root / namespace
        if not namespace_root.exists():
            return 0
        removed = 0
        for path in namespace_root.glob("*.json"):
            path.unlink()
            removed += 1
        record_cache_metric(namespace=namespace, event="invalidate_namespace", metadata={"removed": removed})
        return removed

    def _entry_path(self, *, namespace: str, key: str) -> Path:
        return self.root / namespace / f"{key}.json"

    def _prune(self) -> None:
        entries = list(self.root.glob("*/*.json"))
        if len(entries) <= self.max_entries:
            return
        entries.sort(key=lambda path: path.stat().st_mtime)
        for path in entries[: max(0, len(entries) - self.max_entries)]:
            path.unlink(missing_ok=True)


def build_default_cache() -> LocalJsonCache:
    return LocalJsonCache(
        DEFAULT_SETTINGS.cache.root or DEFAULT_CACHE_ROOT,
        max_entries=DEFAULT_SETTINGS.cache.max_entries or DEFAULT_CACHE_MAX_ENTRIES,
    )


DEFAULT_SAFE_CACHE = build_default_cache()


def get_or_compute(
    *,
    namespace: str,
    key: str,
    compute: Callable[[], T],
    serialize: Callable[[T], dict[str, object]],
    deserialize: Callable[[dict[str, object]], T],
    ttl_seconds: int | None = None,
    metadata: dict[str, object] | None = None,
    cache: LocalJsonCache | None = None,
) -> tuple[T, bool]:
    """Return a cached deterministic value or compute and persist it."""

    resolved_cache = cache or DEFAULT_SAFE_CACHE
    status, entry = resolved_cache.get_entry(namespace=namespace, key=key)
    if status == "hit" and entry is not None:
        record_cache_metric(
            namespace=namespace,
            event="hit",
            hit=True,
            latency_saved_estimate_ms=entry.compute_duration_ms,
            metadata={"key": key},
        )
        log_event(
            logger,
            service="resume_optimizer.cache",
            event_name="cache_hit",
            outcome="success",
            duration_ms=entry.compute_duration_ms,
            metadata={"namespace": namespace},
        )
        return deserialize(entry.payload), True
    if status == "stale":
        record_cache_metric(
            namespace=namespace,
            event="stale_invalidation",
            stale_invalidation=True,
            metadata={"key": key},
        )
        log_event(
            logger,
            service="resume_optimizer.cache",
            event_name="cache_stale_invalidated",
            outcome="success",
            metadata={"namespace": namespace},
        )

    started_at = datetime.now(timezone.utc)
    value = compute()
    compute_duration_ms = max(0, int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000))
    resolved_cache.set_entry(
        namespace=namespace,
        key=key,
        payload=serialize(value),
        ttl_seconds=ttl_seconds,
        compute_duration_ms=compute_duration_ms,
        metadata=metadata,
    )
    record_cache_metric(
        namespace=namespace,
        event="miss",
        hit=False,
        metadata={"key": key},
    )
    log_event(
        logger,
        service="resume_optimizer.cache",
        event_name="cache_miss",
        outcome="success",
        duration_ms=compute_duration_ms,
        metadata={"namespace": namespace},
    )
    return value, False
