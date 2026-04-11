# Pipeline Profiling

The profiling layer is a developer-facing measurement tool for the resume pipeline. It does not change pipeline logic. It runs sample cases, collects stage timings and size indicators, and produces a bottleneck report for future optimization work.

## What It Measures

For each run:

- total latency
- slowest stage
- stage latency breakdown
- retry count
- fallback count
- output artifact size indicators
- failure type distribution

For each batch:

- average total latency
- slowest stage by average latency
- per-stage p50, p95, p99 style summaries through the profiling aggregates
- bottleneck flags across the batch

## Profiling Modes

- `deterministic`
  Uses the Phase 6 regression harness in `backend/tests/orchestration/pipeline_harness.py`.
  This is stable and repeatable locally.
- `real-dry-run`
  Uses the real evaluation runner with live model calls disabled.
- `real-live`
  Uses the real evaluation runner with live model calls enabled.

## Running The Profiler

Deterministic batch:

```bash
python3 -m backend.app.profiling.cli run \
  --mode deterministic \
  --cases backend/tests/fixtures/pipeline_cases/regression_cases.json \
  --limit 5
```

Save a JSON report:

```bash
python3 -m backend.app.profiling.cli run \
  --mode deterministic \
  --output outputs/profiling/deterministic_report.json \
  --json
```

Real dry-run sample case:

```bash
python3 -m backend.app.profiling.cli run \
  --mode real-dry-run \
  --case-file fixtures/evaluation/end_to_end/example_case.json \
  --output outputs/profiling/real_dry_run.json \
  --json
```

Compare two saved reports:

```bash
python3 -m backend.app.profiling.cli compare \
  --left outputs/profiling/baseline.json \
  --right outputs/profiling/candidate.json
```

## Current Bottleneck Thresholds

Current default thresholds are defined in `backend/app/profiling/report.py`.

- stage target latency thresholds:
  - `parse_job_description`: `1500 ms`
  - `generate_structured_content`: `2000 ms`
  - `verify_generated_content`: `1200 ms`
  - `compile_pdf`: `1200 ms`
  - other stages use smaller stage-specific limits
- unstable latency variance:
  - coefficient of variation greater than `0.5` with at least 3 runs
- excessive retries:
  - retry rate above `0.2`
- excessive fallback usage:
  - fallback rate above `0.1`
- compile time anomaly:
  - `compile_pdf` above `3000 ms`
- large output artifact:
  - any artifact above `500000 bytes`
- large total output:
  - total artifacts above `1500000 bytes`

## Reading The Report

- Start with `slowest_stage_by_avg` to find the main batch bottleneck.
- Check each run’s `slowest_stage` to see whether the same stage dominates repeatedly.
- Use retry and fallback counts to separate latency problems from reliability problems.
- Large output flags often point to oversized PDFs, logs, or intermediate artifacts that can distort runtime.
- Variance flags matter even when averages look acceptable. A stage with unstable latency is a likely future incident source.

## Intended Use

This layer is measurement-first. It is meant to support later optimization work, not to optimize anything directly in this task.
