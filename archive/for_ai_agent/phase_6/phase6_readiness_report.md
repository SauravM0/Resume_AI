# Phase 6 Readiness Report

Audit date: 2026-04-07

Scope: readiness audit for Phase 6 orchestration. This report preserves the existing AI-powered resume optimizer idea and does not redesign product behavior.

Repository note: `/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI` was not discoverable as a Git worktree during the audit (`git status` failed at `/mnt`). Treat this report as a filesystem audit, not a git-history audit.

## Executive Summary

The repo has strong Phase 0-3 contracts, a functional Phase 3 generation service, a Phase 4 verification service/orchestrator, and Phase 5 rendering primitives. It does not yet have full Phase 6 orchestration.

Phase 6 can safely build on the existing Python contracts and service modules, but must wrap them behind explicit stage contracts, artifact records, retry policy, and deterministic test seams. The largest blockers are:

- No React/TypeScript frontend exists in this checkout despite the stated stack.
- No full end-to-end Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 orchestrator exists.
- Existing `ResumePipelineService` only runs Phase 3 and Phase 4, not Phase 1, Phase 2, rendering, or PDF compilation.
- Phase 4 emits `Phase4RenderingOutput`, but there is no adapter from that output to Phase 5 `RenderJobInput`.
- Phase 5 has models, mapping, template loading, document assembly, layout, diagnostics, and PDF compiler utilities, but no top-level render service or API route.
- PostgreSQL/Supabase is only represented by SQLAlchemy models/repositories/migrations and `DATABASE_URL`; there is no Supabase client integration.
- Top-level `README.md` is stale: it says Phase 4/5 and frontend are not included, while backend Phase 4/5 code is present and frontend is still absent.
- Build artifacts under `build/lib/**` mirror source and must not be used as integration targets.

## Existing Modules

### Phase 0: Truth Model / Data Model

Files:

- `src/resume_optimizer/models.py`
- `src/resume_optimizer/loaders.py`
- `src/resume_optimizer/normalizers.py`
- `src/resume_optimizer/validators.py`
- `data/master_profile.example.json`

Responsibilities:

- Define strict Pydantic source-of-truth models (`MasterProfile`, profile entries, bullets, metrics, item types, dates, verified status, evidence strength).
- Load JSON profile files from disk.
- Normalize and validate master profile content.

Current input/output:

- Input: raw JSON object loaded from file path.
- Output: `MasterProfile` and optional `ProfileValidationReport`.

Status: complete for file-based local truth model; partially complete for production orchestration because user/profile persistence is not implemented.

Safe reuse:

- Reuse `MasterProfile`, `load_and_normalize_master_profile`, `validate_master_profile`, and normalizers as Stage 0 contract boundaries.

Unsafe for orchestration:

- `load_and_normalize_master_profile(DEFAULT_SETTINGS.default_profile_path)` is a local-file default. Phase 6 should wrap it as a profile source adapter and not hard-code it into end-to-end orchestration.

### Phase 1: Job Understanding

Files:

- `src/resume_optimizer/job_models.py`
- `src/resume_optimizer/ai_service.py`
- `src/resume_optimizer/job_normalizers.py`
- `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt`
- `src/resume_optimizer/openai_client.py`
- `src/resume_optimizer/app.py`
- `tests/test_phase1_core.py`
- `tests/test_phase1_api.py`

Responsibilities:

- Accept raw JD text via `RawJobDescriptionRequest`.
- Call OpenAI Responses API for strict JSON job analysis.
- Normalize raw model output into `NormalizedJobAnalysis`.
- Expose `POST /api/analyze-job`.

Current input/output:

- Input: `RawJobDescriptionRequest { job_description_text, job_posting_url? }`.
- AI raw output: `ParsedJobAnalysisResponse`.
- Canonical output: `NormalizedJobAnalysis` with role type, seniority, domain, skills, requirements, action verbs, culture signals, years required, and prioritized skills.

Status: partially complete.

Safe reuse:

- Reuse `NormalizedJobAnalysis` as the Phase 1 output contract.
- Reuse deterministic normalization functions.

Unsafe for orchestration:

- `analyze_job_description` owns only malformed JSON retry, not stage-level retry/backoff/artifact logging.
- OpenAI client/model settings are global defaults; Phase 6 should inject stage config and client where possible.
- The endpoint returns only the normalized result, not raw model response, prompt version, attempt count, or artifact references.

