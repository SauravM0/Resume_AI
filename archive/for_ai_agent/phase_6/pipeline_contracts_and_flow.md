# Phase 6 Pipeline Contracts And Flow

This document defines the canonical contract boundary for end-to-end resume generation. It does not redesign the product idea and does not define runtime business logic.

## Exact Stage Order

1. `load_source_profile`
2. `normalize_source_data`
3. `ingest_job_description`
4. `parse_job_description`
5. `rank_select_evidence`
6. `generate_structured_content`
7. `verify_generated_content`
8. `render_deterministic_latex`
9. `compile_pdf`
10. `persist_artifacts`

## Why This Order Exists

The pipeline starts with source truth because every downstream stage must remain grounded in the candidate profile. Source data is normalized before ranking so the evidence selector sees canonical IDs, dates, skills, and provenance. The job description is ingested before parsing so raw input can be validated and fingerprinted. Ranking must happen before generation so the model only sees selected, source-linked evidence. Verification must happen before rendering because Phase 5 must not render unsupported generated claims. LaTeX rendering happens before PDF compilation because compilation needs a complete deterministic `.tex` document. Artifact persistence is last so it can persist the final manifest and any intermediate outputs emitted by earlier stages.

## Contract Files

- `backend/app/orchestration/enums.py`
- `backend/app/orchestration/types.py`
- `backend/app/orchestration/pipeline_models.py`
- `backend/app/orchestration/contracts.py`

These files contain Pydantic models and enums only. They do not call LLM providers, write to databases, render LaTeX, or compile PDFs.

## Pipeline Input

Model: `PipelineInput`

Required:

- `job_description_text`
- One profile source: `source_profile`, `source_profile_path`, or `source_profile_id`

Optional:

- `pipeline_run_id`
- `job_posting_url`
- `generation_preferences`
- `template_id`
- `render_job_id`
- `persist_intermediate_artifacts`
- `frontend_correlation_id`

## Stage Contracts

### 1. load_source_profile

Input model: `LoadSourceProfileInput`

Required inputs:

- `source_profile`, `source_profile_path`, or `source_profile_id`

Output model: `LoadSourceProfileOutput`

Output:

- `source_profile_id`
- `source_profile`
- `loaded_from`

Failure types:

- `input_validation`
- `source_profile_load`

Retry eligibility: not retryable by default.

Fallback eligibility: not allowed.

Existing module wrapper candidates:

- `resume_optimizer.loaders`

### 2. normalize_source_data

Input model: `NormalizeSourceDataInput`

Required inputs:

- `source_profile`
- `source_profile_id`

Output model: `NormalizeSourceDataOutput`

Output:

- `source_profile_id`
- `normalized_profile`
- `normalization_applied`
- `validation_warnings`

Failure types:

- `input_validation`
- `source_profile_normalization`

Retry eligibility: not retryable by default.

Fallback eligibility: not allowed.

Existing module wrapper candidates:

- `resume_optimizer.normalizers`
- `resume_optimizer.validators`

### 3. ingest_job_description

Input model: `IngestJobDescriptionInput`

Required inputs:

- `job_description_text`

Optional:

- `job_posting_url`

Output model: `IngestJobDescriptionOutput`

Output:

- `request`
- `jd_hash`
- `source_url`

Failure types:

- `input_validation`
- `job_description_ingestion`

Retry eligibility: not retryable by default.

Fallback eligibility: not allowed.

### 4. parse_job_description

Input model: `ParseJobDescriptionInput`

Required inputs:

- `request`

Output model: `ParseJobDescriptionOutput`

Output:

- `raw_analysis`
- `normalized_analysis`
- `model_artifact_ref`

Failure types:

- `input_validation`
- `job_description_parse`
- `timeout`

Retry eligibility: retryable with backoff.

Fallback eligibility: not allowed.

Existing module wrapper candidates:

- `resume_optimizer.ai_service`
- `resume_optimizer.job_normalizers`

Provider boundary:

- The orchestrator must not hardcode an LLM provider. A stage implementation may inject a model client behind this contract.

### 5. rank_select_evidence

Input model: `RankSelectEvidenceInput`

Required inputs:

- `job_analysis`
- `source_profile`

Output model: `RankSelectEvidenceOutput`

Output:

- `ranking_response`
- `selection_result`

Failure types:

- `input_validation`
- `ranking_selection`

Retry eligibility: not retryable by default.

Fallback eligibility: not allowed.

Existing module wrapper candidates:

- `resume_optimizer.ranking_service`

### 6. generate_structured_content

