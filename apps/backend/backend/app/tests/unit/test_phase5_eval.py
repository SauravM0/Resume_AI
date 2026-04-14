from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.tests.fixtures.phase5_eval_cases import load_phase5_eval_cases
from resume_optimizer.phase5_eval import (
    load_phase5_eval_baseline,
    phase5_eval_summary_json,
    render_phase5_eval_summary,
    run_phase5_eval,
)


def test_phase5_eval_fixture_pack_covers_required_cases() -> None:
    cases = load_phase5_eval_cases()

    assert len(cases) == 10
    assert {case.case_id for case in cases} == {
        "backend_senior_ic",
        "frontend_lead",
        "devops_platform",
        "data_analytics",
        "engineering_management",
        "weak_match",
        "overlapping_experiences",
        "many_projects",
        "sparse_certifications",
        "page_budget_constrained",
    }


def test_phase5_eval_runner_matches_baseline_snapshot() -> None:
    summary = run_phase5_eval(today=date(2026, 4, 9))
    baseline = load_phase5_eval_baseline()

    assert summary.model_dump(mode="json") == baseline
    assert summary.total_cases == 10
    assert summary.passed_cases + summary.failed_cases == 10


def test_phase5_eval_renderers_expose_case_outputs() -> None:
    summary = run_phase5_eval(today=date(2026, 4, 9), case_ids=["backend_senior_ic"])

    text_output = render_phase5_eval_summary(summary)
    json_output = phase5_eval_summary_json(summary)
    parsed = json.loads(json_output)

    assert "Phase 5 Evaluation Summary" in text_output
    assert "backend_senior_ic" in text_output
    assert parsed["total_cases"] == 1
    assert parsed["passed_cases"] + parsed["failed_cases"] == 1
