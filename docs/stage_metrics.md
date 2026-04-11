# Stage Metrics

Stage metrics are recorded as one JSON object per completed stage in:

- `data/metrics/stage_metrics.jsonl`
- Override with `PIPELINE_STAGE_METRICS_PATH`

Each record stores only safe operational metadata:

- `request_id`
- `run_id`
- `stage_name`
- `started_at`
- `ended_at`
- `duration_ms`
- `success`
- `failure_type`
- `retry_count`
- `fallback_used`
- `output_metadata`

Raw job descriptions, raw resumes, generated summaries, and full source profile payloads are intentionally not stored. Metrics output metadata is limited to safe IDs, counts, booleans, statuses, and redacted placeholders for sensitive keys.

## Instrumented stages

- `request_validation`
- `load_source_profile`
- `normalize_source_data`
- `ingest_job_description`
- `parse_job_description`
- `rank_select_evidence`
- `section_planning`
- `generate_structured_content`
- `verify_generated_content`
- `render_deterministic_latex`
- `compile_pdf`
- `persist_artifacts`
- `response_packaging`

## Inspecting Metrics

Use the developer-only CLI:

```bash
python3 -m backend.app.metrics.cli --limit 200
```

This prints aggregate summaries for recent stage records, including:

- `p50_duration_ms`, `p95_duration_ms`, `p99_duration_ms` by stage
- `failure_rate` by stage
- `retry_rate` by stage
- `fallback_rate` by stage
- request-level latency percentiles

## Interpreting The Numbers

- `p50` is the median stage latency.
- `p95` shows the slow tail that affects real user-perceived slowness and bottlenecks.
- `p99` highlights rare worst-case outliers.
- `failure_rate` shows how often a stage ends unsuccessfully.
- `retry_rate` shows how often a stage needed at least one retry before the final outcome.
- `fallback_rate` shows how often a fallback path or fallback decision was involved.

High `p95` with low failure rate usually points to performance bottlenecks. High fallback or retry rates usually point to reliability or input-quality issues even when the request still finishes.

## Example Record

```json
{
  "request_id": "req.4e0a0c9d7c8c4d6abef2f0b9c6d52e73",
  "run_id": "pipeline.4fdb6c87",
  "stage_name": "parse_job_description",
  "started_at": "2026-04-10T12:00:00Z",
  "ended_at": "2026-04-10T12:00:01Z",
  "duration_ms": 1000,
  "success": true,
  "failure_type": null,
  "retry_count": 0,
  "fallback_used": false,
  "output_metadata": {
    "output_type": "ParseJobDescriptionOutput",
    "field_count": 7
  }
}
```
