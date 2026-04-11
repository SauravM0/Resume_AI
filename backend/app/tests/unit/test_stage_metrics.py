from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.metrics.aggregates import summarize_stage_metrics
from backend.app.metrics.models import StageMetricRecord
from backend.app.metrics.storage import JsonlStageMetricsStore, summarize_output_metadata
from backend.app.observability import bind_run_id, reset_trace_context, set_request_id
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.orchestration.stage_executor import StageExecutor


def _recorder() -> PipelineRunRecorder:
    recorder = PipelineRunRecorder(event_emitter=None)
    recorder.create_run(
        run_id="run.metrics.test",
        requested_template="ats_standard",
        requested_mode="resume_pdf",
        job_description_hash="sha256:test",
        source_profile_id="profile.metrics.test",
    )
    return recorder


def test_stage_metric_records_success_timing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = JsonlStageMetricsStore(tmp_path / "stage_metrics.jsonl")
    monkeypatch.setattr("backend.app.metrics.storage.DEFAULT_STAGE_METRICS_STORE", store)
    recorder = _recorder()
    request_token = set_request_id("req.metrics.success")
    run_token = bind_run_id(recorder.run_id)

    try:
        result = StageExecutor(recorder).execute(
            StageName.PARSE_JOB_DESCRIPTION,
            lambda: {"parsed": True},
        )
    finally:
        reset_trace_context(run_token, request_token)

    assert result == {"parsed": True}
    records = store.load()
    assert len(records) == 1
    record = records[0]
    assert record.request_id == "req.metrics.success"
    assert record.run_id == recorder.run_id
    assert record.stage_name == StageName.PARSE_JOB_DESCRIPTION.value
    assert record.success is True
    assert record.duration_ms >= 0
    assert record.retry_count == 0
    assert record.fallback_used is False


def test_stage_metric_records_retries_and_fallbacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = JsonlStageMetricsStore(tmp_path / "stage_metrics.jsonl")
    monkeypatch.setattr("backend.app.metrics.storage.DEFAULT_STAGE_METRICS_STORE", store)
    recorder = _recorder()
    request_token = set_request_id("req.metrics.retry")
    run_token = bind_run_id(recorder.run_id)

    calls = {"count": 0}

    def flaky_operation() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise StageExecutionError(
                "temporary verifier outage",
                failure_type=OrchestrationFailureType.VERIFICATION_RETRYABLE,
                stage_name=StageName.VERIFY_GENERATED_CONTENT,
                retryable=True,
            )
        return "verified"

    try:
        result = StageExecutor(recorder).execute(StageName.VERIFY_GENERATED_CONTENT, flaky_operation)
        with pytest.raises(StageExecutionError):
            StageExecutor(recorder).execute(
                StageName.RANK_SELECT_EVIDENCE,
                lambda: (_ for _ in ()).throw(
                    StageExecutionError(
                        "empty rank result",
                        failure_type=OrchestrationFailureType.RANKING_SELECTION,
                        stage_name=StageName.RANK_SELECT_EVIDENCE,
                    )
                ),
            )
    finally:
        reset_trace_context(run_token, request_token)

    assert result == "verified"
    records = store.load()
    assert len(records) == 2

    retry_record = next(record for record in records if record.stage_name == StageName.VERIFY_GENERATED_CONTENT.value)
    assert retry_record.success is True
    assert retry_record.retry_count == 1
    assert retry_record.fallback_used is False

    fallback_record = next(record for record in records if record.stage_name == StageName.RANK_SELECT_EVIDENCE.value)
    assert fallback_record.success is False
    assert fallback_record.failure_type == OrchestrationFailureType.RANKING_SELECTION.value
    assert fallback_record.fallback_used is True


def test_stage_metric_aggregates_and_redaction() -> None:
    base_time = datetime(2026, 4, 10, tzinfo=timezone.utc)
    records = [
        StageMetricRecord(
            request_id="req.1",
            run_id="run.1",
            stage_name="parse_job_description",
            started_at=base_time,
            ended_at=base_time + timedelta(milliseconds=100),
            duration_ms=100,
            success=True,
        ),
        StageMetricRecord(
            request_id="req.2",
            run_id="run.2",
            stage_name="parse_job_description",
            started_at=base_time,
            ended_at=base_time + timedelta(milliseconds=250),
            duration_ms=250,
            success=False,
            failure_type="job_description_parse",
            retry_count=1,
            fallback_used=True,
        ),
        StageMetricRecord(
            request_id="req.1",
            run_id="run.1",
            stage_name="compile_pdf",
            started_at=base_time + timedelta(milliseconds=300),
            ended_at=base_time + timedelta(milliseconds=700),
            duration_ms=400,
            success=True,
        ),
    ]

    summary = summarize_stage_metrics(records)

    assert summary["record_count"] == 3
    assert summary["request_count"] == 2
    parse_summary = summary["stage_summaries"]["parse_job_description"]
    assert parse_summary["p50_duration_ms"] == 100
    assert parse_summary["p95_duration_ms"] == 250
    assert parse_summary["p99_duration_ms"] == 250
    assert parse_summary["failure_rate"] == 0.5
    assert parse_summary["retry_rate"] == 0.5
    assert parse_summary["fallback_rate"] == 0.5
    assert summary["request_latency_ms"]["p95"] == 700

    redacted = summarize_output_metadata(
        {
            "job_description_text": "secret jd",
            "summary": "secret summary",
            "source_profile_id": "profile.1",
            "selected_items": [1, 2, 3],
        }
    )
    assert redacted["job_description_text"]["redacted"] is True
    assert redacted["job_description_text"]["data_class"] == "raw_job_description"
    assert redacted["summary"]["redacted"] is True
    assert redacted["summary"]["data_class"] == "generated_summary"
    assert redacted["source_profile_id"] == "profile.1"
    assert redacted["selected_items_count"] == 3
