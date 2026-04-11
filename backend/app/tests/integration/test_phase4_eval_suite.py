from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.scripts.run_phase4_eval import (
    DEFAULT_FIXTURE_DIR,
    load_eval_cases,
    render_summary,
    run_eval_cases,
    summarize_results,
)


def test_phase4_eval_suite_all_cases_match_expectations() -> None:
    results = run_eval_cases(load_eval_cases(DEFAULT_FIXTURE_DIR))
    summary = summarize_results(results)

    assert len(results) == 12
    assert all(result.passed_expectations for result in results), render_summary(results)
    assert summary["issue_detection_rate"] == 1.0
    assert summary["false_positive_count"] == 0
    assert summary["repair_success_rate"] == 1.0
    assert summary["degraded_case_count"] == 2
    assert summary["blocked_case_count"] == 1


@pytest.mark.semantic
def test_phase4_eval_suite_semantic_fixture_cases_are_deterministic() -> None:
    results = run_eval_cases(load_eval_cases(DEFAULT_FIXTURE_DIR))
    semantic_modes = {result.case.semantic_mode for result in results}

    assert semantic_modes == {
        "degraded",
        "pass",
        "weak_support",
    }
    assert all(result.passed_expectations for result in results)


def test_phase4_eval_suite_artifact_output_stays_machine_readable() -> None:
    results = run_eval_cases(load_eval_cases(DEFAULT_FIXTURE_DIR))

    for result in results:
        assert result.artifact_final_decision == result.decision_outcome
        assert result.artifact_issue_count == result.issue_count
        assert "status=" in result.artifact_internal_summary
        assert "decision=" in result.artifact_internal_summary
