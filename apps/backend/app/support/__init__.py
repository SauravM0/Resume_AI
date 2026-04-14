"""Operator-safe support tooling for recent runs and system diagnostics."""

from .tooling import (
    build_health_snapshot,
    build_run_detail,
    build_run_summaries,
    count_failure_categories,
    list_safe_temp_workspaces,
    purge_safe_temp_workspaces,
    summarize_cache_health,
    summarize_fallback_frequency,
    summarize_retry_storms,
)

__all__ = [
    "build_health_snapshot",
    "build_run_detail",
    "build_run_summaries",
    "count_failure_categories",
    "list_safe_temp_workspaces",
    "purge_safe_temp_workspaces",
    "summarize_cache_health",
    "summarize_fallback_frequency",
    "summarize_retry_storms",
]
