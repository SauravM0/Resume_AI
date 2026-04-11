"""CLI entrypoint for the Phase 8 release-readiness suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.app.phase8.suite import render_human_report, run_phase8_suite


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 8 production-hardening verification suite.")
    parser.add_argument(
        "--profile",
        choices=("quick", "full"),
        default="quick",
        help="Verification profile to run. Use full before release.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional file path to save the generated report.",
    )
    parser.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="Additional argument to pass through to pytest. Can be repeated.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = run_phase8_suite(profile=args.profile, extra_pytest_args=args.pytest_arg)
    rendered = (
        json.dumps(report.to_dict(), indent=2, sort_keys=True)
        if args.format == "json"
        else render_human_report(report)
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.overall_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
