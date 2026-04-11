from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.profiling.cli import main
from backend.app.profiling.models import (
    ProfilingBatchReport,
    ProfilingBottleneckFlag,
    ProfilingOutputSizeSummary,
    ProfilingRunReport,
    ProfilingStageBreakdown,
)
from backend.app.profiling.report import compare_batch_reports, summarize_profile_runs
from backend.app.profiling.runner import PipelineProfilingRunner, load_deterministic_cases


def test_profiling_runner_executes_deterministic_batch(tmp_path: Path) -> None:
    runner = PipelineProfilingRunner()
    cases = load_deterministic_cases()[:2]

    report = runner.profile_deterministic_cases(cases, artifact_root=tmp_path / "artifacts")

    assert report.profile_mode == "deterministic"
    assert report.run_count == 2
    assert len(report.runs) == 2
    assert report.slowest_stage_by_avg is not None
    assert all(run.total_latency_ms >= 0 for run in report.runs)
    assert all(run.stage_breakdown for run in report.runs)
    assert all(run.slowest_stage is not None for run in report.runs)


def test_profiling_report_flags_artificial_bottlenecks() -> None:
    run_a = ProfilingRunReport(
        profile_mode="deterministic",
        case_id="slow.a",
        scenario="slow_case",
        run_id="run.slow.a",
        total_latency_ms=5200,
        slowest_stage="compile_pdf",
        status="succeeded",
        retry_count=2,
        fallback_count=1,
        output_sizes=ProfilingOutputSizeSummary(
            artifact_count=2,
            total_size_bytes=2_100_000,
            largest_artifact_bytes=900_000,
            artifact_kinds=["pdf"],
        ),
        stage_breakdown=[
            ProfilingStageBreakdown(
                stage_name="compile_pdf",
                total_duration_ms=3500,
                average_duration_ms=3500,
                max_duration_ms=3500,
                min_duration_ms=3500,
                p50_duration_ms=3500,
                p95_duration_ms=3500,
                p99_duration_ms=3500,
                retry_count=1,
                fallback_count=0,
                failure_count=0,
                run_count=1,
            ),
            ProfilingStageBreakdown(
                stage_name="generate_structured_content",
                total_duration_ms=1200,
                average_duration_ms=1200,
                max_duration_ms=1200,
                min_duration_ms=1200,
                p50_duration_ms=1200,
                p95_duration_ms=1200,
                p99_duration_ms=1200,
                retry_count=1,
                fallback_count=1,
                failure_count=0,
                run_count=1,
            ),
        ],
    )
    run_b = run_a.model_copy(
        update={
            "case_id": "slow.b",
            "run_id": "run.slow.b",
            "stage_breakdown": [
                run_a.stage_breakdown[0].model_copy(
                    update={
                        "total_duration_ms": 800,
                        "average_duration_ms": 800,
                        "max_duration_ms": 800,
                        "min_duration_ms": 800,
                        "p50_duration_ms": 800,
                        "p95_duration_ms": 800,
                        "p99_duration_ms": 800,
                    }
                ),
                run_a.stage_breakdown[1].model_copy(
                    update={
                        "total_duration_ms": 2600,
                        "average_duration_ms": 2600,
                        "max_duration_ms": 2600,
                        "min_duration_ms": 2600,
                        "p50_duration_ms": 2600,
                        "p95_duration_ms": 2600,
                        "p99_duration_ms": 2600,
                    }
                ),
            ],
        }
    )
    run_c = run_a.model_copy(
        update={
            "case_id": "slow.c",
            "run_id": "run.slow.c",
            "stage_breakdown": [
                run_a.stage_breakdown[0].model_copy(
                    update={
                        "total_duration_ms": 3900,
                        "average_duration_ms": 3900,
                        "max_duration_ms": 3900,
                        "min_duration_ms": 3900,
                        "p50_duration_ms": 3900,
                        "p95_duration_ms": 3900,
                        "p99_duration_ms": 3900,
                    }
                ),
                run_a.stage_breakdown[1],
            ],
        }
    )

    report = summarize_profile_runs([run_a, run_b, run_c], profile_mode="deterministic")
    flag_types = {flag.flag_type for flag in report.flags}

    assert "stage_latency_exceeded" in flag_types
    assert "unstable_latency_variance" in flag_types
    assert "excessive_retries" in flag_types
    assert "excessive_fallbacks" in flag_types
    assert "compile_time_anomaly" in flag_types
    assert "large_output_artifact" in flag_types
    assert "large_output_total" in flag_types


def test_profiling_compare_and_cli_output(tmp_path: Path, capsys) -> None:
    baseline = ProfilingBatchReport(
        profile_mode="deterministic",
        generated_at=datetime.now(timezone.utc),
        run_count=1,
        successful_run_count=1,
        failed_run_count=0,
        average_total_latency_ms=1000,
        slowest_stage_by_avg="compile_pdf",
        stage_aggregates=[
            ProfilingStageBreakdown(
                stage_name="compile_pdf",
                average_duration_ms=700,
                total_duration_ms=700,
                max_duration_ms=700,
                min_duration_ms=700,
                p50_duration_ms=700,
                p95_duration_ms=700,
                p99_duration_ms=700,
                run_count=1,
            )
        ],
    )
    candidate = baseline.model_copy(
        update={
            "average_total_latency_ms": 1300,
            "stage_aggregates": [
                baseline.stage_aggregates[0].model_copy(
                    update={
                        "average_duration_ms": 950,
                        "total_duration_ms": 950,
                        "max_duration_ms": 950,
                        "min_duration_ms": 950,
                        "p50_duration_ms": 950,
                        "p95_duration_ms": 950,
                        "p99_duration_ms": 950,
                    }
                )
            ],
        }
    )

    comparison = compare_batch_reports(baseline, candidate)
    assert comparison.total_latency_delta_ms == 300
    assert comparison.regressed_stages == ["compile_pdf"]

    left = tmp_path / "baseline.json"
    right = tmp_path / "candidate.json"
    left.write_text(json.dumps(baseline.model_dump(mode="json"), indent=2), encoding="utf-8")
    right.write_text(json.dumps(candidate.model_dump(mode="json"), indent=2), encoding="utf-8")

    exit_code = main(["compare", "--left", str(left), "--right", str(right)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "average_total_latency_delta_ms=300" in output
    assert "regressed_stages=compile_pdf" in output