### Phase 2: Ranking / Selection

Files:

- `src/resume_optimizer/phase2_models.py`
- `src/resume_optimizer/ranking_models.py`
- `src/resume_optimizer/ranking_service.py`
- `src/resume_optimizer/services/phase2_service.py`
- `src/resume_optimizer/evidence_builder.py`
- `src/resume_optimizer/evidence_models.py`
- `src/resume_optimizer/evidence_pool.py`
- `src/resume_optimizer/scoring_engine.py`
- `src/resume_optimizer/scoring.py`
- `src/resume_optimizer/scoring_config.py`
- `src/resume_optimizer/phase2_config.py`
- `src/resume_optimizer/explainability.py`
- `src/resume_optimizer/job_feature_adapter.py`
- `src/resume_optimizer/provenance.py`
- `scripts/run_phase2_eval.py`
- `src/resume_optimizer/phase2_eval.py`
- `src/resume_optimizer/app.py`
- `tests/test_phase2_api.py`
- `tests/test_phase2_models.py`
- `tests/test_ranking_service.py`
- `tests/phase2/**`

Responsibilities:

- Adapt normalized job analysis into ranking features.
- Build canonical evidence units from a `MasterProfile`.
- Score and select experiences, projects, skills, and certifications.
- Produce diagnostics and ranking explanations.
- Expose legacy `POST /api/rank-resume-content`.

Current input/output:

- Input: `NormalizedJobAnalysis` plus `MasterProfile`.
- Service shortcut input: `NormalizedJobAnalysis` only, then loads default profile from disk.
- Output: `Phase2ServiceResult { ranking_response, phase2_result, persistence_* }`.
- Canonical selection output: `Phase2SelectionResult`.
- Legacy output: `RankingResponse`.

Status: complete for deterministic local ranking; partially complete for Phase 6 because persistence is a protocol/no-op and the public endpoint does not return the full canonical Phase 2 artifact.

Safe reuse:

- Reuse `build_phase2_ranking_artifacts` when Phase 6 already has `NormalizedJobAnalysis` and `MasterProfile`.
- Reuse `Phase2SelectionResult` and `RankingResponse` as explicit Stage 2 artifacts.

Unsafe for orchestration:

- `run_for_default_profile` hides profile loading and should be wrapped, not used as the main end-to-end stage implementation.
- `POST /api/rank-resume-content` returns only `RankingResponse`, omitting `Phase2SelectionResult` required by Phase 3.
- `Phase2PersistenceRepository` has no real implementation.

### Phase 3: Structured Content Generation

Files:

- `src/resume_optimizer/phase3_models.py`
- `src/resume_optimizer/phase3_assembler.py`
- `src/resume_optimizer/phase3_section_planner.py`
- `src/resume_optimizer/phase3_generation_service.py`
- `src/resume_optimizer/phase3_output_validation.py`
- `src/resume_optimizer/phase3_rewrite_policy.py`
- `src/resume_optimizer/phase3_headline_summary.py`
- `src/resume_optimizer/services/phase3_service.py`
- `src/resume_optimizer/prompts/phase3_generation_system_prompt.txt`
- `src/resume_optimizer/app.py`
- `tests/test_phase3_*.py`
- `tests/integration/test_phase3_integration.py`

Responsibilities:

- Validate Phase 1/2/source-profile alignment through `Phase3GenerationRequest` and `Phase3AssemblerInput`.
- Assemble compact generation payload.
- Plan section structure deterministically.
- Call the model for strict JSON.
- Validate/finalize generated content with conservative fallbacks.

Current input/output:

- Input: `Phase3AssemblerInput { job_analysis, phase2_selection, phase2_ranking, source_profile, generation_preferences? }`.
- Internal artifacts: `Phase3GenerationRequest`, `Phase3GenerationPayload`, `Phase3SectionPlan`, `Phase3ValidationReport`, `Phase3GenerationResultRecord`.
- Output from service: `Phase3ServiceResult`.
- Output from public endpoint `POST /api/generate-resume-structure`: only `Phase3GenerationResult`.

Status: complete for Phase 3 service-level generation; partially complete for Phase 6 because the API hides internal artifacts that Phase 4/5/observability need.

Safe reuse:

