# Evaluation Run `eval.red.unsupported.leadership.d76a213e6df2`

- Case ID: `red.unsupported.leadership`
- Execution Mode: `dry_run`
- Run Status: `passed`
- Pipeline Status: `pending`
- Artifact Count: `3`

## Stages
- `load_source_profile`: `succeeded` artifacts=`1` load_source_profile completed
- `normalize_source_data`: `succeeded` artifacts=`1` normalize_source_data completed
- `ingest_job_description`: `succeeded` artifacts=`1` ingest_job_description completed
- `parse_job_description`: `skipped` artifacts=`0` dry-run stopped before live LLM stages
- `rank_select_evidence`: `skipped` artifacts=`0` dry-run stopped before live LLM stages
- `generate_structured_content`: `skipped` artifacts=`0` dry-run stopped before live LLM stages
- `verify_generated_content`: `skipped` artifacts=`0` dry-run stopped before live LLM stages
- `render_deterministic_latex`: `skipped` artifacts=`0` dry-run stopped before live LLM stages
- `compile_pdf`: `skipped` artifacts=`0` dry-run stopped before live LLM stages

## Artifacts
- `ingest_job_description` `raw_job_description` [stages/ingest_job_description/raw_job_description.json]
- `load_source_profile` `source_profile` [stages/load_source_profile/source_profile.json]
- `normalize_source_data` `normalized_profile` [stages/normalize_source_data/normalized_profile.json]
