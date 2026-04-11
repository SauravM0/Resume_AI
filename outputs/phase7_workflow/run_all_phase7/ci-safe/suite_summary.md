# Phase 7 Workflow Summary

- Generated At: `2026-04-10T07:59:01.607054+00:00`
- Mode: `ci-safe`
- Command: `run_all_phase7`
- Pass/Fail/Skip: `3/0/1`

## Checks
- `jd_parse` status=`skip` confidence=`skip` jd_parse evaluation requires live model access and is skipped outside live mode.
- `selection` status=`pass` confidence=`quality` selection regression guardrail passed
  artifact: summary_json=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/selection/selection_summary.json
  artifact: summary_md=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/selection/selection_summary.md
- `end_to_end` status=`pass` confidence=`smoke` end_to_end dry-run smoke completed; artifacts persisted but result is not confidence-bearing.
  artifact: aggregate_markdown=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/end_to_end/aggregate_summary.md
  artifact: aggregate_report=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/end_to_end/aggregate_report.json
  artifact: stderr=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/end_to_end/command.stderr.log
  artifact: stdout=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/end_to_end/command.stdout.log
- `red_team` status=`pass` confidence=`smoke` red_team dry-run smoke completed; artifacts persisted but result is not confidence-bearing.
  artifact: aggregate_markdown=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/red_team/aggregate_summary.md
  artifact: aggregate_report=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/red_team/aggregate_report.json
  artifact: stderr=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/red_team/command.stderr.log
  artifact: stdout=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_all_phase7/ci-safe/red_team/command.stdout.log

## Confidence Model
- `quality` means the result contributes to product-confidence gating.
- `smoke` means the path exercised artifact/log generation only and does not prove live quality.
- `skip` means the pack was not run in this mode, typically because live model access was intentionally disabled.
