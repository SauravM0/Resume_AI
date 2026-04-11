Phase 1 gold evaluation fixtures

Run locally:

```bash
PYTHONPATH=src:. python3 scripts/run_phase1_eval.py
```

JSON output:

```bash
PYTHONPATH=src:. python3 scripts/run_phase1_eval.py --json
```

Fixture format:

- `eval_cases.json` contains realistic JD fixtures and gold annotations.
- Each case includes:
  - raw JD text
  - tags for coverage tracking
  - gold expectations for:
    - `job_title`
    - `functional_role_family`
    - `organizational_role_mode`
    - `seniority_level`
    - `must_have_skills`
    - `nice_to_have_skills`
    - recruiter-intent summary
    - JD-quality expectation ranges
    - key responsibility clusters

Evaluation behavior:

- The suite runs the normal Phase 1 parser path with fixed fixture-backed LLM payloads.
- Exact matching is used where it is appropriate:
  - title
  - role family
  - org mode
  - seniority
- Tolerant matching is used where exact string equality would be brittle:
  - skill subset recall
  - responsibility-cluster semantic overlap
  - recruiter-intent summary token overlap
  - JD-quality score ranges

To add a case:

1. Add a new case entry to `eval_cases.json`.
2. Keep the raw JD realistic and grounded in explicit skills and requirements.
3. Run `scripts/run_phase1_eval.py`.
4. Tighten or adjust expectation ranges only when the parser behavior is defensible.
