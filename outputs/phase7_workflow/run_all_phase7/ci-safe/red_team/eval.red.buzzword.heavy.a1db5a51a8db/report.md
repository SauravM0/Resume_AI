# Evaluation Report `red.buzzword.heavy`

## Run
- Scenario: `buzzword_heavy_job_description`
- Description: Buzzword soup should not trigger irrelevant keyword chasing.
- Pack Type: `red_team`
- Run Status: `passed`
- Pipeline Status: `pending`
- Outcome: `fail`
- Structured Score: `0.33`

## Red-Team Intent
- Bad Behavior To Catch: Chasing stray buzzwords and pulling in irrelevant frontend or design-system evidence to match noise.
- Acceptable Fallback: Anchor on the strongest real evidence, omit noisy mismatches, and avoid keyword-stuffed summary language.

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
- Bad behavior target: Chasing stray buzzwords and pulling in irrelevant frontend or design-system evidence to match noise.
- Acceptable fallback: Anchor on the strongest real evidence, omit noisy mismatches, and avoid keyword-stuffed summary language.
- Inspect whether the final output stays grounded in actual backend/platform evidence instead of vague buzzword matching.

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
