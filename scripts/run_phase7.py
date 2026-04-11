from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.evaluation.workflow import (
    WorkflowCheckResult,
    build_suite_report,
    evaluate_backend_live,
    evaluate_jd_parse_live,
    evaluate_selection_ci,
    load_phase7_thresholds,
    render_suite_markdown,
)
from src.resume_optimizer.evaluation import (
    render_jd_parse_summary,
    render_jd_parse_summary_json,
    render_selection_summary,
    render_selection_summary_json,
    run_jd_parse_evaluation,
    run_selection_evaluation,
)


MODE_CHOICES = ("ci-safe", "local-full", "live")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 7 evaluation workflow commands.")
    parser.add_argument(
        "command",
        choices=("run_jd_eval", "run_selection_eval", "run_e2e_eval", "run_red_team_eval", "run_all_phase7"),
    )
    parser.add_argument("--mode", choices=MODE_CHOICES, default="local-full")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/phase7_workflow"),
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=Path("fixtures/evaluation/phase7_thresholds.json"),
    )
    parser.add_argument("--enable-render", choices=("true", "false"), default="false")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = load_phase7_thresholds(args.thresholds.resolve())
    suite_root = (args.output_root / args.command / args.mode).resolve()
    suite_root.mkdir(parents=True, exist_ok=True)

    checks: list[WorkflowCheckResult] = []
    if args.command in {"run_jd_eval", "run_all_phase7"}:
        checks.append(_run_jd_eval(mode=args.mode, output_root=suite_root / "jd_parse", thresholds=thresholds))
    if args.command in {"run_selection_eval", "run_all_phase7"}:
        checks.append(_run_selection_eval(mode=args.mode, output_root=suite_root / "selection", thresholds=thresholds))
    if args.command in {"run_e2e_eval", "run_all_phase7"}:
        checks.append(
            _run_backend_pack(
                name="end_to_end",
                mode=args.mode,
                output_root=suite_root / "end_to_end",
                thresholds=thresholds,
                enable_render=args.enable_render == "true",
            )
        )
    if args.command in {"run_red_team_eval", "run_all_phase7"}:
        checks.append(
            _run_backend_pack(
                name="red_team",
                mode=args.mode,
                output_root=suite_root / "red_team",
                thresholds=thresholds,
                enable_render=False,
            )
        )

    report = build_suite_report(mode=args.mode, command=args.command, checks=checks)
    summary_json_path = suite_root / "suite_summary.json"
    summary_md_path = suite_root / "suite_summary.md"
    summary_json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary_md_path.write_text(render_suite_markdown(report), encoding="utf-8")

    exit_code = 1 if any(check.status == "fail" for check in checks) else 0
    if args.json:
        print(json.dumps({**report, "suite_summary_json": str(summary_json_path), "suite_summary_md": str(summary_md_path)}, indent=2, sort_keys=True))
    else:
        print(render_suite_markdown(report))
        print(f"suite_summary_json={summary_json_path}")
        print(f"suite_summary_md={summary_md_path}")
    return exit_code


def _run_jd_eval(*, mode: str, output_root: Path, thresholds: dict[str, object]) -> WorkflowCheckResult:
    output_root.mkdir(parents=True, exist_ok=True)
    if mode != "live":
        return WorkflowCheckResult(
            name="jd_parse",
            status="skip",
            confidence_level="skip",
            message="jd_parse evaluation requires live model access and is skipped outside live mode.",
        )

    summaries = []
    for pack_path in sorted((REPO_ROOT / "fixtures" / "evaluation" / "jd_parse").glob("*.yaml")):
        summary = run_jd_parse_evaluation(pack_path)
        summaries.append(summary)
        (output_root / f"{pack_path.stem}.md").write_text(render_jd_parse_summary(summary), encoding="utf-8")
        (output_root / f"{pack_path.stem}.json").write_text(render_jd_parse_summary_json(summary), encoding="utf-8")

    combined = _combine_jd_summaries(summaries)
    check = evaluate_jd_parse_live(combined, thresholds["live"]["jd_parse"])
    check.artifact_paths = {
        "summary_dir": str(output_root),
    }
    return check


