"""CLI entrypoint for local pipeline profiling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.profiling.report import compare_batch_reports, render_batch_summary, render_comparison_summary
from backend.app.profiling.runner import (
    DEFAULT_DETERMINISTIC_CASES_PATH,
    PipelineProfilingRunner,
    load_deterministic_cases,
    load_real_cases,
)
from backend.app.profiling.models import ProfilingBatchReport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile the resume generation pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a profiling batch.")
    run_parser.add_argument("--mode", choices=["deterministic", "real-dry-run", "real-live"], default="deterministic")
    run_parser.add_argument("--cases", type=Path, default=DEFAULT_DETERMINISTIC_CASES_PATH)
    run_parser.add_argument("--case-file", type=Path, default=None)
    run_parser.add_argument("--pack", default="end_to_end")
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--artifact-root", type=Path, default=None)
    run_parser.add_argument("--output-root", type=Path, default=None)
    run_parser.add_argument("--stop-after", default="full")
    run_parser.add_argument("--output", type=Path, default=None)
    run_parser.add_argument("--json", action="store_true")

    compare_parser = subparsers.add_parser("compare", help="Compare two saved profiling reports.")
    compare_parser.add_argument("--left", type=Path, required=True)
    compare_parser.add_argument("--right", type=Path, required=True)
    compare_parser.add_argument("--left-label", default="baseline")
    compare_parser.add_argument("--right-label", default="candidate")

    args = parser.parse_args(argv)
    if args.command == "run":
        runner = PipelineProfilingRunner()
        if args.mode == "deterministic":
            report = runner.profile_deterministic_cases(
                load_deterministic_cases(args.cases),
                artifact_root=args.artifact_root,
                limit=args.limit,
            )
        else:
            report = runner.profile_real_cases(
                load_real_cases(case_file=args.case_file, pack=args.pack),
                output_root=args.output_root,
                use_live_llm=args.mode == "real-live",
                enable_render=args.stop_after == "full",
                stop_after=args.stop_after,
                limit=args.limit,
            )
        rendered = json.dumps(report.model_dump(mode="json", exclude_none=True), indent=2, sort_keys=True)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered if args.json else render_batch_summary(report))
        return 0

    left = ProfilingBatchReport.model_validate(json.loads(args.left.read_text(encoding="utf-8")))
    right = ProfilingBatchReport.model_validate(json.loads(args.right.read_text(encoding="utf-8")))
    comparison = compare_batch_reports(
        left,
        right,
        baseline_label=args.left_label,
        candidate_label=args.right_label,
    )
    print(render_comparison_summary(comparison))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
