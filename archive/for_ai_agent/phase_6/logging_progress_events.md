# Phase 6 Logging and Progress Events

This document describes the structured logging and live progress reporting added for Phase 6 orchestration.

## Files Created

- `backend/app/orchestration/events.py`
- `backend/app/orchestration/event_emitter.py`
- `backend/app/api/routes/progress_stream.py`
- `backend/app/tests/unit/test_progress_events.py`
- `frontend/src/types/pipeline.ts`
- `frontend/src/services/progressStream.ts`
- `frontend/src/hooks/usePipelineProgress.ts`
- `frontend/src/components/resume-generation/ProgressTracker.tsx`

## Files Modified

- `backend/app/orchestration/runner.py`
- `src/resume_optimizer/app.py`

## Event Shape

Every frontend progress event uses this safe shape:

```json
{
  "event_id": "event.<uuid>",
  "run_id": "run.example",
  "event_type": "stage_started",
  "timestamp": "2026-04-07T00:00:00Z",
  "stage_name": "parse_job_description",
  "human_message": "parse job description started.",
  "machine_status": "running",
  "progress_percent": 30,
  "metadata": {
    "attempt_number": 1
  }
}
```

Required event types:

- `run_started`
- `stage_started`
- `stage_progress`
- `stage_completed`
- `stage_failed`
- `retry_scheduled`
- `fallback_applied`
- `run_completed`
- `run_failed`

## Backend Flow

`PipelineRunRecorder` is the single bridge for DB events, logs, and live progress:

1. `create_run(...)` emits `run_started`.
2. `record_stage_event(...)` persists the DB event and emits the matching progress event.
3. `record_retry(...)` persists retry attempts to `retry_attempts`.
4. `record_fallback_decision(...)` records a fallback decision as a stage event.
5. `finalize_run(...)` emits `run_completed` or `run_failed`.

This keeps backend logs, DB stage events, and frontend progress aligned.

## SSE Route

Route:

```text
GET /api/pipeline-runs/{run_id}/events
```

Implementation:

- Uses Server-Sent Events.
- Emits buffered history for the run first.
- Streams future events as they are emitted.
- Sends heartbeat comments while waiting.
- Does not expose raw job descriptions, generated resume content, prompts, provider payloads, secrets, or tokens.

Important integration constraint:

- The current generation route is synchronous.
- For live progress before the response returns, the frontend should create a `pipeline_run_id` and include it in the `POST /api/generate-resume` payload.
- The frontend should open `/api/pipeline-runs/{pipeline_run_id}/events` before or immediately after starting the POST request.

## Frontend Flow

TypeScript contract:

- `frontend/src/types/pipeline.ts`

SSE client:

- `frontend/src/services/progressStream.ts`

React hook:

- `frontend/src/hooks/usePipelineProgress.ts`

Display component:

- `frontend/src/components/resume-generation/ProgressTracker.tsx`

Expected frontend usage:

```tsx
const runId = crypto.randomUUID();
const progress = usePipelineProgress(runId);

fetch("/api/generate-resume", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    pipeline_run_id: runId,
    job_description_text: jobDescription,
    source_profile_id: sourceProfileId
  })
});

return <ProgressTracker progress={progress} />;
```

The hook only updates state from backend events. It does not mark stages complete on timers.

## Progress Mapping

Progress is derived from the canonical stage order:

```text
load_source_profile
normalize_source_data
ingest_job_description
parse_job_description
rank_select_evidence
generate_structured_content
verify_generated_content
render_deterministic_latex
compile_pdf
persist_artifacts
```

Stage started percentage uses the beginning of the stage. Stage completed percentage uses the end of the stage. Failed, blocked, retry, and fallback decision events keep the stage's current percentage instead of pretending forward progress.

## Structured Logs

The event emitter logs every progress event with logger name:

```text
resume_optimizer.orchestration
```

Log extra key:

```text
pipeline_event
```

The log payload matches the safe frontend payload and excludes raw resume/job content.

## Sensitive Data Policy

Progress events must not include:

- Raw job descriptions.
- Source profile contents.
- Generated resume text.
- Prompt text.
- Provider request or response bodies.
- Secret values or tokens.

Allowed metadata:

- `attempt_number`
- `failure_type`
- `retryable`
- `fallback_eligible`
- `policy`
- `fallback_strategy`
- `applied`
- `escalation_note`

Raw failure reasons may be persisted in DB retry/fallback records for diagnostics, but they are not exposed in frontend progress event metadata.

## Fallback Semantics

Fallback decision events distinguish considered fallback from applied fallback:

- `fallback_applied` status is used only if a fallback hook actually ran.
- `skipped` status is used when a fallback was considered but not applied.
- The policy layer does not fabricate success.

## Known Limits

- The in-memory emitter is appropriate for local development and a single API process.
- Multi-process or horizontally scaled deployment needs a shared event bus such as Postgres LISTEN/NOTIFY, Redis pub/sub, or Supabase realtime.
- The repository currently has no pre-existing React frontend, so the TypeScript files were added as a minimal integration surface under the requested `frontend/src/...` paths.
