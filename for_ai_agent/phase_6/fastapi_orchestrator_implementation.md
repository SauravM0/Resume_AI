# Phase 6 FastAPI Orchestrator Implementation

## Files Created

- `backend/app/orchestration/errors.py`
- `backend/app/orchestration/runner.py`
- `backend/app/orchestration/stage_executor.py`
- `backend/app/orchestration/result_builder.py`
- `backend/app/orchestration/orchestrator.py`
- `backend/app/services/render_input_adapter.py`
- `backend/app/services/render_service.py`
- `backend/app/schemas/orchestration.py`
- `backend/app/api/routes/generate_resume.py`

## Files Modified

- `src/resume_optimizer/app.py`

## Route Flow

The new route is:

- `POST /api/generate-resume`

The route handler is intentionally thin:

1. FastAPI validates `PipelineInput`.
2. The handler calls `DEFAULT_RESUME_GENERATION_ORCHESTRATOR.run(request)`.
3. On success it returns `GenerateResumePipelineResponse`.
4. On `OrchestrationError` it returns a structured HTTP error with failure type, stage name, retry/fallback flags, and run id when available.

Existing routes remain registered:

- `POST /api/analyze-job`
- `POST /api/rank-resume-content`
- `POST /api/generate-resume-structure`
- `POST /api/generate-resume-with-verification`

## Service Flow

The orchestrator executes stages in this order:

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

The orchestrator creates a run through `PipelineRunRecorder`, then delegates each stage to `StageExecutor`. `StageExecutor` records stage start, success, retry, and failure events using the policy defined in the Phase 6 contract registry.

Final response model:

- `run_id`
- `status`
- `available_outputs`
- `warnings`
- `final_file_reference`
- `artifact_manifest`
- `stage_events`

## Error Flow

Structured stage failures use `StageExecutionError`.

Handled failure classes include:

- Invalid input: `input_validation`, `job_description_ingestion`, `source_profile_load`
- AI provider or schema failure: `job_description_parse`, `generation_provider`, `generation_schema`
- Verification rejection: `verification_blocked`, returned as HTTP 409
- LaTeX/render contract failure: `render_contract`, `latex_render`
- PDF compile failure: `pdf_compile`
- Artifact persistence setup failure: raised when `DATABASE_URL` is configured but SQLAlchemy persistence cannot be imported

The orchestrator does not silently swallow stage failures. It records failed stage events, finalizes the run with final error code/message when possible, commits recorded state, and re-raises the structured error to the route.

## Wrapped Existing Code

The orchestrator wraps these existing modules:

- `resume_optimizer.loaders.load_and_normalize_master_profile`
- `resume_optimizer.normalizers.normalize_master_profile`
- `resume_optimizer.validators.validate_master_profile`
- `resume_optimizer.ai_service.analyze_job_description`
- `resume_optimizer.job_normalizers.normalize_job_analysis`
- `resume_optimizer.ranking_service.build_phase2_ranking_artifacts`
- `resume_optimizer.services.phase3_service.Phase3Service`
- `backend.app.services.verification.orchestrator.VerificationOrchestrator`
- `backend.app.services.template_registry`
- `backend.app.services.latex_mapper`
- `backend.app.services.layout_manager`
- `backend.app.services.document_assembler`
- `backend.app.services.pdf_compiler.compile_tex_document`

## Replaced Code

No existing public endpoint was removed or replaced.

The implementation adds a new Phase 6 endpoint and service layer. The older `generate-resume-with-verification` endpoint remains available for the existing Phase 3+4 flow.

## Persistence Behavior

`PipelineRunRecorder` uses `DATABASE_URL` when configured and lazily creates an `OrchestrationRepository`. If `DATABASE_URL` is not configured, it records events/artifacts in memory and includes a warning in the API response.

The route does not execute SQL and does not import repository classes directly.

## Progress Reporting

The API response includes `stage_events`, and the recorder writes stage events to persistence when configured. A future progress endpoint can read `pipeline_stage_events` by run id and return the same stage-event shape without coupling to route logic.

