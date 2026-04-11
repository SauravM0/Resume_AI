# Phase 6 Frontend Integration

This document describes the React and TypeScript frontend integration for the Phase 6 orchestration pipeline.

## Files Created

- `frontend/src/services/generateResume.ts`
- `frontend/src/hooks/useResumeGeneration.ts`
- `frontend/src/components/resume-generation/JobDescriptionForm.tsx`
- `frontend/src/components/resume-generation/GenerationFailure.tsx`
- `frontend/src/components/resume-generation/GenerationResult.tsx`
- `frontend/src/components/resume-generation/ResumeGenerationPanel.tsx`
- `frontend/src/components/resume-generation/index.ts`
- `frontend/src/pages/ResumeGenerationPage.tsx`

## Files Updated

- `frontend/src/types/pipeline.ts`
- `frontend/src/services/progressStream.ts`
- `frontend/src/hooks/usePipelineProgress.ts`
- `frontend/src/components/resume-generation/ProgressTracker.tsx`

## Component Tree

Minimal Phase 6 tree:

```text
ResumeGenerationPage
ResumeGenerationPanel
JobDescriptionForm
ProgressTracker
GenerationFailure
GenerationResult
```

Responsibilities:

- `JobDescriptionForm`: collects job description and optional posting URL.
- `ResumeGenerationPanel`: coordinates form submit, progress display, failure display, and result display.
- `ProgressTracker`: renders current stage, completed stage history, retry notices, fallback notices, and latest backend progress message.
- `GenerationFailure`: renders backend error message, failed stage, failure type, retryability, fallback eligibility, and run ID.
- `GenerationResult`: renders final status, warnings, available outputs, and final PDF/output reference.

## State Shape Changes

The frontend now tracks:

```ts
interface ResumeGenerationState {
  run_id?: string;
  overall_status: PipelineOverallStatus;
  submitting: boolean;
  response?: GenerateResumeResponse;
  error?: ResumeGenerationError;
  warnings: string[];
  final_outputs: AvailableOutput[];
  progress: PipelineProgressState;
}
```

Progress state tracks:

```ts
interface PipelineProgressState {
  run_id: string;
  events: PipelineProgressEvent[];
  stages: PipelineStageProgress[];
  latest_event?: PipelineProgressEvent;
  progress_percent: number;
  connected: boolean;
  terminal: boolean;
  current_stage?: PipelineStageProgress;
  completed_stages: PipelineStageProgress[];
  retry_notices: PipelineProgressEvent[];
  fallback_notices: PipelineProgressEvent[];
  error?: string;
}
```

## Event Handling Flow

1. User submits a job description.
2. `useResumeGeneration.submit(...)` creates a `run_id` before sending the request.
3. `usePipelineProgress(run_id)` opens the SSE stream at `/api/pipeline-runs/{run_id}/events`.
4. `generateResume(...)` sends `POST /api/generate-resume` with the same `pipeline_run_id`.
5. SSE events update stage progress as the backend emits real stage events.
6. The final POST response fills `warnings`, `available_outputs`, and final output metadata.
7. Errors are normalized and shown through `GenerationFailure`.

The UI does not mark a stage complete without a backend event.

## Backend Event Types To UI State

| Backend event type | UI behavior |
|---|---|
| `run_started` | Shows running status and run ID. |
| `stage_started` | Updates current stage. |
| `stage_progress` | Updates latest message without completing the stage. |
| `stage_completed` | Adds or updates the stage as completed. |
| `stage_failed` | Shows failed stage and failure metadata. |
| `retry_scheduled` | Adds retry notice and shows retrying stage status. |
| `fallback_applied` | Adds fallback notice and shows fallback status. |
| `run_completed` | Marks progress terminal; final response supplies output metadata. |
| `run_failed` | Marks progress terminal and keeps failure state visible. |

## Success State

`GenerationResult` displays:

- final status
- run ID
- warnings from backend
- final PDF link when available
- all available output references

## Failure State

`GenerationFailure` displays:

- backend error message
- failed stage
- failure type
- retryable flag
- fallback eligible flag
- run ID

The failure reason is not hidden, but the UI does not expose raw prompts or sensitive payloads.

## Current Integration Limit

This repository did not contain an existing frontend package setup, `package.json`, `tsconfig.json`, or app router. The frontend files were added under the requested `frontend/src/...` paths as a clean integration surface. A future frontend package should import `ResumeGenerationPage` or `ResumeGenerationPanel` into its actual router.
