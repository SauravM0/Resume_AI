"""Compatibility-friendly Phase 6 verification evaluation entrypoint."""

from __future__ import annotations

from backend.app.scripts.run_phase4_eval import (
    DEFAULT_FIXTURE_DIR,
    EvalCase,
    EvalCaseResult,
    load_eval_cases,
    main,
    render_summary,
    run_eval_cases,
    summarize_results,
)

__all__ = [
    "DEFAULT_FIXTURE_DIR",
    "EvalCase",
    "EvalCaseResult",
    "load_eval_cases",
    "main",
    "render_summary",
    "run_eval_cases",
    "summarize_results",
]


if __name__ == "__main__":
    raise SystemExit(main())
