"""Run the Phase 3 gold selection evaluation suite."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from resume_optimizer.phase3_eval import (
    DEFAULT_PHASE3_EVAL_FIXTURE_ROOT,
    phase3_eval_summary_json,
    render_phase3_eval_summary,
    run_phase3_eval,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 3 gold selection evaluation suite.")
    parser.add_argument("--case", action="append", dest="cases", help="Run only the named case_id. Repeatable.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text summary.")
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_PHASE3_EVAL_FIXTURE_ROOT,
        help="Directory containing Phase 3 eval fixtures.",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="Override the evaluation reference date in YYYY-MM-DD format.",
    )
    args = parser.parse_args()

    summary = run_phase3_eval(
        fixture_root=args.fixture_root,
        case_ids=args.cases,
        today=args.today,
    )
    output = phase3_eval_summary_json(summary) if args.json else render_phase3_eval_summary(summary)
    print(output)


if __name__ == "__main__":
    main()
