"""Operator-safe CLI for recent run inspection and temp cleanup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.app.cache.metrics import DEFAULT_CACHE_METRICS_STORE
from backend.app.metrics import DEFAULT_STAGE_METRICS_STORE
from backend.app.support.tooling import (
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect recent pipeline runs with sanitized operator views.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Show active runtime paths and safety flags.")
    health_parser.set_defaults(handler=_cmd_health)

    recent_parser = subparsers.add_parser("recent-runs", help="List recent runs from stage metrics.")
    recent_parser.add_argument("--limit", type=int, default=20, help="Maximum number of recent runs to print.")
    recent_parser.add_argument(
        "--metrics-limit",
        type=int,
        default=500,
        help="Maximum number of recent stage metric records to scan.",
    )
    recent_parser.set_defaults(handler=_cmd_recent_runs)

    show_parser = subparsers.add_parser("show-run", help="Show sanitized metadata and stage timings for one run.")
    show_parser.add_argument("--run-id", required=True, help="Run identifier to inspect.")
    show_parser.add_argument(
        "--metrics-limit",
        type=int,
        default=1000,
        help="Maximum number of recent stage metric records to scan.",
    )
    show_parser.set_defaults(handler=_cmd_show_run)

    diagnostics_parser = subparsers.add_parser(
        "safe-diagnostics",
        help="Print the same sanitized run view intended for support diagnostics.",
    )
    diagnostics_parser.add_argument("--run-id", required=True, help="Run identifier to inspect.")
    diagnostics_parser.add_argument(
        "--metrics-limit",
        type=int,
        default=1000,
        help="Maximum number of recent stage metric records to scan.",
    )
    diagnostics_parser.set_defaults(handler=_cmd_show_run)

    failures_parser = subparsers.add_parser("failure-counts", help="Count recent stage failure categories.")
    failures_parser.add_argument("--limit", type=int, default=1000, help="Number of recent stage records to scan.")
    failures_parser.set_defaults(handler=_cmd_failure_counts)

    fallback_parser = subparsers.add_parser("fallback-frequency", help="Summarize fallback frequency by stage.")
    fallback_parser.add_argument("--limit", type=int, default=1000, help="Number of recent stage records to scan.")
    fallback_parser.set_defaults(handler=_cmd_fallback_frequency)

    retry_parser = subparsers.add_parser("retry-storms", help="Flag runs with elevated retry activity.")
    retry_parser.add_argument("--limit", type=int, default=1000, help="Number of recent stage records to scan.")
    retry_parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Minimum summed retry count required to flag a run.",
    )
    retry_parser.set_defaults(handler=_cmd_retry_storms)

    cache_parser = subparsers.add_parser("cache-summary", help="Summarize recent cache hits, misses, and invalidations.")
    cache_parser.add_argument("--limit", type=int, default=1000, help="Number of recent cache metric records to scan.")
    cache_parser.set_defaults(handler=_cmd_cache_summary)

    temp_parser = subparsers.add_parser("temp-artifacts", help="List or safely purge temp compile workspaces.")
    temp_parser.add_argument(
        "--older-than-hours",
        type=float,
        default=24.0,
        help="Only target temp workspaces older than this age.",
    )
    temp_parser.add_argument(
        "--temp-root",
        type=Path,
        default=None,
        help="Optional temp root to scan instead of the process temp directory.",
    )
    temp_parser.add_argument(
        "--purge",
        action="store_true",
        help="Delete matching temp workspaces after listing them.",
    )
    temp_parser.set_defaults(handler=_cmd_temp_artifacts)

    args = parser.parse_args(list(argv) if argv is not None else None)
    payload = args.handler(args)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_health(_: argparse.Namespace) -> dict[str, object]:
    return build_health_snapshot()


def _cmd_recent_runs(args: argparse.Namespace) -> dict[str, object]:
    records = DEFAULT_STAGE_METRICS_STORE.load(limit=args.metrics_limit)
    return {
        "metrics_records_scanned": len(records),
        "runs": build_run_summaries(records, limit=args.limit),
    }


def _cmd_show_run(args: argparse.Namespace) -> dict[str, object]:
    records = DEFAULT_STAGE_METRICS_STORE.load(limit=args.metrics_limit)
    detail = build_run_detail(records, run_id=args.run_id)
    if detail is None:
        raise SystemExit(f"Run not found in the most recent {args.metrics_limit} stage metric records: {args.run_id}")
    return detail


def _cmd_failure_counts(args: argparse.Namespace) -> dict[str, object]:
    records = DEFAULT_STAGE_METRICS_STORE.load(limit=args.limit)
    return {
        "metrics_records_scanned": len(records),
        "failure_category_counts": count_failure_categories(records),
    }


def _cmd_fallback_frequency(args: argparse.Namespace) -> dict[str, object]:
    records = DEFAULT_STAGE_METRICS_STORE.load(limit=args.limit)
    return {
        "metrics_records_scanned": len(records),
        **summarize_fallback_frequency(records),
    }


def _cmd_retry_storms(args: argparse.Namespace) -> dict[str, object]:
    records = DEFAULT_STAGE_METRICS_STORE.load(limit=args.limit)
    return {
        "metrics_records_scanned": len(records),
        **summarize_retry_storms(records, threshold=args.threshold),
    }


def _cmd_cache_summary(args: argparse.Namespace) -> dict[str, object]:
    records = DEFAULT_CACHE_METRICS_STORE.load(limit=args.limit)
    return {
        "metrics_records_scanned": len(records),
        **summarize_cache_health(records),
    }


def _cmd_temp_artifacts(args: argparse.Namespace) -> dict[str, object]:
    listed = list_safe_temp_workspaces(
        temp_root=args.temp_root,
        older_than_hours=args.older_than_hours,
    )
    payload: dict[str, object] = {
        "older_than_hours": args.older_than_hours,
        "workspace_count": len(listed),
        "workspaces": listed,
    }
    if args.purge:
        payload["purge"] = purge_safe_temp_workspaces(
            temp_root=args.temp_root,
            older_than_hours=args.older_than_hours,
        )
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
