# Phase 7 Evaluation Foundation

## Purpose

Phase 7 establishes the repository foundation for real regression and red-team evaluation of the resume-generation pipeline. The goal is to make later evaluation work use the actual backend stage implementations, persist inspectable artifacts for every stage, and emit CI-friendly summaries without changing existing product routes or business logic.

This phase adds the real evaluation runner, typed schemas, fixture/output directories, CLI entrypoints, and report artifacts without changing product routes or unrelated business logic.

## Real Pipeline Vs Fake Pipeline

The repository already contains fake or deterministic harnesses for earlier phases, including the Phase 6 orchestration fixture harness in `backend/tests/orchestration/pipeline_harness.py`. Those harnesses are useful for stable tests, but they do not execute the real pipeline path.

Phase 7 draws a strict line:

- Fake pipeline: uses fixture-only stage behavior, synthetic stage outputs, or deterministic test doubles.
- Real pipeline: drives the existing backend orchestration stack and stage adapters so evaluation reflects actual parsing, ranking, generation, verification, rendering, and artifact persistence behavior.

The new `backend.app.evaluation` package now contains the concrete runner that calls the real orchestrator rather than extending the fake registry approach.

## Stage Artifact Model

Each evaluation run should persist a stage-by-stage artifact trail, not just a final pass/fail result.

The Phase 7 implementation introduces:

- `ArtifactManifestEntry`: one durable artifact emitted by one stage for one evaluation run
- `ArtifactManifest`: the full manifest for a run/case pair
- `ArtifactStore`: the contract that persists stage artifacts and returns the manifest
- `summary.md`: a human-readable per-run synopsis

The model is designed to sit beside the existing orchestration artifact types:

- Phase 6 keeps pipeline artifact references in `backend.app.orchestration.types.PipelineArtifactRef`
- Phase 7 adds evaluation-specific manifest entries that record where inspectable artifacts were written for regression analysis and report generation

This means later implementations can preserve the existing runtime artifact logic while layering evaluation-specific persistence and reporting on top.

Each persisted artifact now includes stable metadata:

- timestamp
- stage name
- schema version
- case id
- run id

Structured payloads are stored as pretty-printed JSON envelopes. Non-JSON payloads such as logs or PDFs receive deterministic metadata sidecars.

## Regression Pack Types

Phase 7 reserves four stable fixture packs:

- `jd_parse`: job-description parsing regression cases
- `selection`: ranking and evidence-selection regression cases
- `end_to_end`: full real pipeline evaluation cases
- `red_team`: adversarial, abuse, and failure-oriented cases

These map to `EvaluationPackType` in `backend.app.evaluation.enums`.

The repository fixture roots are:

- `fixtures/evaluation/jd_parse/`
- `fixtures/evaluation/selection/`
- `fixtures/evaluation/end_to_end/`
- `fixtures/evaluation/red_team/`

Future loaders should treat those directories as canonical and stable.

## Scoring And Report Outputs

The Phase 7 foundation adds typed outputs for both scoring and reporting:

- `ScoringSummary`: scorer name, outcome, overall score, metric list, and findings
- `RunSummary`: run status, pipeline status, timing, artifact manifest location, and report location

The split is intentional:

- `EvaluationActualOutputs` captures what the real pipeline did
- `ScoringSummary` captures how the result compares to expectations
- `RunSummary` captures execution/report metadata suitable for CI and automation

`EvaluationReportWriter` is defined as a separate contract so later phases can emit JSON, markdown, or CI-oriented summaries without changing runner or scorer contracts.

## Package Layout

The new backend package is:

```text
backend/app/evaluation/
  __init__.py
  README.md
  artifact_models.py
  case_models.py
  contracts.py
  enums.py
  paths.py
  report_models.py
```

This package is intentionally small and typed. It does not replace the existing orchestration layer. It defines the seam where evaluation code will attach to it.

## How It Plugs Into The Existing Architecture

The current backend flow already had the right components for a real evaluation path:

1. `backend.app.orchestration` defines the stage order, stage contracts, runner recorder, and artifact references.
2. Existing adapters under `backend.app.orchestration.adapters` wrap live modules from `resume_optimizer`.
3. Existing scripts and tests already use fixture-based eval entrypoints for narrow slices.

Phase 7 plugs in above that stack:

1. `JsonEvaluationCaseLoader` loads a regression or red-team case from `fixtures/evaluation/...`.
2. `OrchestratedRealPipelineRunner` maps the case input into the existing orchestration flow and captures `EvaluationActualOutputs`.
3. `LocalFileArtifactStore` writes stage artifacts into `outputs/evaluation_runs/...` and emits an `ArtifactManifest`.
4. `BasicExpectationScorer` compares actual outputs against `EvaluationExpectedOutputs`.
5. `JsonEvaluationReportWriter` emits durable per-run summaries for CI or local inspection.

This keeps product routes and orchestration APIs intact while adding a new evaluation layer that depends on them.

## Real Runner Behavior

The real runner supports:

- full runs
- stop after parse
- stop after selection
- stop after verification
- explicit `use_live_llm`, `enable_render`, `persist_artifacts`, and `fail_fast` flags
- deterministic run ids
- per-stage artifact persistence and run manifests
- dry-run mode when `use_live_llm=false`

Dry-run is explicit. It does not call fake stages. It runs the deterministic prefix that is still valid, then marks downstream stages as skipped with a concrete reason.

If `use_live_llm=true` and required dependencies are missing, the runner fails clearly and records the missing dependency in the run manifest.

## Non-Goals In This Phase

- No changes to FastAPI routes
- No changes to frontend code
- No new product features
- No broad refactors of orchestration or generation services

That boundary is deliberate so later phases can add execution logic without having to rename or redesign the foundation introduced here.