- Reuse `Phase3Service.run` as the Stage 3 implementation.
- Reuse `Phase3ServiceResult` as the artifact bundle.
- Reuse `Phase3ValidationReport` and `Phase3SectionPlan` for Phase 6 logs/artifacts.

Unsafe for orchestration:

- `Phase3ContentGenerationService` only retries malformed JSON once; it does not implement orchestration-level retry classification.
- Severe validation failure raises an exception and loses a typed failed-stage artifact unless Phase 6 wraps it.
- The standalone endpoint returns too little for downstream orchestration.

### Phase 4: Verification

Files:

- `backend/app/schemas/verification.py`
- `backend/app/services/verification/contracts.py`
- `backend/app/services/verification/orchestrator.py`
- `backend/app/services/verification/provenance_service.py`
- `backend/app/services/verification/deterministic_validators.py`
- `backend/app/services/verification/semantic_validator.py`
- `backend/app/services/verification/decision_engine.py`
- `backend/app/services/verification/matchers.py`
- `backend/app/services/verification/extractors.py`
- `backend/app/services/verification/rules.py`
- `backend/app/services/verification/types.py`
- `backend/app/services/ai/prompts/verification_semantic_check.txt`
- `backend/app/db/models/verification_run.py`
- `backend/app/db/models/verification_item.py`
- `backend/app/db/models/verification_issue.py`
- `backend/app/db/models/provenance_link.py`
- `backend/app/db/repositories/verification_repository.py`
- `backend/alembic/versions/20260407_0001_create_verification_tables.py`
- `backend/app/tests/unit/test_*verification*.py`
- `backend/app/tests/integration/test_verification_pipeline.py`

Responsibilities:

- Define Phase 3 -> Phase 4 input and Phase 4 -> rendering gate contracts.
- Build provenance links from generated content back to source truth.
- Run deterministic validators for metrics, tools, keywords, role inflation, leadership/seniority, and summary facts.
- Optionally run semantic faithfulness validation.
- Aggregate item/run decisions into a render gate.
- Optionally persist verification runs/items/issues/provenance via SQLAlchemy.

Current input/output:

- Input: `Phase3VerificationInput { source_profile_id, job_analysis, source_profile, generation_payload, phase3_result, phase3_validation_report? }`.
- Output: `VerificationRunResult { verification_run_id, started_at, finished_at, provenance_map, report, rendering_output }`.
- Rendering gate output: `Phase4RenderingOutput { source_profile_id, verified_result, verification_report, renderable, fallback_action }`.

Status: partially complete and generally reusable, but unsafe as a complete Phase 6 stage until wrapped.

Safe reuse:

- Reuse `VerificationOrchestrator.run` as the Stage 4 implementation.
- Reuse `Phase3VerificationInput`, `VerificationReport`, and `Phase4RenderingOutput`.
- Reuse `VerificationRepository` behind an orchestration persistence adapter.

Unsafe for orchestration:

- `Phase3VerificationInput` does not include `Phase3SectionPlan`; Phase 3 computes it but Phase 4 cannot consume it unless Phase 6 carries it separately.
- `_job_keywords` in `orchestrator.py` reads `preferred_requirements`, but `NormalizedJobAnalysis` uses `nice_to_have_requirements`; this silently drops preferred requirement keyword checks.
- Semantic validator retry is local to malformed JSON/schema only; orchestration-level retry and failure classification are missing.
- Existing `ResumePipelineService` commits only after verification and does not rollback/close sessions; Phase 6 should wrap session lifecycle.

### Phase 5: Deterministic Rendering / LaTeX / PDF

Files:

- `backend/app/models/render_models.py`
- `backend/app/services/rendering_contract.py`
- `backend/app/services/template_registry.py`
- `backend/app/templates/latex/ats_standard/v1/main.tex`
- `backend/app/services/latex_mapper.py`
- `backend/app/services/layout_manager.py`
- `backend/app/services/document_assembler.py`
- `backend/app/services/pdf_compiler.py`
- `backend/app/services/render_diagnostics.py`
- `backend/app/db/models/render_job.py`
- `backend/app/db/repositories/render_repository.py`
- `backend/alembic/versions/20260407_0002_create_render_jobs.py`
- `backend/app/tests/rendering/**`

Responsibilities:

