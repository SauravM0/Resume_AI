"""Developer-only CLI for inspecting recent stage metrics."""

from __future__ import annotations

import argparse
import json

from backend.app.metrics import DEFAULT_STAGE_METRICS_STORE, summarize_stage_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect internal stage metrics.")
    parser.add_argument("--limit", type=int, default=200, help="Number of recent stage records to summarize.")
    args = parser.parse_args()
    records = DEFAULT_STAGE_METRICS_STORE.load(limit=args.limit)
    print(json.dumps(summarize_stage_metrics(records), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
