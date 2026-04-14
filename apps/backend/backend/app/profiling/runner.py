"""Execution runner for developer-facing pipeline profiling."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from backend.app.evaluation import (
    EvaluationCaseDefinition,
    EvaluationRunnerConfig,
    JsonEvaluationCaseLoader,
    LocalFileArtifactStore,
    OrchestratedRealPipelineRunner,
)
from backend.app.metrics.models import StageMetricRecord
import backend.app.metrics.storage as metrics_storage
from backend.app.metrics.storage import JsonlStageMetricsStore
from backend.app.observability import bind_run_id, generate_request_id, reset_trace_context, set_request_id
from backend.app.orchestration.artifacts.artifact_manager import ArtifactManager
from backend.app.orchestration.artifacts.storage_backends import LocalArtifactStorageBackend
from backend.app.orchestration.enums import PipelineStatus
from backend.app.orchestration.errors import OrchestrationError
from backend.app.orchestration.orchestrator import ResumeGenerationOrchestrator
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.profiling.models import (
    ProfilingBottleneckFlag,
    ProfilingOutputSizeSummary,
    ProfilingRunReport,
    ProfilingStageBreakdown,
)
from backend.app.profiling.report import (
    COMPILE_TIME_ANOMALY_MS,
    DEFAULT_STAGE_TARGET_LATENCY_MS,
    LARGE_ARTIFACT_BYTES,
    LARGE_TOTAL_OUTPUT_BYTES,
    summarize_profile_runs,
)
from backend.tests.orchestration.pipeline_harness import (
    FakePipelineStageRegistry,
    PipelineCase,
    load_pipeline_cases,
    orchestrator_input,
)

DEFAULT_DETERMINISTIC_CASES_PATH = Path("backend/tests/fixtures/pipeline_cases/regression_cases.json")


class _CapturingRecorderFactory:
    def __init__(self) -> None:
        self.recorders: list[PipelineRunRecorder] = []

    def __call__(self) -> PipelineRunRecorder:
        recorder = PipelineRunRecorder(event_emitter=None)
        self.recorders.append(recorder)
        return recorder


class PipelineProfilingRunner:
    """Profile deterministic or real sample pipeline runs."""

    def __init__(self, *, metrics_store: JsonlStageMetricsStore | None = None) -> None:
        self.metrics_store = metrics_store or JsonlStageMetricsStore(
            Path(tempfile.mkdtemp(prefix="pipeline-profile-metrics-")) / "stage_metrics.jsonl"
        )

    def profile_deterministic_cases(
        self,
        cases: list[PipelineCase],
        *,
        artifact_root: Path | None = None,
        limit: int | None = None,
    ):
        selected = cases[:limit] if limit is not None else cases
        runs = [self._profile_deterministic_case(case, artifact_root=artifact_root) for case in selected]
        return summarize_profile_runs(runs, profile_mode="deterministic")

    def profile_real_cases(
        self,
        cases: list[EvaluationCaseDefinition],
        *,
        output_root: Path | None = None,
        use_live_llm: bool = False,
        enable_render: bool = False,
        stop_after: str = "full",
        limit: int | None = None,
    ):
        selected = cases[:limit] if limit is not None else cases
        runs = [
            self._profile_real_case(
                case,
                output_root=output_root,
                use_live_llm=use_live_llm,
                enable_render=enable_render,
                stop_after=stop_after,
            )
            for case in selected
        ]
        return summarize_profile_runs(runs, profile_mode="real" if use_live_llm else "real_dry_run")

    def _profile_deterministic_case(
        self,
        case: PipelineCase,
        *,
        artifact_root: Path | None,
    ) -> ProfilingRunReport:
        recorder_factory = _CapturingRecorderFactory()
        artifact_dir = artifact_root or Path(tempfile.mkdtemp(prefix="pipeline-profile-artifacts-"))
        orchestrator = ResumeGenerationOrchestrator(
            recorder_factory=recorder_factory,
            stage_registry=FakePipelineStageRegistry(case),
            artifact_manager=ArtifactManager(LocalArtifactStorageBackend(artifact_dir)),
        )
        run_id = f"run.profile.{case.case_id}"
        request_id = generate_request_id()
        request_token = set_request_id(request_id)
        run_token = bind_run_id(run_id)
        previous_store = metrics_storage.DEFAULT_STAGE_METRICS_STORE
        metrics_storage.DEFAULT_STAGE_METRICS_STORE = self.metrics_store
        started_at = datetime.now(timezone.utc)
        try:
            status = PipelineStatus.FAILED.value
            failure_type = None
            try:
                response = orchestrator.run(
                    orchestrator_input(run_id=run_id, job_description_text=case.job_description_text)
                )
                status = response.status.value
            except OrchestrationError as exc:
                failure_type = exc.failure_type.value
                status = PipelineStatus.BLOCKED.value if exc.http_status_code == 409 else PipelineStatus.FAILED.value
        finally:
            ended_at = datetime.now(timezone.utc)
            metrics_storage.DEFAULT_STAGE_METRICS_STORE = previous_store
            reset_trace_context(run_token, request_token)
        recorder = recorder_factory.recorders[-1]
        records = self._records_for_run(run_id=run_id)
        return self._build_run_report(
            profile_mode="deterministic",
            case_id=case.case_id,
            scenario=case.scenario_type,
            request_id=request_id,
            run_id=run_id,
            status=status,
            failure_type=failure_type,
            records=records,
            artifact_paths=[artifact.uri for artifact in recorder.artifacts if artifact.uri],
            artifact_kinds=[artifact.kind.value for artifact in recorder.artifacts],
            started_at=started_at,
            ended_at=ended_at,
        )

    def _profile_real_case(
        self,
        case: EvaluationCaseDefinition,
        *,
        output_root: Path | None,
        use_live_llm: bool,
        enable_render: bool,
        stop_after: str,
    ) -> ProfilingRunReport:
        request_id = generate_request_id()
        request_token = set_request_id(request_id)
        previous_store = metrics_storage.DEFAULT_STAGE_METRICS_STORE
        metrics_storage.DEFAULT_STAGE_METRICS_STORE = self.metrics_store
        started_at = datetime.now(timezone.utc)
        try:
            runner = OrchestratedRealPipelineRunner()
            artifact_store = LocalFileArtifactStore(output_root or Path(tempfile.mkdtemp(prefix="real-profile-output-")))
            result = runner.run_case_with_details(
                case,
                artifact_store=artifact_store,
                config=EvaluationRunnerConfig(
                    use_live_llm=use_live_llm,
                    enable_render=enable_render,
                    persist_artifacts=True,
                    fail_fast=True,
                    stop_after=stop_after,
                ),
            )
        finally:
            ended_at = datetime.now(timezone.utc)
            metrics_storage.DEFAULT_STAGE_METRICS_STORE = previous_store
            reset_trace_context(None, request_token)
        run_id = result.run_manifest.run_id
        records = self._records_for_run(run_id=run_id)
        return self._build_run_report(
            profile_mode="real" if use_live_llm else "real_dry_run",
            case_id=case.metadata.case_id,
            scenario=case.metadata.scenario,
            request_id=request_id,
            run_id=run_id,
            status=result.actual_outputs.pipeline_status.value,
            failure_type=(None if result.actual_outputs.pipeline_status not in {PipelineStatus.FAILED, PipelineStatus.BLOCKED} else result.run_manifest.final_message),
            records=records,
            artifact_paths=[entry.storage_path for entry in result.artifact_manifest.entries],
            artifact_kinds=[entry.artifact_kind.value for entry in result.artifact_manifest.entries],
            started_at=started_at,
            ended_at=ended_at,
        )

    def _records_for_run(self, *, run_id: str) -> list[StageMetricRecord]:
        return [record for record in self.metrics_store.load() if record.run_id == run_id]

    def _build_run_report(
        self,
        *,
        profile_mode: str,
        case_id: str,
        scenario: str,
        request_id: str | None,
        run_id: str,
        status: str,
        failure_type: str | None,
        records: list[StageMetricRecord],
        artifact_paths: list[str | None],
        artifact_kinds: list[str],
        started_at: datetime,
        ended_at: datetime,
    ) -> ProfilingRunReport:
        stage_groups: dict[str, list[StageMetricRecord]] = defaultdict(list)
        for record in records:
            stage_groups[record.stage_name].append(record)
        stage_breakdown = [_build_stage_breakdown(stage_name, items) for stage_name, items in sorted(stage_groups.items())]
        stage_breakdown.sort(key=lambda item: item.total_duration_ms, reverse=True)
        slowest_stage = stage_breakdown[0].stage_name if stage_breakdown else None
        output_sizes = _output_size_summary(artifact_paths=artifact_paths, artifact_kinds=artifact_kinds)
        report = ProfilingRunReport(
            profile_mode=profile_mode,
            case_id=case_id,
            scenario=scenario,
            request_id=request_id,
            run_id=run_id,
            started_at=started_at,
            ended_at=ended_at,
            total_latency_ms=sum(record.duration_ms for record in records),
            slowest_stage=slowest_stage,
            stage_breakdown=stage_breakdown,
            retry_count=sum(record.retry_count for record in records),
            fallback_count=sum(1 for record in records if record.fallback_used),
            output_sizes=output_sizes,
            failure_type=failure_type,
            status=status,
            flags=[],
        )
        report.flags = _run_flags(report)
        return report


def load_deterministic_cases(path: Path = DEFAULT_DETERMINISTIC_CASES_PATH) -> list[PipelineCase]:
    """Load deterministic pipeline profiling cases."""

    return load_pipeline_cases(path)


def load_real_cases(
    *,
    case_file: Path | None = None,
    pack: str = "end_to_end",
) -> list[EvaluationCaseDefinition]:
    """Load real evaluation cases for profiling."""

    loader = JsonEvaluationCaseLoader()
    if case_file is not None:
        return [loader.load_case(case_file)]
    from backend.app.evaluation.enums import EvaluationPackType

    return loader.load_pack(EvaluationPackType(pack))


def _build_stage_breakdown(stage_name: str, records: list[StageMetricRecord]) -> ProfilingStageBreakdown:
    durations = [record.duration_ms for record in records]
    return ProfilingStageBreakdown(
        stage_name=stage_name,
        total_duration_ms=sum(durations),
        average_duration_ms=sum(durations) / len(durations) if durations else 0.0,
        max_duration_ms=max(durations, default=0),
        min_duration_ms=min(durations, default=0),
        p50_duration_ms=_percentile(durations, 50),
        p95_duration_ms=_percentile(durations, 95),
        p99_duration_ms=_percentile(durations, 99),
        retry_count=sum(record.retry_count for record in records),
        fallback_count=sum(1 for record in records if record.fallback_used),
        failure_count=sum(1 for record in records if not record.success),
        run_count=len(records),
        latency_variance_ms=_variance(durations),
    )


def _run_flags(run: ProfilingRunReport) -> list[ProfilingBottleneckFlag]:
    flags: list[ProfilingBottleneckFlag] = []
    for stage in run.stage_breakdown:
        target = DEFAULT_STAGE_TARGET_LATENCY_MS.get(stage.stage_name)
        if target is not None and stage.total_duration_ms > target:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="stage_latency_exceeded",
                    severity="warning",
                    subject=stage.stage_name,
                    message=f"{stage.stage_name} exceeded its target latency for this run.",
                    threshold=target,
                    observed_value=stage.total_duration_ms,
                )
            )
        if stage.stage_name == "compile_pdf" and stage.total_duration_ms > COMPILE_TIME_ANOMALY_MS:
            flags.append(
                ProfilingBottleneckFlag(
                    flag_type="compile_time_anomaly",
                    severity="warning",
                    subject=stage.stage_name,
                    message="compile_pdf duration exceeded the anomaly threshold.",
                    threshold=COMPILE_TIME_ANOMALY_MS,
                    observed_value=stage.total_duration_ms,
                )
            )
    if run.retry_count > 1:
        flags.append(
            ProfilingBottleneckFlag(
                flag_type="excessive_retries",
                severity="warning",
                subject=run.case_id,
                message="Run retried more than once.",
                threshold=1,
                observed_value=run.retry_count,
            )
        )
    if run.fallback_count > 0:
        flags.append(
            ProfilingBottleneckFlag(
                flag_type="fallback_used",
                severity="warning",
                subject=run.case_id,
                message="Run required a fallback decision or fallback path.",
                threshold=0,
                observed_value=run.fallback_count,
            )
        )
    if run.output_sizes.largest_artifact_bytes > LARGE_ARTIFACT_BYTES:
        flags.append(
            ProfilingBottleneckFlag(
                flag_type="large_output_artifact",
                severity="warning",
                subject=run.case_id,
                message="Largest artifact exceeded output size threshold.",
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
                message="Total output size exceeded threshold.",
                threshold=LARGE_TOTAL_OUTPUT_BYTES,
                observed_value=run.output_sizes.total_size_bytes,
            )
        )
    return flags


def _output_size_summary(*, artifact_paths: list[str | None], artifact_kinds: list[str]) -> ProfilingOutputSizeSummary:
    sizes = []
    for artifact_path in artifact_paths:
        if artifact_path is None:
            continue
        path = Path(artifact_path)
        if path.exists() and path.is_file():
            sizes.append(path.stat().st_size)
    return ProfilingOutputSizeSummary(
        artifact_count=len([path for path in artifact_paths if path is not None]),
        total_size_bytes=sum(sizes),
        largest_artifact_bytes=max(sizes, default=0),
        artifact_kinds=sorted(set(artifact_kinds)),
    )


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, ((len(ordered) * percentile + 99) // 100) - 1)
    return ordered[index]


def _variance(values: list[int]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = sum(values) / len(values)
    return sum((value - avg) ** 2 for value in values) / len(values)
