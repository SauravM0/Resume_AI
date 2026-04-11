"""Serializable models for safe deterministic cache entries and metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CacheEntryRecord(BaseModel):
    """One persisted cache entry envelope."""

    namespace: str
    key: str
    created_at: datetime
    expires_at: datetime | None = None
    compute_duration_ms: int = Field(default=0, ge=0)
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class CacheMetricRecord(BaseModel):
    """One cache access or invalidation metric record."""

    timestamp: datetime
    namespace: str
    event: str
    hit: bool = False
    stale_invalidation: bool = False
    latency_saved_estimate_ms: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
