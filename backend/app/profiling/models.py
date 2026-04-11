"""Typed models for profiling runs and bottleneck reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from resume_optimizer.models import StrictModel


class ProfilingBottleneckFlag(StrictModel):
    """One actionable profiling flag."""

    flag_type: str
    severity: str
    subject: str
    message: str
    threshold: float | int | None = None
    observed_value: float | int | None = None


class ProfilingStageBreakdown(StrictModel):
    """Per-stage metrics for one run or batch aggregate."""

    stage_name: str
    total_duration_ms: int = 0
    average_duration_ms: float = 0.0
    max_duration_ms: int = 0
    min_duration_ms: int = 0
    p50_duration_ms: int = 0
    p95_duration_ms: int = 0
    p99_duration_ms: int = 0
    retry_count: int = 0
    fallback_count: int = 0
    failure_count: int = 0
    run_count: int = 0
    latency_variance_ms: float = 0.0


class ProfilingOutputSizeSummary(StrictModel):
    """Compact output size indicators for one run."""

    artifact_count: int = 0
    total_size_bytes: int = 0
    largest_artifact_bytes: int = 0
    artifact_kinds: list[str] = Field(default_factory=list)


class ProfilingRunReport(StrictModel):
    """Developer-facing profiling report for one pipeline run."""

    profile_mode: str
    case_id: str
    scenario: str
    request_id: str | None = None
    run_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    total_latency_ms: int = 0
    slowest_stage: str | None = None
    stage_breakdown: list[ProfilingStageBreakdown] = Field(default_factory=list)
    retry_count: int = 0
    fallback_count: int = 0
    output_sizes: ProfilingOutputSizeSummary = Field(default_factory=ProfilingOutputSizeSummary)
    failure_type: str | None = None
    status: str
    flags: list[ProfilingBottleneckFlag] = Field(default_factory=list)


class ProfilingBatchReport(StrictModel):
    """Aggregate profile report for a batch run."""

    profile_mode: str
    generated_at: datetime
    run_count: int
    successful_run_count: int
    failed_run_count: int
    total_latency_ms: int = 0
    average_total_latency_ms: float = 0.0
    slowest_stage_by_avg: str | None = None
    runs: list[ProfilingRunReport] = Field(default_factory=list)
    stage_aggregates: list[ProfilingStageBreakdown] = Field(default_factory=list)
    failure_distribution: dict[str, int] = Field(default_factory=dict)
    flags: list[ProfilingBottleneckFlag] = Field(default_factory=list)


class ProfilingComparison(StrictModel):
    """Comparison between two profiling batch reports."""

    baseline_label: str
    candidate_label: str
    baseline_run_count: int
    candidate_run_count: int
    total_latency_delta_ms: int = 0
    stage_delta_ms: dict[str, int] = Field(default_factory=dict)
    regressed_stages: list[str] = Field(default_factory=list)
    improved_stages: list[str] = Field(default_factory=list)
