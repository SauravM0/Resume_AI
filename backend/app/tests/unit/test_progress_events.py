from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.orchestration.enums import PipelineStatus, StageName, StageStatus
from backend.app.orchestration.event_emitter import PipelineEventEmitter, format_sse_event
from backend.app.orchestration.events import PipelineProgressEventType
from backend.app.orchestration.runner import PipelineRunRecorder


def test_recorder_emits_run_and_stage_progress_events() -> None:
    emitter = PipelineEventEmitter()
    recorder = PipelineRunRecorder(event_emitter=emitter)

    run_id = recorder.create_run(
        run_id="run.progress-events-test",
        requested_template="ats_standard",
        requested_mode="resume_pdf",
        job_description_hash="sha256:progress",
        source_profile_id="profile.progress",
    )
    recorder.record_stage_event(
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
        status=StageStatus.RUNNING,
        attempt_number=1,
        message="parse started",
    )
    recorder.record_stage_event(
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
        status=StageStatus.SUCCEEDED,
        attempt_number=1,
        message="parse completed",
    )
    recorder.finalize_run(status=PipelineStatus.SUCCEEDED, duration_ms=10)

    events = emitter.history(run_id)

    assert [event.event_type for event in events] == [
        PipelineProgressEventType.RUN_STARTED,
        PipelineProgressEventType.STAGE_STARTED,
        PipelineProgressEventType.STAGE_COMPLETED,
        PipelineProgressEventType.RUN_COMPLETED,
    ]
    assert events[1].stage_name == StageName.PARSE_JOB_DESCRIPTION
    assert events[2].progress_percent is not None
    assert events[-1].progress_percent == 100


def test_progress_event_metadata_does_not_expose_raw_reason() -> None:
    emitter = PipelineEventEmitter()
    event = emitter.emit_stage_event(
        run_id="run.progress-safe-metadata-test",
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        status=StageStatus.RETRYING,
        attempt_number=1,
        message="raw provider message that should stay out of the human event",
        machine_payload_json={
            "reason": "raw private failure detail",
            "failure_type": "generation_schema",
            "retryable": True,
        },
    )

    assert event.human_message == "generate structured content retry scheduled."
    assert event.metadata["failure_type"] == "generation_schema"
    assert "reason" not in event.metadata


def test_sse_format_uses_named_event_and_json_payload() -> None:
    emitter = PipelineEventEmitter()
    event = emitter.emit_run_started(run_id="run.sse-format-test")

    payload = format_sse_event(event)

    assert "event: run_started" in payload
    assert "data:" in payload
    assert "run.sse-format-test" in payload
