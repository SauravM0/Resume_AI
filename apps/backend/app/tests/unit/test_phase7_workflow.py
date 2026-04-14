from __future__ import annotations

from backend.app.evaluation.workflow import (
    WorkflowCheckResult,
    build_suite_report,
    evaluate_selection_ci,
    render_suite_markdown,
)
from src.resume_optimizer.evaluation.selection_runner import (
    CategoryScore,
    ExpectationAssessment,
    PathologicalDetection,
    SelectionCaseResult,
    SelectionSummary,
)


def _project_score(*, required: bool) -> CategoryScore:
    assessments = []
    if required:
        assessments = [
            ExpectationAssessment(
                label="Required project",
                expectation_type="must_include",
                weight=1.0,
                required=True,
                matched=False,
            )
        ]
    return CategoryScore(
        precision=1.0,
        recall=1.0,
        matched_actual_count=1,
        actual_count=1,
        false_positive_count=0,
        violated_exclusions=0,
        positive_assessments=assessments,
    )


def _case_result(
    *,
    case_id: str,
    passed: bool,
    overall_score: float,
    average_selection_relevance: float,
    project_recall: float = 1.0,
    required_project: bool = False,
    pathological: PathologicalDetection | None = None,
) -> SelectionCaseResult:
    return SelectionCaseResult(
        case_id=case_id,
        description=case_id,
        passed=passed,
        overall_score=overall_score,
        experience_precision=0.82,
        experience_recall=0.9,
        project_precision=1.0,
        project_recall=project_recall,
        bullet_precision=0.78,
        bullet_recall=0.9,
        skill_correctness=0.88,
        diversity_balance_score=0.86,
        average_selection_relevance=average_selection_relevance,
        project_score=_project_score(required=required_project),
        pathological=pathological or PathologicalDetection(),
    )


def _selection_summary(
    *,
    avg_experience_precision: float = 0.82,
    passed_cases: int,
    failed_cases: int,
    avg_project_recall: float,
    pathology_rate: float,
    case_results: list[SelectionCaseResult],
) -> SelectionSummary:
    return SelectionSummary(
        total_cases=passed_cases + failed_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        avg_experience_precision=avg_experience_precision,
        avg_experience_recall=0.9,
        avg_project_precision=1.0,
        avg_project_recall=avg_project_recall,
        avg_bullet_precision=0.78,
        avg_bullet_recall=0.9,
        avg_skill_correctness=0.88,
        avg_diversity_balance=0.86,
        pathology_rate=pathology_rate,
        case_results=case_results,
    )


def _thresholds() -> dict[str, object]:
    return {
        "min_total_cases": 3,
        "regression_guardrail": {
            "max_metric_regression": 0.03,
            "baseline": {
                "pass_rate": 0.6667,
                "avg_experience_precision": 0.8,
                "avg_experience_recall": 0.88,
                "avg_project_precision": 0.95,
                "avg_project_recall": 0.66,
                "avg_bullet_precision": 0.72,
                "avg_bullet_recall": 0.88,
                "avg_skill_correctness": 0.85,
                "avg_diversity_balance": 0.82,
                "pathology_rate": 0.33,
                "avg_selection_relevance": 0.7,
                "avg_overall_score": 0.8,
            },
        },
        "absolute_quality": {
            "min_pass_rate": 0.66,
            "max_pathology_rate": 0.34,
            "min_avg_project_recall": 0.5,
            "min_avg_selection_relevance": 0.65,
            "min_avg_overall_score": 0.75,
        },
    }


