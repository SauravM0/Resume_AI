# Phase 5 Regression Harness

This fixture pack drives the bounded Phase 5 generation regression harness.

Coverage:
- backend senior IC role
- frontend lead role
- devops/platform role
- data/analytics role
- engineering management role
- weak-match case
- profile with overlapping experiences
- profile with many projects
- profile with sparse certifications
- page-budget constrained case

What each case contributes to the baseline snapshot:
- parsed job output
- selected evidence
- section plan
- expected generation shape
- expected quality rules
- red flags
- actual summary, bullet, skills, assembly, and quality outputs

Run locally:

```bash
PYTHONPATH=src:. python3 scripts/run_phase5_eval.py
```

JSON output:

```bash
PYTHONPATH=src:. python3 scripts/run_phase5_eval.py --json
```

The checked-in baseline is in `baseline_snapshot.json`. It reflects the current branch honestly; it is not normalized to all-pass.
