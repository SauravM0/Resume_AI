# ResumeAI codebase audit

## What is actively used right now

- ``start_backend.py` → `backend.app.main:app``
- ``/api/generate-resume` → `backend.app.orchestration.orchestrator.ResumeGenerationOrchestrator``
- `Stages: load profile → normalize profile → ingest JD → parse JD → rank/select evidence → generate structured content → verify → render LaTeX → compile PDF → persist artifacts`
- `Frontend active path: `frontend/src/App.tsx` → `pages/ResumeGenerationPage.tsx` + `hooks/useResumeGeneration.ts` + `services/generateResume.ts``
- `Master profile editing path exists and is active: `frontend/src/pages/MasterProfilePage.tsx` + `backend/app/api/routes/master_profile.py``

## High-confidence cleanup candidates

These files are **not imported anywhere in the repo** based on static analysis, and I did not find a config/runtime path that makes them active.

- `backend/alembic/versions/20260407_0001_create_verification_tables.py`
- `backend/alembic/versions/20260407_0002_create_render_jobs.py`
- `backend/alembic/versions/20260407_0003_create_phase6_orchestration_tables.py`
- `backend/app/config/runtime_summary.py`
- `backend/app/privacy/redaction.py`
- `src/resume_optimizer/ai_provider.py`
- `src/resume_optimizer/evaluation/jd_parse_runner.py`
- `src/resume_optimizer/evaluation/selection_runner.py`
- `src/resume_optimizer/evidence_pool.py`
- `src/resume_optimizer/normalization/engine.py`
- `src/resume_optimizer/phase1_combined_eval.py`

## Legacy / parallel API path that is not your real product runtime

These are not necessarily “dead,” but they are **not the main live path** used by `start_backend.py` + the frontend.

- `backend/app/api/routes/resume.py`
- `backend/app/services/pipeline_service.py`
- `src/resume_optimizer/app.py`

## Tooling / evaluation / documentation directories that are not part of the live product path

These folders may still be useful for QA, benchmarking, or historical notes, but they are **not required for the user-facing product runtime**.

- `docs/`
- `docs/internal/`
- `fixtures/`
- `for_ai_agent/`
- `scripts/`
- `backend/app/evaluation/`
- `backend/app/profiling/`
- `backend/app/phase8/`
- `backend/app/support/`

## Generated / bundled noise that should not live inside a clean source zip

- `**/__pycache__/`
- `**/*.pyc`
- `frontend/tsconfig.node.tsbuildinfo`
- `frontend/tsconfig.tsbuildinfo`
- `outputs/ (currently empty)`

Counts observed:
- `__pycache__` directories: 37
- `.pyc` files: 733

## Frontend files that are not part of the runtime product path

- `frontend/src/types/resume-generation.ts  — compatibility shim only`
- `frontend/src/utils/errorPresentation.ts  — compatibility shim only`
- `frontend/src/test/  — test-only`

## Important architecture findings

- `Job posting URL is accepted by the UI and backend schema, but the backend does not fetch or parse the URL content. The real parser only uses `job_description_text`.`
- `The active backend entrypoint is `backend.app.main`, but there is also an older app at `src/resume_optimizer/app.py`. This creates architecture confusion and test drift.`
- `There are two resume-generation APIs: `/api/generate-resume` (active pipeline) and `/api/generate-resume-with-verification` (older verification route, not used by the frontend).`
- ``backend.app.main` includes the artifacts router twice.`
- `README is outdated: it says frontend is not included, but a substantial frontend exists.`
- `The product currently generates PDF/LaTeX/JSON artifacts, but the “JD link → fetch → analyze → assemble perfect ATS code-format resume preview” workflow is only partially implemented.`

## Recommended cleanup buckets

### Delete now
- `.git/` from distributed project zips
- all `__pycache__/` and `*.pyc`
- `frontend/*.tsbuildinfo`
- `outputs/` if you are not intentionally shipping generated artifacts
- the 11 high-confidence unused files listed above

### Move to `archive/` or `research/` first
- `src/resume_optimizer/app.py`
- `backend/app/api/routes/resume.py`
- `backend/app/services/pipeline_service.py`
- `backend/app/evaluation/`
- `backend/app/profiling/`
- `backend/app/phase8/`
- `backend/app/support/`
- `scripts/`
- `fixtures/`
- `for_ai_agent/`
- `docs/internal/`

### Keep, but reorganize
- `backend/app/orchestration/`
- `backend/app/api/routes/generate_resume.py`
- `backend/app/api/routes/master_profile.py`
- `backend/app/api/routes/pipeline_runs.py`
- `backend/app/api/routes/progress_stream.py`
- `backend/app/api/routes/artifacts.py`
- `backend/app/services/` files used by render/profile/template flow
- `src/resume_optimizer/` modules actually pulled by the active orchestration path
- `frontend/src/` runtime files

## Product gap vs your target workflow

### Your desired workflow
1. User pastes JD text **or** JD link  
2. System extracts keywords and role needs  
3. System reads master profile  
4. System selects best experience / projects / certifications / summary  
5. System assembles a one-page or two-page ATS resume  
6. System shows it in code-like ATS format  
7. User downloads and uses it for applications  

### What is implemented today
- JD text input: **yes**
- JD URL input field: **yes in UI/schema, but no real fetch/parse pipeline**
- Master profile input/editing: **yes**
- Evidence ranking/selection from master profile: **yes**
- Structured resume generation: **yes**
- Verification stage: **yes**
- Deterministic LaTeX + PDF compile: **yes**
- Artifact download: **yes**
- Clean “ATS code-format live resume editor/preview” UX: **partial**
- Real “JD link ingestion/scraping” path: **not implemented**
- Clean single architecture with no parallel legacy app: **not yet**

## What I would do next as senior developer + PM

1. Freeze one official runtime path:
   - backend entrypoint = `backend.app.main`
   - one generation API = `/api/generate-resume`
   - one frontend flow = `ResumeGenerationPage`

2. Create three repo zones:
   - `apps/backend`
   - `apps/frontend`
   - `packages/resume_core` (the reusable `resume_optimizer` logic)

3. Move non-product material out:
   - `archive/legacy_api`
   - `archive/eval_harness`
   - `archive/docs_internal`

4. Implement the missing product step:
   - a real JD ingestion service for URL fetch/extract/clean/fallback-to-manual-text

5. Redesign the user-facing resume output:
   - “Generated ATS Resume”
   - sections locked to ATS schema
   - one-page / two-page mode
   - code-like structured preview + PDF export

6. Remove drift:
   - delete duplicate router registration
   - update README
   - remove unused migration stubs
   - remove dead compatibility shims after final search