def test_evaluate_selection_ci_passes_genuine_quality_scenario() -> None:
    cases = [
        _case_result(case_id="case.1", passed=True, overall_score=0.84, average_selection_relevance=0.73),
        _case_result(case_id="case.2", passed=True, overall_score=0.82, average_selection_relevance=0.72),
        _case_result(case_id="case.3", passed=False, overall_score=0.76, average_selection_relevance=0.67),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            passed_cases=2,
            failed_cases=1,
            avg_project_recall=0.67,
            pathology_rate=0.33,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "pass"
    assert check.metrics["absolute_quality_pass"] == 1.0
    assert check.metrics["regression_guardrail_pass"] == 1.0


def test_evaluate_selection_ci_fails_when_all_cases_fail() -> None:
    cases = [
        _case_result(case_id="case.1", passed=False, overall_score=0.42, average_selection_relevance=0.44),
        _case_result(case_id="case.2", passed=False, overall_score=0.39, average_selection_relevance=0.41),
        _case_result(case_id="case.3", passed=False, overall_score=0.4, average_selection_relevance=0.43),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            avg_experience_precision=0.78,
            passed_cases=0,
            failed_cases=3,
            avg_project_recall=0.4,
            pathology_rate=0.33,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "fail"
    assert "selection quality gate failed" == check.message
    assert any("all selection cases failed" in finding for finding in check.findings)


def test_evaluate_selection_ci_fails_on_high_pathology_rate() -> None:
    pathology = PathologicalDetection(has_irrelevant_old=True, reasons=["bad old experience"])
    cases = [
        _case_result(case_id="case.1", passed=False, overall_score=0.7, average_selection_relevance=0.69, pathological=pathology),
        _case_result(case_id="case.2", passed=True, overall_score=0.8, average_selection_relevance=0.72, pathological=pathology),
        _case_result(case_id="case.3", passed=True, overall_score=0.79, average_selection_relevance=0.71),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            passed_cases=2,
            failed_cases=1,
            avg_project_recall=0.67,
            pathology_rate=0.67,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "fail"
    assert any("pathology_rate above threshold" in finding for finding in check.findings)


def test_evaluate_selection_ci_fails_on_zero_project_recall_for_required_projects() -> None:
    cases = [
        _case_result(
            case_id="case.1",
            passed=False,
            overall_score=0.74,
            average_selection_relevance=0.7,
            project_recall=0.0,
            required_project=True,
        ),
        _case_result(case_id="case.2", passed=True, overall_score=0.82, average_selection_relevance=0.72),
        _case_result(case_id="case.3", passed=True, overall_score=0.81, average_selection_relevance=0.71),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            passed_cases=2,
            failed_cases=1,
            avg_project_recall=0.45,
            pathology_rate=0.0,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "fail"
    assert any("required projects but achieved zero project recall" in finding for finding in check.findings)


def test_evaluate_selection_ci_fails_on_low_average_relevance() -> None:
    cases = [
        _case_result(case_id="case.1", passed=True, overall_score=0.8, average_selection_relevance=0.58),
        _case_result(case_id="case.2", passed=True, overall_score=0.81, average_selection_relevance=0.61),
        _case_result(case_id="case.3", passed=False, overall_score=0.76, average_selection_relevance=0.6),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            passed_cases=2,
            failed_cases=1,
            avg_project_recall=0.67,
            pathology_rate=0.0,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "fail"
    assert any("avg_selection_relevance below threshold" in finding for finding in check.findings)


def test_evaluate_selection_ci_fails_on_regression_even_if_absolute_quality_passes() -> None:
    cases = [
        _case_result(case_id="case.1", passed=True, overall_score=0.83, average_selection_relevance=0.72),
        _case_result(case_id="case.2", passed=True, overall_score=0.82, average_selection_relevance=0.72),
        _case_result(case_id="case.3", passed=False, overall_score=0.77, average_selection_relevance=0.68),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            avg_experience_precision=0.7,
            passed_cases=2,
            failed_cases=1,
            avg_project_recall=0.67,
            pathology_rate=0.33,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "fail"
    assert check.metrics["absolute_quality_pass"] == 1.0
    assert check.metrics["regression_guardrail_pass"] == 0.0
    assert any("avg_experience_precision regressed from baseline" in finding for finding in check.findings)


def test_evaluate_selection_ci_treats_higher_pathology_rate_as_regression() -> None:
    cases = [
        _case_result(case_id="case.1", passed=True, overall_score=0.84, average_selection_relevance=0.73),
        _case_result(case_id="case.2", passed=True, overall_score=0.82, average_selection_relevance=0.72),
        _case_result(case_id="case.3", passed=False, overall_score=0.78, average_selection_relevance=0.68),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            passed_cases=2,
            failed_cases=1,
            avg_project_recall=0.67,
            pathology_rate=0.5,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "fail"
    assert any("pathology_rate regressed from baseline" in finding for finding in check.findings)


def test_evaluate_selection_ci_fails_mixed_results_when_quality_is_still_bad() -> None:
    cases = [
        _case_result(case_id="case.1", passed=True, overall_score=0.81, average_selection_relevance=0.71),
        _case_result(case_id="case.2", passed=False, overall_score=0.63, average_selection_relevance=0.59),
        _case_result(case_id="case.3", passed=False, overall_score=0.61, average_selection_relevance=0.57),
    ]
    check = evaluate_selection_ci(
        _selection_summary(
            passed_cases=1,
            failed_cases=2,
            avg_project_recall=0.52,
            pathology_rate=0.33,
            case_results=cases,
        ),
        _thresholds(),
    )

    assert check.status == "fail"
    assert any("pass_rate below threshold" in finding for finding in check.findings)


def test_render_suite_markdown_describes_confidence_levels() -> None:
    report = build_suite_report(
        mode="ci-safe",
        command="run_all_phase7",
        checks=[
            WorkflowCheckResult(name="selection", status="pass", confidence_level="quality", message="ok"),
            WorkflowCheckResult(name="end_to_end", status="pass", confidence_level="smoke", message="smoke only"),
        ],
    )
    markdown = render_suite_markdown(report)

    assert "# Phase 7 Workflow Summary" in markdown
    assert "`quality` means" in markdown
    assert "`smoke` means" in markdown
