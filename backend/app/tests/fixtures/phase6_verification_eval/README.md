# Phase 6 Verification Evaluation Fixtures

This directory contains the maintained regression fixture set for the real Phase 6 verification path.

Use the preferred entrypoint:

```bash
PYTHONPATH=.:src python3 backend/app/scripts/run_phase6_eval.py
```

The legacy alias still works for backwards compatibility:

```bash
PYTHONPATH=.:src python3 backend/app/scripts/run_phase4_eval.py
```

Run the regression tests:

```bash
PYTHONPATH=.:src pytest -q backend/app/tests/integration/test_phase4_eval_suite.py
```

Fixture fields are intentionally explicit:

- `category`: high-signal scenario label used by regression tests
- `item_type`: `experience_bullet`, `project_bullet`, `summary`, or `skill_statement`
- `source_item_id` / `source_bullet_ids`: provenance-backed evidence used by Phase 6
- `generated_text`: the generated output under verification
- `semantic_mode`: `pass`, `weak_support`, or `degraded`
- `semantic_fallback_behavior` / `semantic_strict_mode`: degraded-mode policy inputs
- `expected_*`: asserted item status, run status, gate decision, fallback action, repair outcome, and audit state

Keep this suite small and realistic. Add only cases that represent actual false-claim patterns, safe outputs, or policy edge cases.
