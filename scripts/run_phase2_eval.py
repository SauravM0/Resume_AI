#!/usr/bin/env python3
"""Run the Phase 2 evaluation matrix from local fixtures."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from resume_optimizer.phase2_eval import (
    DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
    Phase2EvalFixtureError,
    phase2_eval_summary_json,
    render_phase2_eval_summary,
    run_phase2_eval,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 2 evaluation matrix.")
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
        help="Path to the Phase 2 eval fixture root.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Run only the named eval case. Can be passed multiple times.",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override the evaluation date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of the human-readable report.",
    )
    args = parser.parse_args()

    try:
        summary = run_phase2_eval(
            fixture_root=args.fixture_root,
            case_ids=args.cases,
            today=date.fromisoformat(args.today) if args.today else None,
        )
    except Phase2EvalFixtureError as exc:
        print(f"Phase 2 eval fixture error: {exc}", file=sys.stderr)
        return 2
    output = (
        phase2_eval_summary_json(summary)
        if args.json
        else render_phase2_eval_summary(summary)
    )
    print(output)
    return 1 if summary.failed_cases else 0


if __name__ == "__main__":
    sys.exit(main())
