# Phase 6 Stage Adapters

This document records the adapter layer between existing Phase 1-5 implementation modules and the Phase 6 orchestrator. The adapters standardize invocation through `execute(stage_input, context) -> stage_output` and translate stage failures into `StageExecutionError`.

## Common Interface

Adapter base path: `backend/app/orchestration/adapters/base.py`

Registry path: `backend/app/orchestration/stage_registry.py`

Standard context:

```python
StageExecutionContext(
    run_id: str,
    stage_name: StageName,
    recorder: PipelineRunRecorder | None,
    metadata: dict[str, Any],
)
```

The orchestrator calls the registry for these wrapped stages:

```text
parse_job_description
rank_select_evidence
generate_structured_content
verify_generated_content
render_deterministic_latex
compile_pdf
```

The load, normalize, ingest, and persist stages remain inside `backend/app/orchestration/orchestrator.py` for now because they are lightweight orchestration glue rather than Phase 1-5 product modules.

## Adapter Map

### Job Parsing

Original module paths:

- `src/resume_optimizer/ai_service.py`
- `src/resume_optimizer/job_normalizers.py`

Adapter path:

- `backend/app/orchestration/adapters/job_parser_adapter.py`

Original input/output:

- Input: raw job description text passed to `analyze_job_description(job_description_text)`.
- Intermediate output: `ParsedJobAnalysisResponse`.
- Normalization input: `normalize_job_analysis(raw_analysis, job_description_text)`.
- Output: `NormalizedJobAnalysis`.

Normalized input/output:

- Input: `ParseJobDescriptionInput(request=RawJobDescriptionRequest)`.
- Output: `ParseJobDescriptionOutput(raw_analysis, normalized_analysis)`.

Exception mapping:

- `JobAnalysisError` and other exceptions become `StageExecutionError` with `JOB_DESCRIPTION_PARSE`.
- The error is retryable because the underlying dependency may be an AI provider call.

Assumptions:

- The adapter preserves existing prompt/provider behavior by calling `analyze_job_description` directly.
- The adapter does not introduce fallback parsing.

Dangerous or inconsistent:

- Provider behavior is still hidden behind `resume_optimizer.ai_service`.
- Raw analysis may be `None` only if future parsing becomes deterministic; current adapter preserves it when returned.

### Evidence Ranking

Original module path:

- `src/resume_optimizer/ranking_service.py`

Adapter path:

- `backend/app/orchestration/adapters/ranker_adapter.py`

Original input/output:

- Input: `NormalizedJobAnalysis`, `MasterProfile`.
- Output: `Phase2RankingArtifacts` with `ranking_response` and `selection_result`.

Normalized input/output:

- Input: `RankSelectEvidenceInput(job_analysis, source_profile)`.
- Output: `RankSelectEvidenceOutput(ranking_response, selection_result)`.

Exception mapping:

- Any ranking exception becomes `StageExecutionError` with `RANKING_SELECTION`.

Assumptions:

- Ranking is deterministic enough to reuse directly.
- No retry is set because local ranking failures usually indicate schema or data mismatch rather than transient infrastructure.

Dangerous or inconsistent:

- The ranking service returns a composite artifact object, while the Phase 6 contract persists the split fields. The adapter performs that split explicitly.

### Structured Generation

Original module paths:

- `src/resume_optimizer/services/phase3_service.py`
- `src/resume_optimizer/phase3_generation_service.py`

Adapter path:

- `backend/app/orchestration/adapters/generator_adapter.py`

Original input/output:

- Input: `job_analysis`, `phase2_selection`, `phase2_ranking`, `source_profile`, optional `generation_preferences`.
- Output: Phase 3 service result containing request, generation payload, section plan, generation result, and validation report.

Normalized input/output:

- Input: `GenerateStructuredContentInput`.
- Output: `GenerateStructuredContentOutput`.

Exception mapping:

- `Phase3GenerationError` becomes `GENERATION_PROVIDER`.
- Other exceptions become `GENERATION_SCHEMA`.
- Both are marked retryable and fallback eligible at the adapter boundary.

Assumptions:

- Existing prompt behavior remains inside `Phase3Service.run`.
- The adapter does not inject provider configuration or prompt text.

Dangerous or inconsistent:

- Provider failures and schema failures are still coupled inside Phase 3 internals in some paths. The adapter makes a best-effort distinction only where the existing exception type supports it.

### Verification

Original module paths:

- `backend/app/services/verification/orchestrator.py`
- `backend/app/schemas/verification.py`
- `backend/app/services/verification/types.py`

Adapter path:

- `backend/app/orchestration/adapters/verifier_adapter.py`

Original input/output:

- Input: `Phase3VerificationInput`, `generation_id`, optional `pipeline_run_id`.
- Output: verification result with `verification_run_id`, `report`, and `rendering_output`.

