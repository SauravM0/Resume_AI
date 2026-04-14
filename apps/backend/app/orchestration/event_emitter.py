"""In-memory event emitter for Phase 6 progress streaming and logs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
import json
import logging
from queue import Empty, Queue
from threading import Lock
from typing import Any

from backend.app.orchestration.enums import PipelineStatus, StageName, StageStatus
from backend.app.orchestration.events import (
    PipelineProgressEvent,
    PipelineProgressEventType,
)

LOGGER = logging.getLogger("resume_optimizer.orchestration")
MAX_HISTORY_EVENTS_PER_RUN = 250

PIPELINE_STAGE_ORDER: tuple[StageName, ...] = (
    StageName.LOAD_SOURCE_PROFILE,
    StageName.NORMALIZE_SOURCE_DATA,
    StageName.INGEST_JOB_DESCRIPTION,
    StageName.PARSE_JOB_DESCRIPTION,
    StageName.RANK_SELECT_EVIDENCE,
    StageName.GENERATE_STRUCTURED_CONTENT,
    StageName.VERIFY_GENERATED_CONTENT,
    StageName.RENDER_DETERMINISTIC_LATEX,
    StageName.COMPILE_PDF,
    StageName.PERSIST_ARTIFACTS,
)


class PipelineEventEmitter:
    """Emit structured run events to logs and in-memory SSE subscribers."""

    def __init__(self) -> None:
        self._history: dict[str, list[PipelineProgressEvent]] = defaultdict(list)
        self._subscribers: dict[str, list[Queue[PipelineProgressEvent]]] = defaultdict(
            list
        )
        self._lock = Lock()

    def emit(self, event: PipelineProgressEvent) -> PipelineProgressEvent:
        """Persist event in memory, publish to subscribers, and write structured logs."""

        with self._lock:
            history = self._history[event.run_id]
            history.append(event)
            if len(history) > MAX_HISTORY_EVENTS_PER_RUN:
                del history[: len(history) - MAX_HISTORY_EVENTS_PER_RUN]
            subscribers = list(self._subscribers.get(event.run_id, []))
        for subscriber in subscribers:
            subscriber.put(event)
        LOGGER.info(
            "pipeline_progress_event", extra={"pipeline_event": event.to_log_payload()}
        )
        return event

    def emit_run_started(self, *, run_id: str) -> PipelineProgressEvent:
        """Emit a run-started progress event."""

        return self.emit(
            PipelineProgressEvent(
                run_id=run_id,
                event_type=PipelineProgressEventType.RUN_STARTED,
                human_message="Resume generation started.",
                machine_status=PipelineStatus.RUNNING.value,
                progress_percent=0,
            )
        )

    def emit_run_finished(
        self,
        *,
        run_id: str,
        status: PipelineStatus,
        final_error_code: str | None = None,
    ) -> PipelineProgressEvent:
        """Emit a terminal run event."""

        failed = status in {PipelineStatus.FAILED, PipelineStatus.BLOCKED}
        return self.emit(
            PipelineProgressEvent(
                run_id=run_id,
                event_type=PipelineProgressEventType.RUN_FAILED
                if failed
                else PipelineProgressEventType.RUN_COMPLETED,
                human_message="Resume generation failed."
                if failed
                else "Resume generation completed.",
                machine_status=status.value,
                progress_percent=100 if not failed else None,
                metadata=_compact_metadata({"final_error_code": final_error_code}),
            )
        )

    def emit_stage_event(
        self,
        *,
        run_id: str,
        stage_name: StageName,
        status: StageStatus,
        attempt_number: int,
        message: str,
        machine_payload_json: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        duration_ms: int | None = None,
    ) -> PipelineProgressEvent:
        """Emit a frontend-safe event corresponding to a persisted stage event."""

        event_type = _event_type_for_status(status)
        return self.emit(
            PipelineProgressEvent(
                run_id=run_id,
                event_type=event_type,
                stage_name=stage_name,
                human_message=_human_message(stage_name, status, message),
                machine_status=status.value,
                progress_percent=_progress_percent(stage_name, status),
                metadata=_safe_stage_metadata(
                    stage_name=stage_name,
                    status=status,
                    attempt_number=attempt_number,
                    machine_payload_json=machine_payload_json or {},
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                ),
            )
        )

    def history(self, run_id: str) -> list[PipelineProgressEvent]:
        """Return buffered events for a run."""

        with self._lock:
            return list(self._history.get(run_id, []))

    def subscribe(self, run_id: str) -> Iterator[PipelineProgressEvent | None]:
        """Yield historical and future events. `None` is a heartbeat."""

        queue: Queue[PipelineProgressEvent] = Queue()
        with self._lock:
            history = list(self._history.get(run_id, []))
            self._subscribers[run_id].append(queue)
        try:
            for event in history:
                yield event
            while True:
                try:
                    yield queue.get(timeout=15)
                except Empty:
                    yield None
        finally:
            with self._lock:
                subscribers = self._subscribers.get(run_id, [])
                if queue in subscribers:
                    subscribers.remove(queue)
                if not subscribers:
                    self._subscribers.pop(run_id, None)


def format_sse_event(event: PipelineProgressEvent | dict | None) -> str:
    """Format a progress event, dict, or heartbeat as Server-Sent Events text."""

    if event is None:
        return ": heartbeat\n\n"
    if isinstance(event, dict):
        payload = json.dumps(event, separators=(",", ":"))
        return f"data: {payload}\n\n"
    try:
        payload = json.dumps(
            event.model_dump(mode="json", exclude_none=True), separators=(",", ":")
        )
        return f"id: {event.event_id}\nevent: {event.event_type.value}\ndata: {payload}\n\n"
    except Exception:
        return f"data: {json.dumps({'status': 'error', 'message': 'Event serialization failed'})}\n\n"


def _event_type_for_status(status: StageStatus) -> PipelineProgressEventType:
    if status == StageStatus.RUNNING:
        return PipelineProgressEventType.STAGE_STARTED
    if status == StageStatus.SUCCEEDED:
        return PipelineProgressEventType.STAGE_COMPLETED
    if status == StageStatus.RETRYING:
        return PipelineProgressEventType.RETRY_SCHEDULED
    if status == StageStatus.FALLBACK_APPLIED:
        return PipelineProgressEventType.FALLBACK_APPLIED
    if status in {StageStatus.FAILED, StageStatus.BLOCKED}:
        return PipelineProgressEventType.STAGE_FAILED
    return PipelineProgressEventType.STAGE_PROGRESS


def _progress_percent(stage_name: StageName, status: StageStatus) -> int | None:
    if stage_name not in PIPELINE_STAGE_ORDER:
        return None
    index = PIPELINE_STAGE_ORDER.index(stage_name)
    if status == StageStatus.RUNNING:
        return int(index / len(PIPELINE_STAGE_ORDER) * 100)
    if status == StageStatus.SUCCEEDED:
        return int((index + 1) / len(PIPELINE_STAGE_ORDER) * 100)
    return int(index / len(PIPELINE_STAGE_ORDER) * 100)


def _human_message(stage_name: StageName, status: StageStatus, message: str) -> str:
    if status == StageStatus.RUNNING:
        return f"{_stage_label(stage_name)} started."
    if status == StageStatus.SUCCEEDED:
        return f"{_stage_label(stage_name)} completed."
    if status == StageStatus.RETRYING:
        return f"{_stage_label(stage_name)} retry scheduled."
    if status == StageStatus.FALLBACK_APPLIED:
        return f"{_stage_label(stage_name)} fallback applied."
    if status in {StageStatus.FAILED, StageStatus.BLOCKED}:
        return f"{_stage_label(stage_name)} failed."
    return message[:160] if message else f"{_stage_label(stage_name)} updated."


def _stage_label(stage_name: StageName) -> str:
    return stage_name.value.replace("_", " ")


def _safe_stage_metadata(
    *,
    stage_name: StageName,
    status: StageStatus,
    attempt_number: int,
    machine_payload_json: dict[str, Any],
    started_at: datetime | None,
    ended_at: datetime | None,
    duration_ms: int | None,
) -> dict[str, Any]:
    allowed_keys = {
        "failure_type",
        "failure_category",
        "retryable",
        "fallback_eligible",
        "policy",
        "fallback_strategy",
        "applied",
        "escalation_note",
        "decision_outcome",
        "decision_confidence",
        "renderable",
        "repair_count",
        "verification_run_id",
    }
    metadata = {
        key: value for key, value in machine_payload_json.items() if key in allowed_keys
    }
    metadata["phase_id"] = stage_name.value
    metadata["phase_label"] = _stage_label(stage_name)
    metadata["status"] = status.value
    metadata["attempt_number"] = attempt_number
    if started_at is not None:
        metadata["started_at"] = started_at.isoformat()
    if ended_at is not None:
        metadata["ended_at"] = ended_at.isoformat()
    if duration_ms is not None:
        metadata["duration_ms"] = duration_ms
    return metadata


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value is not None}


DEFAULT_PIPELINE_EVENT_EMITTER = PipelineEventEmitter()
