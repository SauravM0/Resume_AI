# Evaluation Report `case.end_to_end.backend_example`

## Run
- Scenario: `backend_resume_generation`
- Description: Example end-to-end quality evaluation for a backend-targeted final resume.
- Pack Type: `end_to_end`
- Run Status: `passed`
- Pipeline Status: `pending`
- Outcome: `fail`
- Structured Score: `0.00`

## Structured Checks
- `pipeline_status_match`: `REVIEW` score=`0.00` expected=succeeded, actual=pending
- `required_artifacts_present`: `REVIEW` score=`0.00` required=2, present=3

## Reviewer Signals
- none

## Reviewer Comments
- none

## Findings
- expected=succeeded, actual=pending
- required=2, present=3

## Artifact Links
- none

## Persisted Artifacts
- `ingest_job_description` `raw_job_description` `stages/ingest_job_description/raw_job_description.json`
- `load_source_profile` `source_profile` `stages/load_source_profile/source_profile.json`
- `normalize_source_data` `normalized_profile` `stages/normalize_source_data/normalized_profile.json`
