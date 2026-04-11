"""CLI entrypoint for the real end-to-end evaluation harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.evaluation import (
    DEFAULT_EVALUATION_OUTPUT_ROOT,
    EndToEndQualityScorer,
    EvaluationPackType,
    EvaluationRunnerConfig,
    JsonEvaluationCaseLoader,
    MarkdownJsonEvaluationReportWriter,
    LocalFileArtifactStore,
    OrchestratedRealPipelineRunner,
    RedTeamQualityScorer,
    render_aggregate_markdown_report,
    render_case_metrics_csv,
)
from backend.app.evaluation.aggregate_reporting import load_aggregate_report
from backend.app.evaluation.scorer import BasicExpectationScorer
from backend.app.evaluation.report_writer import (
    build_aggregate_json_report,
    render_compact_terminal_summary,
)
from backend.app.orchestration.enums import StageName, StageStatus
from backend.app.orchestration.pipeline_models import CompilePdfOutput, VerifyGeneratedContentOutput


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the real ResumeAI evaluation harness.")
    parser.add_argument("--case-file", type=Path, help="Path to one evaluation case JSON file.")
    parser.add_argument("--pack", choices=[item.value for item in EvaluationPackType], help="Run all cases in one fixture pack.")
    parser.add_argument("--use-live-llm", choices=["true", "false"], default="true")
    parser.add_argument("--enable-render", choices=["true", "false"], default="false")
    parser.add_argument("--persist-artifacts", choices=["true", "false"], default="true")
    parser.add_argument("--fail-fast", choices=["true", "false"], default="true")
    parser.add_argument("--stop-after", choices=["parse", "selection", "verification", "full"], default="full")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_EVALUATION_OUTPUT_ROOT)
    parser.add_argument(
        "--compare-to",
        type=Path,
        help="Path to a previous aggregate_report.json or prior evaluation output directory.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.case_file and not args.pack:
        raise SystemExit("one of --case-file or --pack is required")

    loader = JsonEvaluationCaseLoader()
    cases = [loader.load_case(args.case_file)] if args.case_file else loader.load_pack(EvaluationPackType(args.pack))
    config = EvaluationRunnerConfig(
        use_live_llm=args.use_live_llm == "true",
        enable_render=args.enable_render == "true",
        persist_artifacts=args.persist_artifacts == "true",
        fail_fast=args.fail_fast == "true",
        stop_after=args.stop_after,
    )
    artifact_store = LocalFileArtifactStore(args.output_root)
    runner = OrchestratedRealPipelineRunner()
    report_writer = MarkdownJsonEvaluationReportWriter()

    exit_code = 0
    rendered_results: list[dict[str, object]] = []
    previous_report = load_aggregate_report(args.compare_to) if args.compare_to else None
    for case in cases:
        if case.metadata.pack_type is EvaluationPackType.RED_TEAM:
            scorer = RedTeamQualityScorer()
        elif case.metadata.pack_type is EvaluationPackType.END_TO_END and config.use_live_llm:
            scorer = EndToEndQualityScorer()
        else:
            scorer = BasicExpectationScorer()
        run_result = runner.run_case_with_details(
            case,
            artifact_store=artifact_store,
            config=config,
        )
        scoring_summary = scorer.score_case(
            case,
            run_result.actual_outputs,
            run_result.artifact_manifest,
        )
        if run_result.run_summary.artifact_manifest_path is not None:
            report_path = report_writer.write_case_report(
                case=case,
                run_summary=run_result.run_summary,
                scoring_summary=scoring_summary,
                artifact_manifest=run_result.artifact_manifest,
                output_root=Path(run_result.run_summary.artifact_manifest_path).parent,
            )
            run_result.run_manifest.report_path = str(report_path)
        result_payload = {
            "case_id": case.metadata.case_id,
            "run_id": run_result.run_manifest.run_id,
            "pack_type": case.metadata.pack_type.value,
            "execution_mode": run_result.run_manifest.execution_mode,
            "run_status": run_result.run_manifest.run_status.value,
            "pipeline_status": (
                run_result.run_manifest.pipeline_status.value
                if run_result.run_manifest.pipeline_status is not None
                else None
            ),
            "outcome": scoring_summary.outcome.value,
            "overall_score": scoring_summary.overall_score,
            "metrics": [metric.model_dump(mode="json", exclude_none=True) for metric in scoring_summary.metrics],
            "reviewer_signals": [
                signal.model_dump(mode="json", exclude_none=True) for signal in scoring_summary.reviewer_signals
            ],
            "reviewer_comments": list(scoring_summary.reviewer_comments),
            "missing_dependencies": [
                item.model_dump(mode="json", exclude_none=True)
                for item in run_result.run_manifest.missing_dependencies
            ],
            "artifact_manifest_path": run_result.run_manifest.artifact_manifest_path,
            "report_path": run_result.run_manifest.report_path,
            "artifact_paths": dict(scoring_summary.artifact_paths),
            "final_message": run_result.run_manifest.final_message,
            "stages": [
                item.model_dump(mode="json", exclude_none=True)
                for item in run_result.run_manifest.stage_records
            ],
        }
        result_payload.update(_build_case_observation_snapshot(run_result.actual_outputs))
        rendered_results.append(result_payload)
        if run_result.run_manifest.run_status.value in {"failed", "error"} or scoring_summary.outcome.value == "fail":
            exit_code = 1

    aggregate_payload = build_aggregate_json_report(results=rendered_results, previous_report=previous_report)
    aggregate_path = args.output_root / "aggregate_report.json"
    aggregate_markdown_path = args.output_root / "aggregate_summary.md"
    aggregate_case_metrics_path = args.output_root / "aggregate_case_metrics.csv"
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(json.dumps(aggregate_payload, indent=2, sort_keys=True), encoding="utf-8")
    aggregate_markdown_path.write_text(render_aggregate_markdown_report(aggregate_payload), encoding="utf-8")
    aggregate_case_metrics_path.write_text(render_case_metrics_csv(rendered_results), encoding="utf-8")

    if args.json:
        print(
            json.dumps(
                {
                    **aggregate_payload,
                    "aggregate_report_path": str(aggregate_path),
                    "aggregate_markdown_path": str(aggregate_markdown_path),
                    "aggregate_case_metrics_path": str(aggregate_case_metrics_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(render_compact_terminal_summary(rendered_results, aggregate_payload))
        for item in rendered_results:
            if item["artifact_manifest_path"]:
                print(f"artifact_manifest={item['artifact_manifest_path']}")
            if item["report_path"]:
                print(f"report={item['report_path']}")
        print(f"aggregate_report={aggregate_path}")
        print(f"aggregate_markdown={aggregate_markdown_path}")
        print(f"aggregate_case_metrics={aggregate_case_metrics_path}")
    return exit_code


def _build_case_observation_snapshot(actual_outputs) -> dict[str, object]:
    verification_issue_count = 0
    verification_issue_categories: dict[str, int] = {}
    verification_issue_severity_counts: dict[str, int] = {}
    render_attempted = False
    render_success: bool | None = None

    for stage_output in actual_outputs.stage_outputs:
        if stage_output.status is not StageStatus.SUCCEEDED:
            continue
        if stage_output.stage_name is StageName.VERIFY_GENERATED_CONTENT:
            parsed = _safe_model_validate(VerifyGeneratedContentOutput, stage_output.output_snapshot)
            if parsed is not None:
                issues = [*parsed.verification_report.issues, *[issue for item in parsed.verification_report.item_results for issue in item.issues]]
                verification_issue_count = len(issues)
                for issue in issues:
                    verification_issue_categories[issue.category.value] = verification_issue_categories.get(issue.category.value, 0) + 1
                    verification_issue_severity_counts[issue.severity.value] = verification_issue_severity_counts.get(issue.severity.value, 0) + 1
        if stage_output.stage_name is StageName.COMPILE_PDF:
            render_attempted = True
            parsed_compile = _safe_model_validate(CompilePdfOutput, stage_output.output_snapshot)
            if parsed_compile is not None:
                render_success = parsed_compile.compile_result.compile_success

    return {
        "verification_issue_count": verification_issue_count,
        "verification_issue_categories": verification_issue_categories,
        "verification_issue_severity_counts": verification_issue_severity_counts,
        "render_attempted": render_attempted,
        "render_success": render_success,
    }


def _safe_model_validate(model_cls, snapshot: dict[str, object]):
    try:
        return model_cls.model_validate(snapshot or {})
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
