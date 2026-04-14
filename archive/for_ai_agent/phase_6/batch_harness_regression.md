# Phase 6 Batch Harness and Regression Framework

This document describes the internal orchestration regression harness for Phase 6.

## Files Created

- `backend/tests/__init__.py`
- `backend/tests/orchestration/__init__.py`
- `backend/tests/orchestration/pipeline_harness.py`
- `backend/tests/orchestration/test_pipeline_regression_harness.py`
- `backend/tests/fixtures/pipeline_cases/regression_cases.json`
- `scripts/run_pipeline_regression.py`

## Purpose

The harness runs multiple deterministic end-to-end orchestration scenarios and reports:

- Final run status.
- Failed stage, if any.
- Error type, if any.
- Stage-level outcomes and attempts.
- Retry attempts.
- Fallback decisions.
- Artifact kinds emitted by the run.
- Snapshot-like structural fields.

The default harness does not call live AI providers and does not require a local LaTeX compiler. It uses a deterministic fake stage registry while still exercising the real orchestrator, recorder, stage executor, retry/fallback policy, artifact recording, and stage event paths.

## How To Run

Run the default suite:

```bash
PYTHONPATH=src:. python3 scripts/run_pipeline_regression.py
```

Write the report to a file:

```bash
PYTHONPATH=src:. python3 scripts/run_pipeline_regression.py \
  --output /tmp/pipeline_regression_report.json
```

Choose an artifact root:

```bash
PYTHONPATH=src:. python3 scripts/run_pipeline_regression.py \
  --artifact-root /tmp/resumeai-regression-artifacts
```

Run pytest coverage:

```bash
PYTHONPATH=src:. pytest -q -s backend/tests/orchestration/test_pipeline_regression_harness.py
```

## Existing Case Coverage

The default fixture file is:

```text
backend/tests/fixtures/pipeline_cases/regression_cases.json
```

It includes:

- `strong_match`
- `moderate_match`
- `weak_match`
- `short_jd`
- `noisy_jd`
- `special_characters`
- `latex_sensitive_content`
- `verifier_rejection`
- `retry_triggering`

## How To Add A New Regression Case

Add an object to `backend/tests/fixtures/pipeline_cases/regression_cases.json`.

Minimum fields:

```json
{
  "case_id": "new_case",
  "scenario_type": "strong_match",
  "job_description_text": "Job description text used by the harness.",
  "expected_status": "succeeded",
  "snapshot_fields": ["stage_sequence", "artifact_kinds"]
}
```

Optional failure fields:

```json
{
  "forced_failure_stage": "verify_generated_content",
  "forced_failure_type": "verification_blocked",
  "expected_terminal_stage": "verify_generated_content"
}
```

Optional retry field:

```json
{
  "retry_once_stage": "generate_structured_content",
  "forced_failure_type": "generation_schema"
}
```

Use stable `case_id` values because they are used in deterministic `run_id` values.

## Pass And Fail Criteria

A case passes when:

- The final status equals `expected_status`.
- If `expected_terminal_stage` is set, the localized failed stage matches it.
- The harness completes without unclassified fixture/model errors.

A batch passes when:

- `failed_count` is `0`.
- Every case result has `passed: true`.

A case fails when:

- The run status differs from expectation.
- The pipeline fails at a different stage than expected.
- A strict contract validation error occurs in the fixture builder.
- Retry/fallback metadata is missing for cases that are intended to exercise those paths.

## Stage-Level Diagnostics

Each result includes `stage_outcomes`:

```json
{
  "stage_name": "generate_structured_content",
  "status": "retrying",
  "attempt_number": 1,
  "failure_type": "generation_schema"
}
```

Use this field to identify exactly where a regression started.

Retry information is emitted in `retry_attempts`.

Fallback information is emitted in `fallback_decisions`.

## Snapshot-Like Validation

Good snapshot fields:

- `stage_sequence`
- `artifact_kinds`
- final status
- failed stage
- error type
- retry strategy
- fallback strategy
- presence of PDF artifact kind

Avoid snapshotting too rigidly:

- Exact generated prose.
- Full raw job description text.
- Large nested Pydantic payloads.
- Timestamps.
- UUIDs.
- Local temp paths.
- Exact human-readable error prose from Pydantic or provider exceptions.

Reasoning:

- The orchestration contract should be stable.
- Human prose and local paths are allowed to vary without indicating a product regression.
- Safety, provenance, stage order, and artifact presence are the high-value assertions.

## Golden-Case Coverage

The harness provides structural golden coverage rather than full prose goldens.

Current golden-like assertions:

- Successful cases complete all ten Phase 6 stages in order.
- Successful cases emit expected artifact kinds including `job_analysis`, `phase3_result`, `verification_report`, and `pdf`.
- Verifier rejection blocks at `verify_generated_content`.
- Retry-triggering case retries only `generate_structured_content` and then succeeds.

## Limitations

- The default harness does not call live AI providers.
- The default harness does not compile LaTeX with `pdflatex`.
- It is intended for orchestration regression, not final model-quality evaluation.
- A separate provider-enabled suite can be added later, but it should be opt-in because it will be slower and less deterministic.
