# Phase 6 Retry and Fallback Policy

This document defines the formal retry and fallback behavior used by the Phase 6 orchestration pipeline. The policy is keyed by `stage_name`, `error_type`, and `current_attempt`.

Code paths:

- `backend/app/orchestration/policies/policy_types.py`
- `backend/app/orchestration/policies/error_classifier.py`
- `backend/app/orchestration/policies/retry_policy.py`
- `backend/app/orchestration/policies/fallback_policy.py`
- `backend/app/orchestration/stage_executor.py`

## Policy Result Shape

Every failed stage attempt becomes a `PolicyRequest`:

```text
stage_name
failure_type
current_attempt
exception_type
message
```

The policy engine returns a `PolicyDecision`:

```text
action: retry | fallback | fail
retry: bool
fallback: bool
fail: bool
retry_strategy
fallback_strategy
max_attempts
backoff_seconds
safe_to_apply_automatically
escalation_note
```

Safe default:

- If no policy matches, the action is `fail`.
- The policy engine never retries infinitely.
- Fallback is never applied automatically unless a safe implementation hook exists and the policy explicitly marks it safe.

## Stage Policy Table

| Stage | Error type | Attempt | Decision | Strategy | Why |
|---|---|---:|---|---|---|
| `load_source_profile` | any | 1 | fail | none | Bad profile references or unreadable source data should not be retried blindly. |
| `normalize_source_data` | any | 1 | fail | none | Normalization failure means source data does not satisfy downstream contracts. |
| `ingest_job_description` | any | 1 | fail | none | Invalid request shape must be returned to caller, not retried. |
| `parse_job_description` | `job_description_parse` | 1 | retry | `stricter_instruction_path` | Malformed provider output can be retried once; stricter path is used only if an adapter hook exists. |
| `parse_job_description` | `job_description_parse` | 2 | fail | none | Repeated parser failure is terminal. |
| `parse_job_description` | `timeout` | 1 | retry | `fixed_backoff` | One transient provider timeout retry is allowed. |
| `rank_select_evidence` | `ranking_selection` | 1 | fallback | `deterministic_best_match_subset` | Empty rank result can only fall back to a source-backed deterministic subset if an explicit hook exists. |
| `generate_structured_content` | `generation_provider` | 1 | retry | `fixed_backoff` | One transient AI provider retry is allowed. |
| `generate_structured_content` | `generation_schema` | 1 | retry | `stricter_instruction_path` | Malformed generated JSON can be retried once; no prompt change is made unless supported by the adapter. |
| `generate_structured_content` | `generation_schema` | 2 | fail | none | Repeated schema failure is terminal and must not be hidden. |
| `generate_structured_content` | `timeout` | 1 | retry | `fixed_backoff` | One transient generation timeout retry is allowed. |
| `verify_generated_content` | `verification_retryable` | 1 | retry | `immediate` | Verifier execution failure can be retried once. |
| `verify_generated_content` | `verification_blocked` | 1 | fallback | `source_bullet_or_safer_rewrite` | Verification rejection may recover only through source-grounded fallback content. |
| `render_deterministic_latex` | `latex_render` | 1 | fallback | `latex_render_correction` | Deterministic render correction is allowed only if a hook preserves verified content. |
| `render_deterministic_latex` | `render_contract` | 1 | fail | none | Render contract mismatch means upstream verified output is not renderable. |
| `compile_pdf` | `pdf_compile` | 1 | retry | `local_render_correction` | One local compile retry is allowed without regenerating upstream content. |
| `compile_pdf` | `pdf_compile` | 2 | fallback | `latex_render_correction` | A correction fallback may be considered after retry budget, but only with a deterministic hook. |
| `compile_pdf` | `timeout` | 1 | retry | `fixed_backoff` | One transient compiler timeout retry is allowed. |
| `persist_artifacts` | `artifact_persistence` | 1 | fail | none | Persistence failure must fail fast if the run record cannot be trusted. |

## What Must Never Be Retried Blindly

- Source profile loading from an invalid or mismatched profile ID.
- Source profile normalization failures.
- Request validation and job description ingestion failures.
- Verification rejections caused by unsupported content.
- Render contract failures where verified output is not renderable.
- Artifact persistence failures when the DB run state cannot be trusted.
- Any stage after its explicit retry budget is exhausted.

## What Fallback Means for Content Safety

Fallback must never introduce new unsupported content. A fallback is only safe if it is either source-preserving or verifier-approved.

Allowed fallback concepts:

- Ranking fallback can use a deterministic best-match subset only if all selected items come from the source profile.
- Verification fallback can use original source bullet text or a safer rewrite only if provenance remains attached and unsupported claims are removed.
- LaTeX fallback can correct deterministic rendering or escaping issues only; it must not rewrite resume content.
- PDF compile fallback can retry or correct local LaTeX formatting only; it must not rerun job parsing, ranking, or generation.

Current implementation note:

- The policy engine records fallback decisions but does not fabricate fallback outputs.
- `safe_to_apply_automatically` is currently `False` for all fallback rules.
- If no explicit fallback hook is provided, the executor records the fallback decision and fails safely.

## Persistence Behavior

Retry attempts:

- Persisted through `PipelineRunRecorder.record_retry(...)`.
- Stored in the `retry_attempts` table when a repository is configured.
- Includes `stage_name`, `attempt_number`, `reason`, `retry_strategy`, and `result_status`.

Fallback decisions:

- Persisted through `PipelineRunRecorder.record_fallback_decision(...)`.
- Stored as `pipeline_stage_events` records when a repository is configured.
- Includes `fallback_strategy`, `applied`, `escalation_note`, and the full policy decision payload in `machine_payload_json`.
- Uses `skipped` status when fallback was considered but not applied.
- Uses `fallback_applied` status only when an explicit safe fallback hook actually ran.

Stage failures:

- Every failed attempt records a stage event with the classified `failure_type` and serialized policy decision.
- Repeated failure is never converted into success by the policy layer.

## Local Retry Scope

The executor retries only the failed stage operation. It does not rerun the full pipeline unless a future orchestrator explicitly chooses to restart a run.

Examples:

- A generation schema failure retries only `generate_structured_content`.
- A verifier execution failure retries only `verify_generated_content`.
- A PDF compile failure retries only `compile_pdf`.

## Debugging Expectations

A failed run should show:

- The original failing stage event.
- The policy decision payload.
- Any retry attempt rows.
- Any fallback decision stage events.
- The final pipeline error code and message.

This lets a human distinguish between:

- A transient failure that was retried and then succeeded.
- A fallback that was considered but not applied.
- A terminal failure where no safe recovery policy existed.
