#!/usr/bin/env python3
"""Run deterministic Phase 6 orchestration regression cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.tests.orchestration.pipeline_harness import load_pipeline_cases, run_pipeline_cases

DEFAULT_CASES_PATH = REPO_ROOT / "backend/tests/fixtures/pipeline_cases/regression_cases.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 6 pipeline regression cases.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to a pipeline case JSON file.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Optional durable artifact root for regression outputs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for the structured JSON report.",
    )
    args = parser.parse_args()

    cases = load_pipeline_cases(args.cases)
    report = run_pipeline_cases(cases, artifact_root=args.artifact_root)
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
