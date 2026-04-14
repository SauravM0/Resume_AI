Phase 3 gold evaluation fixtures

Run locally:

```bash
PYTHONPATH=src:. python3 scripts/run_phase3_eval.py --today 2026-04-08
```

JSON output:

```bash
PYTHONPATH=src:. python3 scripts/run_phase3_eval.py --json --today 2026-04-08
```

Fixture format:

- `eval_cases.json` contains the gold cases.
- Each case references a realistic profile fixture by `profile_fixture`.
- Each case embeds a normalized job analysis plus expected:
  - `selected_experiences`
  - `selected_projects`
  - `highlighted_skills`
  - important `omitted_items`

To add a case:

1. Add or reuse a profile fixture in [phase2_candidate_profiles.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/fixtures/phase2_candidate_profiles.py).
2. Add a new case entry to `eval_cases.json`.
3. Run the Phase 3 eval script and update tests if needed.