Input model: `GenerateStructuredContentInput`

Required inputs:

- `job_analysis`
- `phase2_selection`
- `phase2_ranking`
- `source_profile`

Optional:

- `generation_preferences`

Output model: `GenerateStructuredContentOutput`

Output:

- `request`
- `generation_payload`
- `section_plan`
- `phase3_result`
- `validation_report`

Failure types:

- `input_validation`
- `generation_provider`
- `generation_schema`
- `timeout`

Retry eligibility: retryable with backoff.

Fallback eligibility: allowed for schema failures when the existing Phase 3 fallback validator can produce source-grounded output.

Existing module wrapper candidates:

- `resume_optimizer.services.phase3_service`

Provider boundary:

- The orchestrator must call a stage implementation, not a provider SDK directly.

### 7. verify_generated_content

Input model: `VerifyGeneratedContentInput`

Required inputs:

- `source_profile_id`
- `job_analysis`
- `source_profile`
- `generation_payload`
- `phase3_result`

Optional:

- `phase3_validation_report`

Output model: `VerifyGeneratedContentOutput`

Output:

- `verification_run_id`
- `verification_report`
- `rendering_output`

Failure types:

- `input_validation`
- `verification_blocked`
- `verification_retryable`

Retry eligibility: retryable for retryable verification failures.

Fallback eligibility: allowed only when the verification report says content is renderable or provides a safe fallback action.

Existing module wrapper candidates:

- `backend.app.services.verification.orchestrator`

### 8. render_deterministic_latex

Input model: `RenderDeterministicLatexInput`

Required inputs:

- `source_profile`
- `rendering_output`
- `template_id`
- `render_job_id`

Output model: `RenderDeterministicLatexOutput`

Output:

- `render_input`
- `assembled_document`
- `render_output`

Failure types:

- `input_validation`
- `render_contract`
- `latex_render`

Retry eligibility: not retryable by default.

Fallback eligibility: not allowed in the contract layer. Runtime rendering may only use deterministic layout/template fallbacks that do not change verified content semantics.

Existing module wrapper candidates:

- `backend.app.models.render_models`
- `backend.app.services.template_registry`
- `backend.app.services.latex_mapper`
- `backend.app.services.layout_manager`
- `backend.app.services.document_assembler`

### 9. compile_pdf

Input model: `CompilePdfInput`

Required inputs:

- `render_job_id`
- `template_id`
- `assembled_document`

Output model: `CompilePdfOutput`

Output:

- `compile_result`
- `pdf_artifact_ref`
- `log_artifact_ref`

Failure types:

- `input_validation`
- `pdf_compile`
- `timeout`

Retry eligibility: retryable.

Fallback eligibility: not allowed by default.

Existing module wrapper candidates:

- `backend.app.services.pdf_compiler`

### 10. persist_artifacts

Input model: `PersistArtifactsInput`

Required inputs:

- `pipeline_run_id`
- `stage_results`

Optional:

- `requested_artifact_kinds`

Output model: `PersistArtifactsOutput`

Output:

- `pipeline_run_id`
- `artifact_refs`
- `result_artifact_ref`

Failure types:

- `input_validation`
- `artifact_persistence`

Retry eligibility: retryable with backoff.

Fallback eligibility: not allowed in the contract layer.

## Stage Result Envelope

Model: `StageResult`

Fields:

- `pipeline_run_id`
- `stage_name`
- `status`
- `attempt`
- `timing`
- `output`
- `output_artifacts`
- `errors`
- `warnings`
- `retry_eligible`
- `fallback_eligible`
- `fallback_applied`

Rules:

- A `succeeded` stage must include `output`.
- A `failed` or `blocked` stage must include at least one `StageError`.
- `fallback_applied` requires `fallback_eligible`.

## Final Pipeline Result

Model: `PipelineResult`

Fields:

- `pipeline_run_id`
- `status`
- `started_at`
- `finished_at`
- `stage_results`
- `artifact_manifest`
- `final_pdf_artifact`
- `final_latex_artifact`
- `verification_report`
- `errors`
- `warnings`

Rules:

- A successful result must include `final_pdf_artifact`.
- A failed or blocked result must include at least one `StageError`.

## Sample Success Payload