def _run_selection_eval(*, mode: str, output_root: Path, thresholds: dict[str, object]) -> WorkflowCheckResult:
    output_root.mkdir(parents=True, exist_ok=True)
    pack_path = REPO_ROOT / "fixtures" / "evaluation" / "selection" / "backend_selection.yaml"
    summary = run_selection_evaluation(pack_path)
    (output_root / "selection_summary.md").write_text(render_selection_summary(summary), encoding="utf-8")
    (output_root / "selection_summary.json").write_text(render_selection_summary_json(summary), encoding="utf-8")
    check = evaluate_selection_ci(summary, thresholds["ci_safe"]["selection"])
    check.artifact_paths = {
        "summary_md": str(output_root / "selection_summary.md"),
        "summary_json": str(output_root / "selection_summary.json"),
    }
    return check


def _run_backend_pack(
    *,
    name: str,
    mode: str,
    output_root: Path,
    thresholds: dict[str, object],
    enable_render: bool,
) -> WorkflowCheckResult:
    output_root.mkdir(parents=True, exist_ok=True)
    use_live = mode == "live"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "backend" / "app" / "scripts" / "run_real_evaluation.py"),
        "--pack",
        name,
        "--use-live-llm",
        "true" if use_live else "false",
        "--enable-render",
        "true" if enable_render and use_live else "false",
        "--persist-artifacts",
        "true",
        "--fail-fast",
        "false",
        "--output-root",
        str(output_root),
        "--json",
    ]
    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_path = output_root / "command.stdout.log"
    stderr_path = output_root / "command.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    payload = _extract_json_payload(completed.stdout)
    if payload is None:
        return WorkflowCheckResult(
            name=name,
            status="fail",
            confidence_level="smoke" if not use_live else "quality",
            message=f"{name} evaluation did not emit parseable JSON output.",
            findings=[f"exit_code={completed.returncode}"],
            artifact_paths={"stdout": str(stdout_path), "stderr": str(stderr_path)},
        )

    if not use_live:
        status = "pass" if Path(payload["aggregate_report_path"]).exists() else "fail"
        message = (
            f"{name} dry-run smoke completed; artifacts persisted but result is not confidence-bearing."
            if status == "pass"
            else f"{name} dry-run smoke failed to persist expected artifacts."
        )
        return WorkflowCheckResult(
            name=name,
            status=status,
            confidence_level="smoke",
            message=message,
            artifact_paths={
                "aggregate_report": str(payload.get("aggregate_report_path")),
                "aggregate_markdown": str(payload.get("aggregate_markdown_path")),
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            },
        )

    check = evaluate_backend_live(name=name, aggregate_payload=payload, thresholds=thresholds["live"][name])
    check.artifact_paths = {
        "aggregate_report": str(payload.get("aggregate_report_path")),
        "aggregate_markdown": str(payload.get("aggregate_markdown_path")),
        "aggregate_case_metrics": str(payload.get("aggregate_case_metrics_path")),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }
    return check


def _extract_json_payload(stdout: str) -> dict[str, object] | None:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _combine_jd_summaries(summaries: list[object]) -> object:
    if not summaries:
        raise ValueError("at least one jd_parse summary is required")
    total_cases = sum(summary.total_cases for summary in summaries)
    passed_cases = sum(summary.passed_cases for summary in summaries)
    failed_cases = sum(summary.failed_cases for summary in summaries)
    return type(summaries[0])(
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        title_accuracy=sum(summary.title_accuracy * summary.total_cases for summary in summaries) / total_cases,
        role_family_accuracy=sum(summary.role_family_accuracy * summary.total_cases for summary in summaries) / total_cases,
        org_mode_accuracy=sum(summary.org_mode_accuracy * summary.total_cases for summary in summaries) / total_cases,
        seniority_accuracy=sum(summary.seniority_accuracy * summary.total_cases for summary in summaries) / total_cases,
        must_have_skill_recall=sum(summary.must_have_skill_recall * summary.total_cases for summary in summaries) / total_cases,
        nice_to_have_skill_recall=sum(summary.nice_to_have_skill_recall * summary.total_cases for summary in summaries) / total_cases,
        responsibility_recall=sum(summary.responsibility_recall * summary.total_cases for summary in summaries) / total_cases,
        average_confidence=sum(summary.average_confidence * summary.total_cases for summary in summaries) / total_cases,
        case_results=[case for summary in summaries for case in summary.case_results],
    )


if __name__ == "__main__":
    raise SystemExit(main())
