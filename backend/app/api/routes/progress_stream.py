"""SSE route for Phase 6 pipeline progress events."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.orchestration.event_emitter import (
    DEFAULT_PIPELINE_EVENT_EMITTER,
    format_sse_event,
)

router = APIRouter(prefix="/api", tags=["pipeline-progress"])


@router.get("/pipeline-runs/{run_id}/events")
def stream_pipeline_progress(run_id: str) -> StreamingResponse:
    """Stream real progress events for a pipeline run via Server-Sent Events."""

    def event_stream():
        for event in DEFAULT_PIPELINE_EVENT_EMITTER.subscribe(run_id):
            yield format_sse_event(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
