# Evaluation Report `red.irrelevant.keyword.match`

## Run
- Scenario: `irrelevant_but_keyword_matching_content`
- Description: Old frontend keyword overlap should not contaminate a backend/platform resume.
- Pack Type: `red_team`
- Run Status: `passed`
- Pipeline Status: `pending`
- Outcome: `fail`
- Structured Score: `0.33`

## Red-Team Intent
- Bad Behavior To Catch: Using a stray UI keyword to justify old irrelevant frontend experience in a backend-focused resume.
- Acceptable Fallback: Keep the resume backend-heavy and omit old frontend-only items despite token overlap.

## Structured Checks
- `overclaim_risk`: `REVIEW` score=`0.00` verification output missing
- `weak_fit_honesty`: `PASS` score=`1.00` case does not require weak-fit caution
- `ranking_collapse`: `REVIEW` score=`0.00` distinct_selected_sources=0, weak_coverage_areas=none
- `one_source_dominance`: `REVIEW` score=`0.00` dominant_share=1.00, source_bullet_counts=none
- `irrelevant_keyword_chasing`: `PASS` score=`1.00` forbidden_selected=none, selected_sources=none
- `unsafe_summary_inflation`: `REVIEW` score=`0.00` missing summary

## Reviewer Signals
- `overclaim_risk`: `TRIGGERED` severity=`error` verification output missing
- `weak_fit_honesty`: `clear` severity=`warning`
- `ranking_collapse`: `TRIGGERED` severity=`warning` distinct_selected_sources=0, weak_coverage_areas=none
- `one_source_dominance`: `TRIGGERED` severity=`warning` dominant_share=1.00, source_bullet_counts=none
- `irrelevant_keyword_chasing`: `clear` severity=`error`
- `unsafe_summary_inflation`: `TRIGGERED` severity=`error` missing summary

## Reviewer Comments
- Bad behavior target: Using a stray UI keyword to justify old irrelevant frontend experience in a backend-focused resume.
- Acceptable fallback: Keep the resume backend-heavy and omit old frontend-only items despite token overlap.
- Verify that old jQuery and microsite work does not leak into the final resume.

## Findings
- verification output missing
- distinct_selected_sources=0, weak_coverage_areas=none
- dominant_share=1.00, source_bullet_counts=none
- missing summary

## Artifact Links
- none

## Persisted Artifacts
- `ingest_job_description` `raw_job_description` `stages/ingest_job_description/raw_job_description.json`
- `load_source_profile` `source_profile` `stages/load_source_profile/source_profile.json`
- `normalize_source_data` `normalized_profile` `stages/normalize_source_data/normalized_profile.json`
