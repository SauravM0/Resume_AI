# Evaluation Report `red.overfull.profile`

## Run
- Scenario: `overfull_profile`
- Description: Large strong profiles should not collapse into a single dominant story when breadth is available.
- Pack Type: `red_team`
- Run Status: `passed`
- Pipeline Status: `pending`
- Outcome: `fail`
- Structured Score: `0.33`

## Red-Team Intent
- Bad Behavior To Catch: Letting one current experience crowd out richer breadth from supporting projects and adjacent backend history.
- Acceptable Fallback: Preserve breadth across recent experience and one relevant project without collapsing into one source.

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
- Bad behavior target: Letting one current experience crowd out richer breadth from supporting projects and adjacent backend history.
- Acceptable fallback: Preserve breadth across recent experience and one relevant project without collapsing into one source.
- Check whether the multi-region project survives when strong current experience already exists.

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
