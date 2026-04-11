"""Run the Phase 1 gold evaluation suite."""

from __future__ import annotations

import argparse
from pathlib import Path

from resume_optimizer.phase1_eval import (
    DEFAULT_PHASE1_EVAL_FIXTURE_ROOT,
    phase1_eval_summary_json,
    render_phase1_eval_summary,
    run_phase1_eval,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 1 gold evaluation suite.")
    parser.add_argument("--case", action="append", dest="cases", help="Run only the named case_id. Repeatable.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text summary.")
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_PHASE1_EVAL_FIXTURE_ROOT,
        help="Directory containing Phase 1 eval fixtures.",
    )
    args = parser.parse_args()

    summary = run_phase1_eval(
        fixture_root=args.fixture_root,
        case_ids=args.cases,
    )
    output = phase1_eval_summary_json(summary) if args.json else render_phase1_eval_summary(summary)
    print(output)


if __name__ == "__main__":
    main()