- Define render input/output, section, artifact, diagnostic, and compile contracts.
- Load and validate controlled LaTeX templates.
- Escape and map display-ready render models into LaTeX fragments.
- Assemble final `.tex` by replacing known placeholders.
- Estimate layout and perform deterministic trimming.
- Compile `.tex` to PDF through `pdflatex`.
- Persist privacy-safe render diagnostics.

Current input/output:

- Renderer contract input: `RenderJobInput { render_job_id, source_profile_id, template_id, personal_info, summary?, experiences, projects, skills, education, certifications, sections, section_visibility, layout_constraints, render_options, verified_status, confidence }`.
- Mapper output: `SectionRenderResult` fragments keyed by `TemplatePlaceholder`.
- Assembler output: `AssembledDocument { template_id, template_version, tex_content, diagnostics }`.
- Compiler output: `PdfCompileResult` with `CompileResult` and artifact metadata.
- Final intended output model: `RenderJobOutput`.

Status: partially complete. Core primitives are present; top-level Stage 5 render orchestration is missing.

Safe reuse:

- Reuse render Pydantic models, `template_registry`, `latex_mapper`, `layout_manager`, `document_assembler`, `pdf_compiler`, and `render_diagnostics`.
- Reuse `ats_standard` LaTeX template as the initial default template.

Unsafe for orchestration:

- No implemented adapter converts `Phase4RenderingOutput` or `Phase3GenerationResult + MasterProfile` into `RenderJobInput`.
- No render service composes: validate prerequisites -> layout -> mapper -> template -> assembly -> compile -> diagnostics -> `RenderJobOutput`.
- No FastAPI route exposes rendering or full PDF artifact generation.
- `pdf_compiler.write_tex_file` writes to disk directly, which is appropriate for compilation but must be wrapped with artifact lifecycle controls and cleanup policy in Phase 6.

### Backend API Endpoints

Files:

- `src/resume_optimizer/app.py`
- `backend/app/api/routes/resume.py`

Endpoints:

- `POST /api/analyze-job`: input `RawJobDescriptionRequest`; output `NormalizedJobAnalysis`.
- `POST /api/rank-resume-content`: input `NormalizedJobAnalysis`; output `RankingResponse`.
- `POST /api/generate-resume-structure`: input `Phase3AssemblerInput`; output `Phase3GenerationResult`.
- `POST /api/generate-resume-with-verification`: input `Phase3AssemblerInput`; output `GenerateResumeVerificationResponse`; returns HTTP 409 when verification status maps to `verification_failed`.

Status: partially complete.

Gaps:

- No endpoint executes Phase 1 -> Phase 5 in one request.
- No endpoint returns a typed Phase 6 run artifact timeline.
- No endpoint returns PDF artifacts.
- No route exists outside `src/resume_optimizer/app.py` as the FastAPI app entrypoint; `backend/app/api/routes/resume.py` is included by that app, but `backend/app` does not define its own app factory.

### Frontend Request Flow

Files found: none.

Evidence:

- No `package.json`, `tsconfig`, `vite.config.*`, `next.config.*`, `.ts`, or `.tsx` files were found at the audited depth.
- Text search found backend API tests but no frontend `fetch`, Axios, React, or Supabase client code.

Status: missing.

Phase 6 implication:

- Orchestration should first expose stable backend contracts and testable endpoints. Frontend integration must be treated as future work unless frontend files are added.

### PostgreSQL / Supabase

Files:

- `backend/app/db/models/*.py`
- `backend/app/db/repositories/verification_repository.py`
- `backend/app/db/repositories/render_repository.py`
- `backend/alembic/versions/20260407_0001_create_verification_tables.py`
- `backend/alembic/versions/20260407_0002_create_render_jobs.py`
- `backend/app/services/pipeline_service.py`

Status: partially complete.

Current behavior:

- SQLAlchemy models/repositories and migrations exist for verification and render diagnostics.
- `ResumePipelineService` creates a SQLAlchemy engine/session from `DATABASE_URL` for verification persistence.

Gaps:

- No Supabase client.
- No Alembic config file found in repo root.
- No Phase 1/2/3 artifact persistence tables found.
- No render artifact storage integration.

## Exact Inconsistencies And Schema Mismatches

