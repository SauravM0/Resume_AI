"""Profiling report generation and bottleneck flagging."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import ceil
from statistics import mean, pvariance

from backend.app.profiling.models import (
    ProfilingBatchReport,
    ProfilingBottleneckFlag,
    ProfilingComparison,
    ProfilingRunReport,
    ProfilingStageBreakdown,
)

DEFAULT_STAGE_TARGET_LATENCY_MS: dict[str, int] = {
    "request_validation": 50,
    "load_source_profile": 100,
    "normalize_source_data": 100,
    "ingest_job_description": 50,
    "parse_job_description": 1500,
    "rank_select_evidence": 500,
    "section_planning": 250,
    "generate_structured_content": 2000,
    "verify_generated_content": 1200,
    "render_deterministic_latex": 600,
    "compile_pdf": 1200,
    "persist_artifacts": 250,
    "response_packaging": 100,
}
LATENCY_VARIANCE_CV_THRESHOLD = 0.5
EXCESSIVE_RETRY_RATE_THRESHOLD = 0.2
EXCESSIVE_FALLBACK_RATE_THRESHOLD = 0.1
COMPILE_TIME_ANOMALY_MS = 3000
LARGE_ARTIFACT_BYTES = 500_000
LARGE_TOTAL_OUTPUT_BYTES = 1_500_000
COMPARE_REGRESSION_THRESHOLD_MS = 100


def summarize_profile_runs(
    runs: list[ProfilingRunReport],
    *,
    profile_mode: str,
) -> ProfilingBatchReport:
    """Build a batch profiling report from per-run reports."""

    stage_groups: dict[str, list[ProfilingStageBreakdown]] = defaultdict(list)
    failure_distribution = Counter(run.failure_type or "none" for run in runs if run.failure_type is not None)
    for run in runs:
        for stage in run.stage_breakdown:
            stage_groups[stage.stage_name].append(stage)

    stage_aggregates = [
        _aggregate_stage(stage_name, items)
        for stage_name, items in sorted(stage_groups.items())
    ]
    stage_aggregates.sort(key=lambda item: item.average_duration_ms, reverse=True)
    flags = _batch_flags(stage_aggregates, runs)

    return ProfilingBatchReport(
        profile_mode=profile_mode,
        generated_at=datetime.now(timezone.utc),
        run_count=len(runs),
        successful_run_count=sum(1 for run in runs if run.failure_type is None and run.status not in {"failed", "blocked"}),
        failed_run_count=sum(1 for run in runs if run.failure_type is not None or run.status in {"failed", "blocked"}),
        total_latency_ms=sum(run.total_latency_ms for run in runs),
        average_total_latency_ms=mean([run.total_latency_ms for run in runs]) if runs else 0.0,
        slowest_stage_by_avg=stage_aggregates[0].stage_name if stage_aggregates else None,
        runs=runs,
        stage_aggregates=stage_aggregates,
        failure_distribution=dict(sorted(failure_distribution.items())),
        flags=flags,
    )


def compare_batch_reports(
    baseline: ProfilingBatchReport,
    candidate: ProfilingBatchReport,
    *,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
) -> ProfilingComparison:
    """Compare two saved profiling reports."""

    baseline_map = {item.stage_name: item for item in baseline.stage_aggregates}
    candidate_map = {item.stage_name: item for item in candidate.stage_aggregates}
    stage_names = sorted(set(baseline_map) | set(candidate_map))
    deltas: dict[str, int] = {}
    regressed: list[str] = []
    improved: list[str] = []
    for stage_name in stage_names:
        baseline_avg = int(round(baseline_map.get(stage_name, ProfilingStageBreakdown(stage_name=stage_name)).average_duration_ms))
        candidate_avg = int(round(candidate_map.get(stage_name, ProfilingStageBreakdown(stage_name=stage_name)).average_duration_ms))
        delta = candidate_avg - baseline_avg
        deltas[stage_name] = delta
        if delta >= COMPARE_REGRESSION_THRESHOLD_MS:
            regressed.append(stage_name)
        if delta <= -COMPARE_REGRESSION_THRESHOLD_MS:
            improved.append(stage_name)
    return ProfilingComparison(
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        baseline_run_count=baseline.run_count,
        candidate_run_count=candidate.run_count,
        total_latency_delta_ms=int(round(candidate.average_total_latency_ms - baseline.average_total_latency_ms)),
        stage_delta_ms=deltas,
        regressed_stages=regressed,
        improved_stages=improved,
    )


def render_batch_summary(report: ProfilingBatchReport) -> str:
    """Render a concise human-readable batch profiling summary."""

    lines = [
        f"profile_mode={report.profile_mode}",
        f"run_count={report.run_count}",
        f"average_total_latency_ms={int(round(report.average_total_latency_ms))}",
        f"slowest_stage_by_avg={report.slowest_stage_by_avg or 'n/a'}",
        "stage_latency_summary:",
    ]
    for stage in report.stage_aggregates:
        lines.append(
            f"- {stage.stage_name}: avg={int(round(stage.average_duration_ms))} p95={stage.p95_duration_ms} retries={stage.retry_count} fallbacks={stage.fallback_count} failures={stage.failure_count}"
        )
    if report.flags:
        lines.append("flags:")
        for flag in report.flags:
            lines.append(f"- {flag.severity}:{flag.flag_type}:{flag.subject} {flag.message}")
    return "\n".join(lines)


def render_comparison_summary(comparison: ProfilingComparison) -> str:
    """Render a concise comparison between two batch profiling reports."""

    lines = [
        f"baseline={comparison.baseline_label} runs={comparison.baseline_run_count}",
        f"candidate={comparison.candidate_label} runs={comparison.candidate_run_count}",
        f"average_total_latency_delta_ms={comparison.total_latency_delta_ms}",
    ]
    if comparison.regressed_stages:
        lines.append("regressed_stages=" + ",".join(comparison.regressed_stages))
    if comparison.improved_stages:
        lines.append("improved_stages=" + ",".join(comparison.improved_stages))
    return "\n".join(lines)


def _aggregate_stage(stage_name: str, items: list[ProfilingStageBreakdown]) -> ProfilingStageBreakdown:
    avg_values = [int(round(item.average_duration_ms)) for item in items]
    retry_count = sum(item.retry_count for item in items)
    fallback_count = sum(item.fallback_count for item in items)
    failure_count = sum(item.failure_count for item in items)
    return ProfilingStageBreakdown(
        stage_name=stage_name,
        total_duration_ms=sum(item.total_duration_ms for item in items),
        average_duration_ms=mean(avg_values) if avg_values else 0.0,
        max_duration_ms=max((item.max_duration_ms for item in items), default=0),
        min_duration_ms=min((item.min_duration_ms for item in items), default=0),
        p50_duration_ms=_percentile(avg_values, 50),
        p95_duration_ms=_percentile(avg_values, 95),
        p99_duration_ms=_percentile(avg_values, 99),
        retry_count=retry_count,
        fallback_count=fallback_count,
        failure_count=failure_count,
        run_count=len(items),
        latency_variance_ms=pvariance(avg_values) if len(avg_values) > 1 else 0.0,
    )


def _batch_flags(
    stage_aggregates: list[ProfilingStageBreakdown],
    runs: list[ProfilingRunReport],
) -> list[ProfilingBottleneckFlag]:
    flags: list[ProfilingBottleneckFlag] = []
    run_count = len(runs) or 1
    for stage in stage_aggregates:
        target = DEFAULT_STAGE_TARGET_LATENCY_MS.get(stage.stage_name)
        if target is not None and stage.p95_duration_ms > target:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="stage_latency_exceeded",
                    severity="warning",
                    subject=stage.stage_name,
                    message=f"{stage.stage_name} p95 latency exceeds target.",
                    threshold=target,
                    observed_value=stage.p95_duration_ms,
                )
            )
        cv = _coefficient_of_variation(stage.average_duration_ms, stage.latency_variance_ms)
        if stage.run_count >= 3 and cv > LATENCY_VARIANCE_CV_THRESHOLD:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="unstable_latency_variance",
                    severity="warning",
                    subject=stage.stage_name,
                    message=f"{stage.stage_name} latency variance is unstable across runs.",
                    threshold=LATENCY_VARIANCE_CV_THRESHOLD,
                    observed_value=round(cv, 3),
                )
            )
        retry_rate = stage.retry_count / run_count
        if retry_rate > EXCESSIVE_RETRY_RATE_THRESHOLD:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="excessive_retries",
                    severity="warning",
                    subject=stage.stage_name,
                    message=f"{stage.stage_name} retry rate is above threshold.",
                    threshold=EXCESSIVE_RETRY_RATE_THRESHOLD,
                    observed_value=round(retry_rate, 3),
                )
            )
        fallback_rate = stage.fallback_count / run_count
        if fallback_rate > EXCESSIVE_FALLBACK_RATE_THRESHOLD:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="excessive_fallbacks",
                    severity="warning",
                    subject=stage.stage_name,
                    message=f"{stage.stage_name} fallback rate is above threshold.",
                    threshold=EXCESSIVE_FALLBACK_RATE_THRESHOLD,
                    observed_value=round(fallback_rate, 3),
                )
            )
        if stage.stage_name == "compile_pdf" and stage.max_duration_ms > COMPILE_TIME_ANOMALY_MS:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="compile_time_anomaly",
                    severity="warning",
                    subject=stage.stage_name,
                    message="compile_pdf exceeded the compile time anomaly threshold.",
                    threshold=COMPILE_TIME_ANOMALY_MS,
                    observed_value=stage.max_duration_ms,
                )
            )
    for run in runs:
        if run.output_sizes.largest_artifact_bytes > LARGE_ARTIFACT_BYTES:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="large_output_artifact",
                    severity="warning",
                    subject=run.case_id,
                    message="Largest output artifact exceeds threshold.",
                    threshold=LARGE_ARTIFACT_BYTES,
                    observed_value=run.output_sizes.largest_artifact_bytes,
                )
            )
        if run.output_sizes.total_size_bytes > LARGE_TOTAL_OUTPUT_BYTES:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="large_output_total",
                    severity="warning",
                    subject=run.case_id,
                    message="Total output artifact size exceeds threshold.",
                    threshold=LARGE_TOTAL_OUTPUT_BYTES,
                    observed_value=run.output_sizes.total_size_bytes,
                )
            )
    return flags


def _coefficient_of_variation(avg: float, variance: float) -> float:
    if avg <= 0:
        return 0.0
    return (variance ** 0.5) / avg


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, ceil((percentile / 100) * len(ordered)) - 1)
    return ordered[index]