Normalized input/output:

- Input: `VerifyGeneratedContentInput`.
- Output: `VerifyGeneratedContentOutput`.

Exception mapping:

- Execution errors become `VERIFICATION_RETRYABLE`.
- Reports with `FAILED` or `BLOCKED` status become `VERIFICATION_BLOCKED` with HTTP 409 semantics.

Assumptions:

- Verification remains the render gate. The adapter does not bypass failed or blocked reports.
- `pipeline_run_id` is taken from `StageExecutionContext.run_id`.

Dangerous or inconsistent:

- `generation_id` is derived from `phase3_result.metadata.source_profile_id`, which is existing behavior carried forward from the previous orchestration implementation. A future refinement should introduce a dedicated generation artifact ID.

### LaTeX Rendering

Original module paths:

- `backend/app/services/render_input_adapter.py`
- `backend/app/services/render_service.py`

Adapter path:

- `backend/app/orchestration/adapters/latex_renderer_adapter.py`

Original input/output:

- Input to bridge: `source_profile`, `Phase4RenderingOutput`, `template_id`, `render_job_id`.
- Input to render service: `RenderJobInput`.
- Output: render service result with `render_input`, `assembled_document`, and optional `render_output`.

Normalized input/output:

- Input: `RenderDeterministicLatexInput`.
- Output: `RenderDeterministicLatexOutput`.

Exception mapping:

- `RenderInputAdapterError` becomes `RENDER_CONTRACT`.
- Other render exceptions become `LATEX_RENDER`.

Assumptions:

- Rendering remains deterministic and does not call an LLM.
- The adapter only bridges verified output into the render service.

Dangerous or inconsistent:

- The Phase 4 rendering output must be renderable and must match the source profile ID. The adapter preserves those checks.
- Render artifacts are still represented by service objects, while persistence records a serialized contract artifact from the orchestrator.

### PDF Compilation

Original module path:

- `backend/app/services/pdf_compiler.py`

Adapter path:

- `backend/app/orchestration/adapters/pdf_compile_adapter.py`

Original input/output:

- Input: `tex_content`, `render_job_id`, `template_id`.
- Output: `PdfCompileResult` with PDF path, log path, return code, warnings, errors, and compile status.

Normalized input/output:

- Input: `CompilePdfInput(render_job_id, template_id, assembled_document)`.
- Output: `CompilePdfOutput(compile_result, pdf_artifact_ref, log_artifact_ref)`.

Exception mapping:

- Exceptions and unsuccessful compile results become `PDF_COMPILE`.
- Compile failures are retryable because they can be caused by transient filesystem or compiler availability issues.

Assumptions:

- The adapter persists PDF and log artifact references through `context.recorder` when available.
- The adapter records the final output row on successful compilation when a recorder is available.

Dangerous or inconsistent:

- Local filesystem paths are still the immediate artifact reference. Supabase storage upload is not implemented in this adapter.
- Failed compile diagnostics are preserved in `PdfCompileResult` only when the compiler service returns a result. Exceptions before result creation only preserve the exception message.

## Registry Behavior

`StageRegistry` owns adapter lookup and dispatch. The orchestrator no longer imports the internal Phase 1-5 implementation modules for these six stages. It passes typed pipeline model inputs to the registry and receives typed pipeline model outputs.

Default registry contents:

- `JobParserAdapter`
- `RankerAdapter`
- `GeneratorAdapter`
- `VerifierAdapter`
- `LatexRendererAdapter`
- `PdfCompileAdapter`

The registry can be replaced in tests by constructing `ResumeGenerationOrchestrator(stage_registry=custom_registry)`.

## What Was Wrapped vs Replaced

Wrapped:

- Job parsing AI service and job normalizer.
- Phase 2 ranking artifact builder.
- Phase 3 service.
- Phase 4 verification orchestrator.
- Phase 4 to Phase 5 render input bridge and render service.
- PDF compiler service.

Replaced:

- Direct orchestration calls to these modules inside `backend/app/orchestration/orchestrator.py` were replaced with `StageRegistry.execute(...)`.

Not changed:

- Prompt behavior.
- Ranking algorithm.
- Verification rules.
- Deterministic LaTeX mapping and layout behavior.
- PDF compilation command behavior.

## Remaining Risks

- The retry and fallback policy layer is still outside the adapters; adapters only mark classification metadata on `StageExecutionError`.
- Some adapters still classify broad exceptions because underlying modules do not expose finer-grained exception types.
- The PDF adapter persists local paths, not Supabase object keys.
- Artifact extraction exists in the base interface but the orchestrator still records most serialized Pydantic model artifacts centrally.
- Source profile load, source normalization, job ingestion, and final artifact persistence do not yet use adapter classes.
