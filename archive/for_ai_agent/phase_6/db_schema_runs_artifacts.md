# Phase 6 Run And Artifact Database Schema

This document explains the Phase 6 orchestration persistence schema for PostgreSQL and Supabase-hosted PostgreSQL. It covers orchestration traceability only; it does not add auth, billing, or frontend analytics.

## Migration

Migration file:

- `backend/alembic/versions/20260407_0003_create_phase6_orchestration_tables.py`

ORM models:

- `backend/app/db/models/pipeline_run.py`
- `backend/app/db/models/pipeline_stage_event.py`
- `backend/app/db/models/pipeline_artifact.py`
- `backend/app/db/models/pipeline_output.py`
- `backend/app/db/models/retry_attempt.py`
- `backend/app/db/models/verification_issue.py`

Repository:

- `backend/app/db/repositories/orchestration_repository.py`

## Why Each Table Exists

### pipeline_runs

`pipeline_runs` is the aggregate root for one end-to-end resume generation request.

It stores:

- Stable run id as a UUID-formatted string.
- Lifecycle status.
- Requested template and requested mode.
- Job description hash.
- Source profile id.
- Start/completion timestamps and duration.
- Final error code/message for failed or blocked runs.

This table answers: "What happened to this generation request?"

### pipeline_stage_events

`pipeline_stage_events` stores a timeline of stage attempts for a run.

It stores:

- Run id.
- Stage name.
- Stage status.
- Start/end timestamps and duration.
- Attempt number.
- Human-readable message.
- `machine_payload_json` for structured, non-secret diagnostics.

This table answers: "Where did the pipeline fail, retry, or apply fallback?"

### pipeline_artifacts

`pipeline_artifacts` is the artifact manifest for stage outputs.

It stores:

- Run id.
- Stage name.
- Artifact type.
- Storage kind.
- Storage path/key for referenced artifacts.
- Inline JSON for small structured artifacts.
- Content hash.
- Creation timestamp.

This table answers: "Which exact artifacts were produced by each stage?"

### pipeline_outputs

`pipeline_outputs` stores the final output record for the generated resume artifact.

It stores:

- Run id.
- PDF path or storage key.
- LaTeX path or storage key.
- Page count.
- Compile status.
- Output metadata JSON.
- Creation timestamp.

This table answers: "Where is the final PDF/LaTeX output and how did compilation finish?"

### verification_issues

`verification_issues` already existed for Phase 4 item-level verification. Phase 6 extends it to support run-level traceability.

New run-level fields:

- `run_id`
- `output_item_ref`
- `issue_type`
- `description`
- `source_refs_json`
- `resolution_status`

Existing fields remain compatible:

- `verification_item_id`
- `category`
- `severity`
- `message`
- `source_span_json`
- `generated_span_json`
- `details_json`

This table answers: "Which generated content or output item was unsafe, unsupported, blocked, or remediated?"

### retry_attempts

`retry_attempts` stores explicit retry decisions and outcomes.

It stores:

- Run id.
- Stage name.
- Attempt number.
- Retry reason.
- Retry strategy.
- Result status.
- Creation timestamp.

This table answers: "Why did the pipeline retry, how did it retry, and what happened?"

## How A Run Is Represented Over Time

1. Insert one `pipeline_runs` row when a generation request is accepted.
2. Append `pipeline_stage_events` rows as each stage starts, succeeds, fails, retries, or applies fallback.
3. Insert `pipeline_artifacts` rows whenever a stage produces a durable or inline artifact.
4. Insert `retry_attempts` rows when orchestration decides to retry a failed stage.
5. Insert `verification_issues` rows when verification finds unsupported content or records a fallback/block decision.
6. Insert one `pipeline_outputs` row when final PDF/LaTeX output exists or compilation metadata must be recorded.
7. Update `pipeline_runs` with completed status, `completed_at`, `duration_ms`, and final error fields.

The run can be debugged from `pipeline_runs` first, then joined to events, artifacts, outputs, issues, and retries by `run_id`.

## Inline JSON Vs Referenced Artifacts

Store inline JSON when:

- The payload is small.
- It is structured metadata, not raw private content.
- It is needed for quick debugging.
- It does not contain secrets or private tokens.

Use `storage_path_or_key` when:

- The payload is large.
- The artifact is a PDF, `.tex`, compile log, model raw response, or long stage output.
- The artifact belongs in local storage, object storage, or Supabase Storage.
- The payload may contain private resume or job description content that should be fetched through stricter access controls.

Examples:

- Inline: stage status summary, selected artifact ids, compile diagnostics summary.
- Referenced: final PDF, final LaTeX, compile log, raw model response, full Phase 3 payload snapshot.

## Required Debug Fields

For failed runs, the minimum debugging path is:

- `pipeline_runs.status`
- `pipeline_runs.final_error_code`
- `pipeline_runs.final_error_message`
- `pipeline_stage_events.stage_name`
- `pipeline_stage_events.status`
- `pipeline_stage_events.attempt_number`
- `pipeline_stage_events.message`
- `pipeline_stage_events.machine_payload_json`
- `retry_attempts.reason`
- `retry_attempts.retry_strategy`
- `retry_attempts.result_status`
- `verification_issues.issue_type`
- `verification_issues.severity`
- `verification_issues.description`
- `verification_issues.source_refs_json`
- `verification_issues.resolution_status`

For successful runs, the minimum replay path is:

- `pipeline_runs.id`
- `pipeline_runs.job_description_hash`
- `pipeline_runs.source_profile_id`
- `pipeline_stage_events` in created order
- `pipeline_artifacts` by stage and artifact type
- `pipeline_outputs.pdf_path_or_storage_key`
- `pipeline_outputs.latex_path_or_storage_key`
- `pipeline_outputs.output_metadata_json`

## Supabase PostgreSQL Readiness

The schema uses PostgreSQL-compatible primitives:

- String UUID-formatted ids, consistent with current repository models.
- `JSONB` in migrations for structured metadata.
- Explicit foreign keys with cascade delete from `pipeline_runs`.
- Indexes on run, stage, status, artifact type, storage kind, job hash, and issue resolution dimensions.

No Supabase-specific client or auth policy is introduced in this phase. Row-level security policies can be added later when user identity and tenancy are defined.

## Privacy And Safety Rules

- Do not store raw secrets or private tokens.
- Do not mix pipeline events with frontend analytics.
- Do not add billing or auth tables here.
- Keep raw PDF/LaTeX/log artifacts behind storage references unless there is a deliberate inline debugging reason.
- Keep `machine_payload_json` and `output_metadata_json` bounded and diagnostic-focused.

