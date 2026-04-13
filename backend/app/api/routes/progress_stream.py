"""SSE route for Phase 6 pipeline progress events."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.orchestration.event_emitter import (
    DEFAULT_PIPELINE_EVENT_EMITTER,
    format_sse_event,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["pipeline-progress"])


@router.get("/pipeline-runs/{run_id}/events")
def stream_pipeline_progress(run_id: str) -> StreamingResponse:
    """Stream real progress events for a pipeline run via Server-Sent Events."""

    if not run_id or not run_id.startswith("run."):
        raise HTTPException(status_code=404, detail="Run not found")

    def event_stream():
        try:
            for event in DEFAULT_PIPELINE_EVENT_EMITTER.subscribe(run_id):
                if event is None:
                    yield format_sse_event({"status": "waiting"})
                    continue
                try:
                    yield format_sse_event(event)
                except Exception as emit_err:
                    logger.warning(
                        "event_serialization_failed",
                        extra={"run_id": run_id, "error": str(emit_err)},
                    )
                    yield format_sse_event(
                        {"status": "error", "message": "Event serialization failed"}
                    )
        except Exception as sub_err:
            logger.error(
                "subscription_failed", extra={"run_id": run_id, "error": str(sub_err)}
            )
            yield format_sse_event(
                {"status": "error", "message": "Failed to subscribe to events"}
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
