from __future__ import annotations

from datetime import date
import json

from resume_optimizer.phase3_eval import (
    load_phase3_eval_manifest,
    phase3_eval_summary_json,
    render_phase3_eval_summary,
    run_phase3_eval,
)


def test_phase3_eval_manifest_exists_and_is_loadable() -> None:
    manifest = load_phase3_eval_manifest()

    assert len(manifest.cases) >= 3
    assert {case.case_id for case in manifest.cases} >= {
        "backend_strong_match",
        "backend_redundant_projects_hidden",
        "frontend_portfolio_projects_promoted",
    }


def test_phase3_eval_runner_executes_gold_cases_successfully() -> None:
    summary = run_phase3_eval(today=date(2026, 4, 8))

    assert summary.total_cases == 3
    assert summary.passed_cases == 3
    assert summary.failed_cases == 0
    assert summary.average_experience_precision == 1.0
    assert summary.average_experience_recall == 1.0
    assert summary.average_project_precision == 1.0
    assert summary.average_project_recall == 1.0
    assert summary.average_skill_precision == 1.0
    assert summary.average_skill_recall == 1.0
    assert summary.average_omission_correctness == 1.0


def test_phase3_eval_summary_renderers_expose_case_metrics() -> None:
    summary = run_phase3_eval(today=date(2026, 4, 8))

    text_output = render_phase3_eval_summary(summary)
    json_output = phase3_eval_summary_json(summary)
    parsed = json.loads(json_output)

    assert "Phase 3 Evaluation Summary" in text_output
    assert "experience P/R=1.00/1.00" in text_output
    assert "backend_strong_match" in text_output
    assert parsed["total_cases"] == 3
    assert parsed["passed_cases"] == 3
    assert len(parsed["case_results"]) == 3