```json
{
  "pipeline_run_id": "pipeline.123",
  "status": "succeeded",
  "stage_results": [
    {
      "pipeline_run_id": "pipeline.123",
      "stage_name": "compile_pdf",
      "status": "succeeded",
      "attempt": 1,
      "output_artifacts": [
        {
          "artifact_id": "artifact.pdf.123",
          "kind": "pdf",
          "stage_name": "compile_pdf",
          "storage_backend": "local_file",
          "schema_version": "phase6.artifact.v1",
          "uri": "/tmp/resume.pdf",
          "content_type": "application/pdf"
        }
      ],
      "errors": [],
      "warnings": [],
      "retry_eligible": false,
      "fallback_eligible": false,
      "fallback_applied": false
    }
  ],
  "artifact_manifest": [
    {
      "artifact_id": "artifact.pdf.123",
      "kind": "pdf",
      "stage_name": "compile_pdf",
      "storage_backend": "local_file",
      "schema_version": "phase6.artifact.v1",
      "uri": "/tmp/resume.pdf",
      "content_type": "application/pdf"
    }
  ],
  "final_pdf_artifact": {
    "artifact_id": "artifact.pdf.123",
    "kind": "pdf",
    "stage_name": "compile_pdf",
    "storage_backend": "local_file",
    "schema_version": "phase6.artifact.v1",
    "uri": "/tmp/resume.pdf",
    "content_type": "application/pdf"
  },
  "errors": [],
  "warnings": []
}
```

The sample omits nested successful stage `output` objects for readability. Runtime payloads should include the typed output where appropriate.

## Sample Failure Payload

```json
{
  "pipeline_run_id": "pipeline.456",
  "status": "failed",
  "stage_results": [
    {
      "pipeline_run_id": "pipeline.456",
      "stage_name": "verify_generated_content",
      "status": "failed",
      "attempt": 1,
      "output": null,
      "output_artifacts": [],
      "errors": [
        {
          "error_id": "error.verify.1",
          "stage_name": "verify_generated_content",
          "failure_type": "verification_blocked",
          "message": "Generated content failed verification and cannot be rendered.",
          "retryable": false,
          "fallback_eligible": false
        }
      ],
      "warnings": [],
      "retry_eligible": false,
      "fallback_eligible": false,
      "fallback_applied": false
    }
  ],
  "artifact_manifest": [],
  "final_pdf_artifact": null,
  "errors": [
    {
      "error_id": "error.verify.1",
      "stage_name": "verify_generated_content",
      "failure_type": "verification_blocked",
      "message": "Generated content failed verification and cannot be rendered.",
      "retryable": false,
      "fallback_eligible": false
    }
  ],
  "warnings": []
}
```

## Artifact Persistence

Each stage may emit `PipelineArtifactRef` values. These references are serializable and can point to:

- `inline` JSON snapshots
- `local_file` paths
- `postgres` records
- `supabase_storage` objects
- `external` systems

Contracts do not write artifacts directly. A persistence stage or repository adapter is responsible for converting stage outputs into durable records.

Recommended artifact mapping:

- `load_source_profile` -> `source_profile`
- `normalize_source_data` -> `normalized_profile`
- `ingest_job_description` -> `raw_job_description`
- `parse_job_description` -> `job_analysis`
- `rank_select_evidence` -> `phase2_selection`, `phase2_ranking`
- `generate_structured_content` -> `phase3_request`, `phase3_payload`, `phase3_section_plan`, `phase3_result`, `phase3_validation_report`
- `verify_generated_content` -> `verification_report`, `rendering_gate`
- `render_deterministic_latex` -> `render_input`, `latex_document`
- `compile_pdf` -> `pdf`, `compile_log`
- `persist_artifacts` -> `pipeline_result`

## Frontend Stage Events

Frontend clients should treat stage updates as an ordered stream of `StageEvent` or `StageResult` summaries.

Interpretation rules:

- `pending`: stage has not started.
- `running`: stage is active; show progress.
- `retrying`: stage failed in a retryable way and is being attempted again.
- `fallback_applied`: deterministic fallback was used; show a warning but continue unless final result fails.
- `succeeded`: stage is complete; artifact references may be available.
- `failed`: stage failed; show the stage error and stop unless the orchestrator emits a later retry event.
- `blocked`: policy prevents continuation, usually from verification or validation.
- `skipped`: stage was intentionally omitted by policy.

Frontend should not infer payload shape from stage name strings. It should use `stage_name`, `status`, `errors`, `warnings`, and `artifact_refs`, then request full artifacts by `artifact_id` when needed.

## Future Extensibility

The stage contract format is not resume-only. A later cover-letter pipeline can add new `StageName` values and stage IO models while reusing:

- `PipelineInput` style request envelopes
- `StageResult`
- `StageError`
- `PipelineArtifactRef`
- `PipelineResult`
- retry and fallback policy models

