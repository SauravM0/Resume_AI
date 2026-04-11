# Phase 7 Workflow Summary

- Generated At: `2026-04-11T11:42:06.572563+00:00`
- Mode: `local-full`
- Command: `run_selection_eval`
- Pass/Fail/Skip: `1/0/0`

## Checks
- `selection` status=`pass` confidence=`quality` selection quality gate passed: absolute quality and regression guardrail both passed
  artifact: summary_json=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_selection_eval/local-full/selection/selection_summary.json
  artifact: summary_md=/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/outputs/phase7_workflow/run_selection_eval/local-full/selection/selection_summary.md

## Confidence Model
- `quality` means the result contributes to product-confidence gating.
- In `ci-safe`, the `selection` check passes only when both absolute quality and regression guardrails pass; stable bad behavior is still a failure.
- `smoke` means the path exercised artifact/log generation only and does not prove live quality.
- `skip` means the pack was not run in this mode, typically because live model access was intentionally disabled.
