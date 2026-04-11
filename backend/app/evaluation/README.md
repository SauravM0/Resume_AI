# Phase 7 Evaluation

This package now contains the real evaluation harness and the typed contracts it builds on.

The runner executes the live backend orchestration path. It does not use the fake orchestration registry from `backend/tests/orchestration`.

## Included

- `contracts.py`: Protocol contracts for the real runner, artifact store, case loader, scorer, and report writer
- `case_models.py`: evaluation case metadata, expected outputs, case definitions, and actual outputs
- `artifact_models.py`: persisted stage artifact manifest models
- `runtime_models.py`: run config, dependency checks, stage records, and run manifests
- `report_models.py`: CI-friendly run and scoring summaries
- `runner.py`: the real orchestrator-backed evaluation runner
- `storage.py`: local filesystem artifact persistence
- `loader.py`: JSON case loading
- `scorer.py`: baseline expectation scoring
- `report_writer.py`: JSON report output
- `paths.py`: canonical repository fixture and output directories

## Persisted Run Layout

Each persisted run now writes:

- `manifest.json`: machine-readable artifact inventory
- `run_manifest.json`: execution metadata, dependency checks, and stage outcomes
- `summary.md`: human-readable run summary
- `stages/<stage_name>/<artifact_name>`: artifact payloads
- `stages/<stage_name>/<artifact_name>.metadata.json`: per-artifact metadata sidecars for text and binary inspection

Structured JSON artifacts are wrapped as:

- `artifact_metadata`
- `payload`

## CLI

Run one case:

```bash
PYTHONPATH=.:src python3 backend/app/scripts/run_real_evaluation.py \
  --case-file fixtures/evaluation/end_to_end/example_case.json \
  --use-live-llm true \
  --enable-render false \
  --stop-after verification
```

Run a dry-run without live model calls:

```bash
PYTHONPATH=.:src python3 backend/app/scripts/run_real_evaluation.py \
  --case-file fixtures/evaluation/end_to_end/example_case.json \
  --use-live-llm false \
  --enable-render false
```

Workflow entrypoint:

```bash
PYTHONPATH=.:src python3 scripts/run_phase7.py run_all_phase7 --mode ci-safe
```

Available workflow commands:

- `run_jd_eval`
- `run_selection_eval`
- `run_e2e_eval`
- `run_red_team_eval`
- `run_all_phase7`

Workflow modes:

- `ci-safe`: selection quality is confidence-bearing; end-to-end and red-team run as smoke only; jd-parse is skipped
- `local-full`: same live-access split as `ci-safe`, but intended for local artifact review
- `live`: all supported packs run as real confidence-bearing evaluation

Do not treat `ci-safe` or `local-full` green runs as proof of live resume quality. In those modes:

- `selection` is the only quality-gating Phase 7 pack
- `end_to_end` and `red_team` only prove that artifact/log generation still works through the real runner
- `jd_parse` is intentionally skipped because it depends on live parsing

## Thresholds And CI

Phase 7 CI thresholds are stored in:

- `fixtures/evaluation/phase7_thresholds.json`

Current default behavior:

- CI-safe gating uses deterministic selection quality gating with two requirements:
  - an absolute quality pass, which rejects obviously bad selection outcomes even if they are stable
  - a regression guardrail pass, which catches backsliding from the checked-in baseline
- live-only packs have explicit live thresholds but are not run by default in CI

This is intentional. The repository should not confuse dry-run smoke success with live quality confidence.

For `selection`, a general workflow pass now means both conditions held. A run fails the workflow if, for example:

- all cases fail
- pathology rate is severe
- required-project cases get zero project recall
- average selected relevance is too low

This prevents Phase 7 from normalizing a bad but stable selection baseline.

## Local Commands

```bash
make run_selection_eval PHASE7_MODE=local-full
make run_all_phase7 PHASE7_MODE=local-full
make run_jd_eval PHASE7_MODE=live
make run_e2e_eval PHASE7_MODE=live PHASE7_RENDER=true
make run_red_team_eval PHASE7_MODE=live
```

## CI Command

```bash
make run_all_phase7 PHASE7_MODE=ci-safe
```

## Artifact Inspection

Workflow artifacts are written under:

- `outputs/phase7_workflow/<command>/<mode>/`

Useful files:

- `suite_summary.md`
- `suite_summary.json`
- deterministic pack summaries such as `selection/selection_summary.md`
- backend pack outputs such as `end_to_end/aggregate_report.json`
- backend command logs: `command.stdout.log` and `command.stderr.log`

## Authoring New Cases

Case authoring remains fixture-first:

- `fixtures/evaluation/jd_parse/`
- `fixtures/evaluation/selection/`
- `fixtures/evaluation/end_to_end/`
- `fixtures/evaluation/red_team/`

Guidance:

- use `selection` for deterministic ranking/selection quality
- use `end_to_end` for final structured resume quality
- use `red_team` for brittle or unsafe behavior
- for red-team cases, always define:
  - `bad_behavior_to_catch`
  - `acceptable_fallback_behavior`
  - reviewer guidance that tells the reviewer what unsafe behavior to inspect

## Separation From Fake Harnesses

The real runner lives in `backend.app.evaluation.runner.OrchestratedRealPipelineRunner`.

The orchestration-only fake harness remains in `backend/tests/orchestration/pipeline_harness.py`.

They are separate by construction:

- the real runner imports `ResumeGenerationOrchestrator` and live stage adapters from `backend.app.orchestration`
- the fake harness imports `FakePipelineStageRegistry` from test code
- the real runner fails when live dependencies are missing unless `use_live_llm=false` was explicitly requested
- the real runner never substitutes synthetic stage outputs

## Loading Saved Runs

Use:

- `load_saved_evaluation_run(...)`
- `render_loaded_run_summary(...)`

to reconstruct a previously persisted evaluation run without re-executing the pipeline.

Fixture packs live under:

- `fixtures/evaluation/jd_parse/`
- `fixtures/evaluation/selection/`
- `fixtures/evaluation/end_to_end/`
- `fixtures/evaluation/red_team/`

Run outputs live under:

- `outputs/evaluation_runs/`
