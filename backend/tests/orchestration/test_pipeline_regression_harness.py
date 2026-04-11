from __future__ import annotations

from pathlib import Path

from backend.app.orchestration.enums import PipelineStatus
from backend.tests.orchestration.pipeline_harness import (
    load_pipeline_cases,
    run_pipeline_case,
    run_pipeline_cases,
)

CASES_PATH = Path("backend/tests/fixtures/pipeline_cases/regression_cases.json")


def test_batch_harness_runs_all_pipeline_cases(tmp_path: Path) -> None:
    cases = load_pipeline_cases(CASES_PATH)
    report = run_pipeline_cases(cases, artifact_root=tmp_path / "artifacts")

    assert report["case_count"] == 9
    assert report["passed_count"] == 9
    assert report["failed_count"] == 0
    assert {result["scenario_type"] for result in report["results"]} == {
        "strong_match",
        "moderate_match",
        "weak_match",
        "short_jd",
        "noisy_jd",
        "special_characters",
        "latex_sensitive_content",
        "verifier_rejection",
        "retry_triggering",
    }


def test_harness_snapshots_stage_sequence_and_artifact_kinds(tmp_path: Path) -> None:
    case = next(case for case in load_pipeline_cases(CASES_PATH) if case.case_id == "strong_match")
    result = run_pipeline_case(case, artifact_root=tmp_path / "artifacts")

    assert result.passed is True
    assert result.status == PipelineStatus.SUCCEEDED.value
    assert result.snapshot["stage_sequence"] == [
        "load_source_profile",
        "normalize_source_data",
        "ingest_job_description",
        "parse_job_description",
        "rank_select_evidence",
        "generate_structured_content",
        "verify_generated_content",
        "render_deterministic_latex",
        "compile_pdf",
        "persist_artifacts",
    ]
    assert "job_analysis" in result.snapshot["artifact_kinds"]
    assert "phase3_result" in result.snapshot["artifact_kinds"]
    assert "verification_report" in result.snapshot["artifact_kinds"]
    assert "pdf" in result.snapshot["artifact_kinds"]


def test_harness_localizes_verifier_rejection(tmp_path: Path) -> None:
    case = next(case for case in load_pipeline_cases(CASES_PATH) if case.case_id == "verifier_rejection")
    result = run_pipeline_case(case, artifact_root=tmp_path / "artifacts")

    assert result.passed is True
    assert result.status == PipelineStatus.BLOCKED.value
    assert result.failed_stage == "verify_generated_content"
    assert result.error_type == "verification_blocked"
    assert result.fallback_decisions
    assert result.fallback_decisions[0]["fallback_strategy"] == "source_bullet_or_safer_rewrite"


def test_harness_records_retry_attempt_without_full_pipeline_restart(tmp_path: Path) -> None:
    case = next(case for case in load_pipeline_cases(CASES_PATH) if case.case_id == "retry_triggering")
    result = run_pipeline_case(case, artifact_root=tmp_path / "artifacts")

    assert result.passed is True
    assert result.status == PipelineStatus.SUCCEEDED.value
    assert result.retry_attempts == [
        {
            "stage_name": "generate_structured_content",
            "attempt_number": 2,
            "reason": "forced retry for retry_triggering",
            "retry_strategy": "stricter_instruction_path",
            "result_status": "retrying",
        }
    ]
    generation_outcomes = [
        outcome
        for outcome in result.stage_outcomes
        if outcome["stage_name"] == "generate_structured_content"
    ]
    assert [outcome["status"] for outcome in generation_outcomes] == ["retrying", "succeeded"]