- README mismatch: `README.md` says frontend, resume generation, LaTeX, and PDF rendering are not included, but Phase 3 generation and Phase 4/5 backend modules are present. Frontend remains absent.
- API artifact mismatch: `POST /api/rank-resume-content` returns `RankingResponse`, but Phase 3 needs both `Phase2SelectionResult` and `RankingResponse`.
- API artifact mismatch: `POST /api/generate-resume-structure` returns only `Phase3GenerationResult`, but Phase 4 needs `Phase3GenerationPayload` and `Phase3ValidationReport`, and Phase 6 likely needs `Phase3SectionPlan`.
- Verification keyword mismatch: `backend/app/services/verification/orchestrator.py` reads `preferred_requirements`, but `NormalizedJobAnalysis` defines `nice_to_have_requirements`.
- Phase 4/5 handoff mismatch: `Phase4RenderingOutput` contains `verified_result` and `verification_report`; Phase 5 requires `RenderJobInput`. No adapter exists.
- Phase 3/4 artifact mismatch: `Phase3ServiceResult` includes `section_plan`, but `Phase3VerificationInput` does not.
- Persistence mismatch: Phase 2 has a persistence protocol but no implementation; Phase 4/5 have SQLAlchemy repositories.
- Stack mismatch: stated PostgreSQL via Supabase, but implementation uses raw SQLAlchemy `DATABASE_URL`; no Supabase-specific code exists.
- Build artifact hazard: `build/lib/**` duplicates source modules and should not be edited or imported intentionally by Phase 6.

## Blocking Issues For Phase 6

- Missing Stage 6 run contract with run id, stage ids, statuses, retries, artifacts, timings, and safe logs.
- Missing end-to-end orchestrator spanning Phase 1, Phase 2, Phase 3, Phase 4, and Phase 5.
- Missing Phase 5 render service and Phase 4 -> Phase 5 adapter.
- Missing artifact persistence strategy for Phase 1, Phase 2, Phase 3, render outputs, prompts, model raw responses, and retry attempts.
- Missing frontend request flow.
- Missing Supabase-specific integration, if Supabase is required beyond a PostgreSQL connection string.
- No git worktree was available at the audited path, so Phase 6 source-control workflow cannot be verified from this checkout.

## Safe Reuse Candidates

- `src/resume_optimizer/models.py` source truth models.
- `src/resume_optimizer/job_models.py` and `job_normalizers.py`.
- `src/resume_optimizer/ranking_service.py::build_phase2_ranking_artifacts`.
- `src/resume_optimizer/services/phase3_service.py::Phase3Service.run`.
- `backend/app/services/verification/orchestrator.py::VerificationOrchestrator.run`.
- `backend/app/schemas/verification.py` contracts.
- `backend/app/models/render_models.py` contracts.
- `backend/app/services/template_registry.py`.
- `backend/app/services/latex_mapper.py`.
- `backend/app/services/layout_manager.py`.
- `backend/app/services/document_assembler.py`.
- `backend/app/services/pdf_compiler.py`.
- `backend/app/services/render_diagnostics.py`.

## Unsafe Code That Must Be Wrapped Or Replaced

- Wrap `src/resume_optimizer/services/phase2_service.py::run_for_default_profile`; do not use hidden default profile loading in the main orchestrator.
- Wrap `src/resume_optimizer/ai_service.py::analyze_job_description`; preserve retry details and raw artifacts.
- Wrap `src/resume_optimizer/phase3_generation_service.py::generate_with_report`; classify model errors, validation errors, severe failures, and retries.
- Wrap `backend/app/services/pipeline_service.py::ResumePipelineService`; it is Phase 3+4 only and should not be treated as full Phase 6 orchestration.
- Replace or fix `backend/app/services/verification/orchestrator.py::_job_keywords` use of `preferred_requirements`.
- Wrap `backend/app/services/pdf_compiler.py::compile_tex_document`; make workspace/artifact cleanup, timeout, and artifact references explicit in Stage 5 artifacts.
- Do not edit `build/lib/**` as source.

## Minimal Readiness Validator

Phase 6 will reuse:

- Existing Pydantic contracts for Phase 0-5.
- Deterministic Phase 2 ranking artifacts.
- Phase 3 service result bundle.
- Phase 4 verification orchestrator and persistence repository.
- Phase 5 render primitives and LaTeX template.

Phase 6 will wrap:

