Phase 2 evaluation fixtures

Run locally from the repository root:

```bash
PYTHONPATH=src python3 scripts/run_phase2_eval.py --today 2026-04-06
```

Emit JSON for CI or tooling:

```bash
PYTHONPATH=src python3 scripts/run_phase2_eval.py --json --today 2026-04-06
```

Fixture structure:

- `eval_cases.json`: manifest of Phase 2 evaluation cases
- `profiles/`: source profile fixtures loaded by the real Phase 2 service path
- `jobs/`: normalized job-analysis fixtures for each case

Each case in `eval_cases.json` must define:

- `case_id`
- `description`
- `profile_fixture`
- `job_analysis_fixture`
- `expectation`

Validation is strict and runs before evaluation starts. The harness fails early if:

- the fixture root is missing
- `eval_cases.json` is missing or malformed
- a referenced profile file is missing or invalid
- a referenced job-analysis file is missing or invalid
- a requested `--case` id does not exist

To add a new case:

1. Add a profile JSON under `profiles/` or reuse an existing one.
2. Add a normalized job-analysis JSON under `jobs/`.
3. Add the case entry to `eval_cases.json` with explicit expectations.
4. Run `PYTHONPATH=src python3 scripts/run_phase2_eval.py --today 2026-04-06`.
5. Tighten expectations only after verifying the real output is acceptable quality.
