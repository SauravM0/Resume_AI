from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.cache.models import CacheMetricRecord
from backend.app.metrics.models import StageMetricRecord
from backend.app.support import tooling
from backend.app.support.cli import main


def _stage_record(
    *,
    run_id: str,
    request_id: str,
    stage_name: str,
    start_offset_ms: int,
    duration_ms: int,
    success: bool = True,
    failure_type: str | None = None,
    retry_count: int = 0,
    fallback_used: bool = False,
    output_metadata: dict[str, Any] | None = None,
) -> StageMetricRecord:
    base = datetime(2026, 4, 10, tzinfo=UTC)
    started_at = base + timedelta(milliseconds=start_offset_ms)
    ended_at = started_at + timedelta(milliseconds=duration_ms)
    return StageMetricRecord(
        request_id=request_id,
        run_id=run_id,
        stage_name=stage_name,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        success=success,
        failure_type=failure_type,
        retry_count=retry_count,
        fallback_used=fallback_used,
        output_metadata=output_metadata or {},
    )


def test_build_run_summaries_and_detail_redact_sensitive_content() -> None:
    records = [
        _stage_record(
            run_id="run.2",
            request_id="req.2",
            stage_name="parse_job_description",
            start_offset_ms=0,
            duration_ms=80,
            success=True,
            output_metadata={"job_description_text": "Top secret JD", "status": "parsed"},
        ),
        _stage_record(
            run_id="run.2",
            request_id="req.2",
            stage_name="verify_generated_content",
            start_offset_ms=120,
            duration_ms=50,
            success=False,
            failure_type="verification_error",
            retry_count=1,
            fallback_used=True,
            output_metadata={"summary": "Generated secret summary"},
        ),
        _stage_record(
            run_id="run.1",
            request_id="req.1",
            stage_name="render_resume",
            start_offset_ms=0,
            duration_ms=40,
        ),
    ]

    summaries = tooling.build_run_summaries(records, limit=10)

    assert [summary["run_id"] for summary in summaries] == ["run.2", "run.1"]
    assert summaries[0]["status"] == "failed"
    assert summaries[0]["retry_count"] == 1
    assert summaries[0]["fallback_stage_count"] == 1
    assert summaries[0]["failure_categories"] == ["verification_error"]

    detail = tooling.build_run_detail(records, run_id="run.2")
    assert detail is not None
    rendered = json.dumps(detail)
    assert "Top secret JD" not in rendered
    assert "Generated secret summary" not in rendered
    assert detail["stages"][0]["output_metadata"]["job_description_text"]["redacted"] is True
    assert detail["stages"][1]["output_metadata"]["summary"]["redacted"] is True


def test_retry_storms_and_fallback_frequency_are_aggregated() -> None:
    records = [
        _stage_record(
            run_id="run.retry",
            request_id="req.retry",
            stage_name="job_parsing",
            start_offset_ms=0,
            duration_ms=100,
            retry_count=2,
        ),
        _stage_record(
            run_id="run.retry",
            request_id="req.retry",
            stage_name="generation",
            start_offset_ms=150,
            duration_ms=200,
            retry_count=2,
            fallback_used=True,
        ),
        _stage_record(
            run_id="run.ok",
            request_id="req.ok",
            stage_name="generation",
            start_offset_ms=0,
            duration_ms=100,
            fallback_used=True,
        ),
    ]

    retry_summary = tooling.summarize_retry_storms(records, threshold=3)
    assert retry_summary["flagged_run_count"] == 1
    assert retry_summary["flagged_runs"][0]["run_id"] == "run.retry"
    assert retry_summary["flagged_runs"][0]["retry_count"] == 4

    fallback_summary = tooling.summarize_fallback_frequency(records)
    assert fallback_summary["fallbacks"] == 2
    assert fallback_summary["by_stage"]["generation"]["fallbacks"] == 2
    assert fallback_summary["by_stage"]["generation"]["fallback_rate"] == 1.0


def test_cache_health_summary_flags_stale_invalidations() -> None:
    base = datetime(2026, 4, 10, tzinfo=UTC)
    records = [
        CacheMetricRecord(timestamp=base, namespace="jd_parse", event="hit", hit=True, latency_saved_estimate_ms=150),
        CacheMetricRecord(timestamp=base, namespace="jd_parse", event="miss", hit=False),
        CacheMetricRecord(
            timestamp=base,
            namespace="jd_parse",
            event="invalidate",
            stale_invalidation=True,
        ),
    ]

    summary = tooling.summarize_cache_health(records)

    assert summary["status"] == "investigate"
    assert summary["hits"] == 1
    assert summary["misses"] == 1
    assert summary["stale_invalidations"] == 1


def test_safe_temp_workspace_listing_and_purge(tmp_path: Path) -> None:
    safe_old = tmp_path / "resume-render-old"
    safe_new = tmp_path / "resume-render-new"
    unsafe = tmp_path / "other-service-temp"
    safe_old.mkdir()
    safe_new.mkdir()
    unsafe.mkdir()

    now = datetime(2026, 4, 10, tzinfo=UTC)
    old_ts = (now - timedelta(hours=30)).timestamp()
    new_ts = (now - timedelta(hours=2)).timestamp()
    unsafe_ts = (now - timedelta(hours=40)).timestamp()
    for path, ts in ((safe_old, old_ts), (safe_new, new_ts), (unsafe, unsafe_ts)):
        os.utime(path, (ts, ts))

    listed = tooling.list_safe_temp_workspaces(temp_root=tmp_path, older_than_hours=24, now=now)
    assert [item["name"] for item in listed] == ["resume-render-old"]

    purged = tooling.purge_safe_temp_workspaces(temp_root=tmp_path, older_than_hours=24, now=now)
    assert purged["purged_count"] == 1
    assert safe_old.exists() is False
    assert safe_new.exists() is True
    assert unsafe.exists() is True


def test_support_cli_smoke_outputs_sanitized_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    records = [
        _stage_record(
            run_id="run.cli",
            request_id="req.cli",
            stage_name="verification",
            start_offset_ms=0,
            duration_ms=90,
            success=False,
            failure_type="verification_error",
            retry_count=1,
            fallback_used=True,
            output_metadata={"summary": "Sensitive generated summary"},
        )
    ]

    class FakeStageStore:
        def load(self, *, limit: int | None = None) -> list[StageMetricRecord]:
            return records[-limit:] if limit is not None else records

    monkeypatch.setattr("backend.app.support.cli.DEFAULT_STAGE_METRICS_STORE", FakeStageStore())

    assert main(["show-run", "--run-id", "run.cli", "--metrics-limit", "10"]) == 0
    payload = json.loads(capsys.readouterr().out)
    rendered = json.dumps(payload)

    assert payload["run"]["run_id"] == "run.cli"
    assert payload["stages"][0]["failure_type"] == "verification_error"
    assert payload["stages"][0]["output_metadata"]["summary"]["redacted"] is True
    assert "Sensitive generated summary" not in rendered
