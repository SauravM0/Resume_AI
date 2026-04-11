# Phase 6 Artifact Storage and Cleanup

This document defines how Phase 6 pipeline artifacts are stored, referenced, and cleaned up.

## Files Created

- `backend/app/orchestration/artifacts/__init__.py`
- `backend/app/orchestration/artifacts/models.py`
- `backend/app/orchestration/artifacts/storage_backends.py`
- `backend/app/orchestration/artifacts/cleanup.py`
- `backend/app/orchestration/artifacts/artifact_manager.py`
- `backend/app/tests/unit/test_artifact_manager.py`

## Files Modified

- `backend/app/orchestration/orchestrator.py`
- `backend/app/orchestration/adapters/pdf_compile_adapter.py`

## Artifact Lifecycle

1. A pipeline run is created with a stable `run_id`.
2. Each stage emits a stage event and, when meaningful, an artifact record.
3. Intermediate JSON artifacts are recorded through `ArtifactManager.persist_inline_json(...)`.
4. PDF compile artifacts are first written to the compiler temp workspace by the existing PDF compiler.
5. `ArtifactManager.persist_compile_result(...)` copies `.tex`, `.log`, and `.pdf` files from temp workspace into durable artifact storage.
6. The durable artifact references are recorded through `PipelineRunRecorder.record_artifact(...)`.
7. The final output row is recorded with durable PDF and LaTeX paths.
8. Only after durable copies and artifact references exist, the temp compile workspace is deleted.

## Durable vs Temporary Artifacts

Inline DB JSON artifacts:

- Parsed job JSON: `job_analysis`
- Ranked evidence and selection JSON: `phase2_selection`
- Generated structured content JSON: `phase3_result`
- Verification report JSON: `verification_report`
- Source and normalized profile artifacts when emitted by the orchestrator

Durable file artifacts:

- Rendered LaTeX from compile input: `outputs/resume.tex`
- Compile log: `outputs/compile.log`
- Final PDF: `outputs/resume.pdf`

Temporary artifacts:

- Compiler workspace directories created by `backend/app/services/pdf_compiler.py`
- Temporary `.aux`, intermediate LaTeX files, and transient compiler outputs inside the workspace

## Storage Backend Policy

Current implementation:

- Uses `LocalArtifactStorageBackend`.
- Default root: `data/pipeline_artifacts`.
- Override with `PIPELINE_ARTIFACT_ROOT`.
- Storage references are persisted as `local_file` artifact rows.

Supabase/PostgreSQL friendliness:

- Artifact metadata remains in PostgreSQL-compatible rows through `pipeline_artifacts`.
- Inline JSON remains structured JSON metadata.
- File storage is abstracted behind `ArtifactStorageBackend`, so Supabase Storage can replace local disk without changing orchestrator stage contracts.

Deployment warning:

- Local disk should not be treated as permanent in ephemeral deployments.
- For hosted or multi-node deployments, use object storage for final PDF, LaTeX, and logs.

## Cleanup Triggers

The cleanup path is intentionally narrow:

- Cleanup is triggered by `ArtifactManager.persist_compile_result(...)`.
- Cleanup only runs after file artifacts have been copied to durable storage.
- Cleanup calls `cleanup_compile_workspace(...)`.
- Cleanup refuses paths outside the system temp directory.
- Cleanup refuses paths that do not start with `resume-render-`.

This prevents accidental deletion of durable outputs or unrelated user files.

## Failure-Safe Behavior

Successful compile:

- If durable artifact persistence fails after PDF compilation, the adapter raises `ARTIFACT_PERSISTENCE`.
- The run must not report success without durable output references.
- Temp workspace cleanup is not allowed to run before durable output persistence.

Failed compile:

- The adapter attempts to persist available `.tex` and `.log` diagnostics.
- If compile output persistence fails during a failed compile, the run still fails as `PDF_COMPILE`.
- The policy layer may retry the compile stage, but it does not rerun upstream generation.

Partial runs:

- Artifacts recorded before failure remain traceable by `run_id`.
- Final `pipeline_outputs` are only recorded after successful compile artifact persistence.
- Cleanup targets only compiler temp workspaces, not DB rows or durable artifact files.

## What Must Be Deleted

Safe temporary cleanup targets:

- Compiler workspace directory under the OS temp directory.
- Directory name must start with `resume-render-`.
- Auxiliary files inside that workspace.

What must not be deleted:

- `data/pipeline_artifacts/<run_id>/outputs/resume.pdf`
- `data/pipeline_artifacts/<run_id>/outputs/resume.tex`
- `data/pipeline_artifacts/<run_id>/outputs/compile.log`
- Any file outside the safe compiler temp workspace
- Any DB rows that preserve run traceability

## Stage-Aware Artifact Mapping

| Stage | Artifact | Storage |
|---|---|---|
| `load_source_profile` | source profile | inline JSON |
| `normalize_source_data` | normalized profile | inline JSON |
| `ingest_job_description` | raw job description metadata | inline JSON |
| `parse_job_description` | normalized job analysis | inline JSON |
| `rank_select_evidence` | ranking and selection output | inline JSON |
| `generate_structured_content` | Phase 3 generation result | inline JSON |
| `verify_generated_content` | verification report and render gate | inline JSON |
| `render_deterministic_latex` | assembled LaTeX model | inline JSON |
| `compile_pdf` | final PDF, LaTeX, compile log | durable file storage |
| `persist_artifacts` | artifact manifest summary | inline JSON |

## Current Limits

- The storage abstraction is local-disk backed by default.
- Supabase object storage is not implemented yet.
- Large intermediate JSON payloads are still stored inline; if payload size grows, move those to structured files or object storage while keeping metadata in PostgreSQL.
- Cleanup currently targets compile workspaces only; it does not perform retention cleanup of old durable artifacts.
