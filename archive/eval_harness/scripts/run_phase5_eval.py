"""Run the Phase 5 bounded-generation regression harness."""

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

from resume_optimizer.phase5_eval import (
    phase5_eval_summary_json,
    render_phase5_eval_summary,
    run_phase5_eval,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 5 bounded-generation regression harness.")
    parser.add_argument("--case", action="append", dest="cases", help="Run only the named case_id. Repeatable.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text summary.")
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="Override the evaluation reference date in YYYY-MM-DD format.",
    )
    args = parser.parse_args()

    summary = run_phase5_eval(case_ids=args.cases, today=args.today or date(2026, 4, 9))
    output = phase5_eval_summary_json(summary) if args.json else render_phase5_eval_summary(summary)
    print(output)


if __name__ == "__main__":
    main()