- OpenAI-backed Phase 1 and Phase 3 calls.
- Existing `ResumePipelineService`, or more likely supersede it with a new full orchestrator while reusing its Phase 3/4 pieces.
- SQLAlchemy session/repository creation.
- PDF compilation and artifact paths.
- Local default profile loading.

Phase 6 must not touch yet:

- Product concept or resume optimization behavior.
- LaTeX template structure except through controlled placeholders.
- `build/lib/**` generated copies.
- Frontend code, because none exists in this checkout.
- Supabase-specific code, unless a concrete Supabase client/config is introduced.

## Implementation Recommendation

Use the least disruptive path: add a new Phase 6 orchestration layer that imports existing stage services and contracts rather than moving or renaming them.

Recommended sequence:

1. Add Phase 6 contracts for `PipelineRun`, `StageRun`, `ArtifactRef`, retry metadata, and stage statuses.
2. Fix the Phase 4 keyword mismatch (`preferred_requirements` -> `nice_to_have_requirements`) with a focused regression test.
3. Add a Stage 5 adapter from `Phase4RenderingOutput` plus `MasterProfile` to `RenderJobInput`.
4. Add a Phase 5 render service that composes validation, layout, mapping, template assembly, compilation, and diagnostics.
5. Add a full Phase 6 backend service that executes Phase 1 -> Phase 5 with injected stage clients/repositories and deterministic test fakes.
6. Add one full-orchestration API route after service-level tests exist.
7. Update README only after the new route and tests exist.

## Exact Files Phase 6 Should Modify

- `backend/app/services/verification/orchestrator.py`
- `backend/app/tests/unit/test_deterministic_validators.py` or a new focused verification unit test file
- `src/resume_optimizer/app.py`
- `backend/app/api/routes/resume.py`
- `README.md`
- `pyproject.toml` only if new test/runtime dependencies are required
- `backend/app/db/models/__init__.py` only if new Phase 6 persistence models are added
- `backend/app/db/repositories/__init__.py` only if new repositories are added

## Exact Files Phase 6 Should Create

- `backend/app/services/orchestration/__init__.py`
- `backend/app/services/orchestration/contracts.py`
- `backend/app/services/orchestration/artifacts.py`
- `backend/app/services/orchestration/retry_policy.py`
- `backend/app/services/orchestration/stage_logger.py`
- `backend/app/services/orchestration/resume_orchestrator.py`
- `backend/app/services/render_service.py`
- `backend/app/services/render_input_adapter.py`
- `backend/app/schemas/orchestration.py`
- `backend/app/api/routes/orchestration.py`
- `backend/app/db/models/pipeline_run.py` if durable Phase 6 runs are required
- `backend/app/db/models/pipeline_stage_run.py` if durable stage runs are required
- `backend/app/db/models/pipeline_artifact.py` if durable artifact references are required
- `backend/app/db/repositories/orchestration_repository.py` if durable Phase 6 runs are required
- `backend/alembic/versions/<new_revision>_create_phase6_orchestration_tables.py` if durable Phase 6 runs are required
- `backend/app/tests/unit/test_phase6_contracts.py`
- `backend/app/tests/unit/test_render_input_adapter.py`
- `backend/app/tests/unit/test_render_service.py`
- `backend/app/tests/unit/test_resume_orchestrator.py`
- `backend/app/tests/integration/test_phase6_orchestration_pipeline.py`

## Current Stage Readiness

| Stage | Status | Phase 6 action |
| --- | --- | --- |
| Phase 0 truth model | Complete for local file mode | Reuse and wrap profile source |
| Phase 1 job understanding | Partially complete | Wrap AI call, raw artifacts, retries |
| Phase 2 ranking/selection | Complete locally, partial persistence | Reuse artifact builder, avoid legacy-only endpoint |
| Phase 3 generation | Complete service, partial API artifact exposure | Reuse service result, wrap retries/failures |
| Phase 4 verification | Partially complete | Reuse orchestrator, fix keyword mismatch, wrap persistence |
| Phase 5 rendering/PDF | Partially complete | Add adapter and render service |
| Backend APIs | Partially complete | Add full orchestration route after service tests |
| Frontend flow | Missing | Do not assume present |
| Supabase/PostgreSQL | Partially complete | Decide whether SQLAlchemy `DATABASE_URL` is sufficient or add Supabase-specific client |

