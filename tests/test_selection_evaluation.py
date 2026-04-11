"""Tests for the Phase 7 real selection evaluation pack."""

from __future__ import annotations

from datetime import date
import json

from src.resume_optimizer.evaluation.case_models import (
    Expectation,
    ExpectationMatchMode,
    ExpectationType,
    SelectionExpectations,
)
from src.resume_optimizer.evaluation.selection_runner import (
    CategoryScore,
    PathologicalDetection,
    SelectionCaseResult,
    _ActualSelectable,
    _detect_pathologies,
    _score_category,
    render_selection_case_report,
    render_selection_summary_json,
    run_selection_evaluation,
)


def test_acceptable_alternative_group_counts_once() -> None:
    actual_items = [
        _ActualSelectable(
            id="exp.1",
            label="Staff Platform Engineer @ RelayOps",
            match_values=("Staff Platform Engineer @ RelayOps", "RelayOps platform strategy"),
            relevance_score=0.9,
            source_item_id="exp.1",
        )
    ]
    expectations = [
        Expectation(
            type=ExpectationType.ACCEPTABLE_ALTERNATIVE,
            value="RelayOps",
            match_mode=ExpectationMatchMode.FUZZY,
            alternative_group="breadth_slot",
        ),
        Expectation(
            type=ExpectationType.ACCEPTABLE_ALTERNATIVE,
            value="ComputeDock",
            match_mode=ExpectationMatchMode.FUZZY,
            alternative_group="breadth_slot",
        ),
    ]

    score = _score_category(expectations, actual_items)

    assert score.recall == 1.0
    assert len(score.positive_assessments) == 1
    assert score.positive_assessments[0].matched is True


def test_must_exclude_penalizes_precision() -> None:
    actual_items = [
        _ActualSelectable(
            id="exp.good",
            label="Backend Engineer @ SignalStack",
            match_values=("Backend Engineer @ SignalStack",),
            relevance_score=0.8,
            source_item_id="exp.good",
        ),
        _ActualSelectable(
            id="exp.bad",
            label="Java Developer @ LegacyBank",
            match_values=("Java Developer @ LegacyBank", "Struts monolith"),
            relevance_score=0.2,
            end_year=2019,
            source_item_id="exp.bad",
        ),
    ]
    expectations = [
        Expectation(type=ExpectationType.MUST_INCLUDE, value="Backend Engineer @ SignalStack"),
        Expectation(type=ExpectationType.MUST_NOT_INCLUDE, value="Java Developer @ LegacyBank"),
    ]

    score = _score_category(expectations, actual_items)

    assert score.precision == 0.5
    assert score.recall == 1.0
    assert score.violated_exclusions == 1


def test_pathology_detection_flags_old_irrelevant_selection() -> None:
    actual_selection = {
        "experiences": [
            _ActualSelectable(
                id="exp.good",
                label="Backend Engineer @ SignalStack",
                match_values=("Backend Engineer @ SignalStack",),
                relevance_score=0.82,
                source_item_id="exp.good",
                selected_bullet_count=3,
            ),
            _ActualSelectable(
                id="exp.bad",
                label="Java Developer @ LegacyBank",
                match_values=("Java Developer @ LegacyBank",),
                relevance_score=0.2,
                end_year=2018,
                source_item_id="exp.bad",
                selected_bullet_count=1,
            ),
        ],
        "projects": [],
        "bullets": [
            _ActualSelectable(
                id="b1",
                label="good bullet 1",
                match_values=("good bullet 1",),
                source_item_id="exp.good",
                selected_bullet_count=1,
            ),
            _ActualSelectable(
                id="b2",
                label="good bullet 2",
                match_values=("good bullet 2",),
                source_item_id="exp.good",
                selected_bullet_count=1,
            ),
            _ActualSelectable(
                id="b3",
                label="good bullet 3",
                match_values=("good bullet 3",),
                source_item_id="exp.good",
                selected_bullet_count=1,
            ),
            _ActualSelectable(
                id="b4",
                label="bad bullet",
                match_values=("bad bullet",),
                source_item_id="exp.bad",
                selected_bullet_count=1,
            ),
        ],
        "skills": [],
    }
    score = CategoryScore(
        precision=0.5,
        recall=1.0,
        matched_actual_count=1,
        actual_count=2,
        false_positive_count=1,
        violated_exclusions=1,
    )
    expectations = SelectionExpectations(
        min_selection_relevance=0.6,
        min_bullet_count=3,
    )

    pathology = _detect_pathologies(
        actual_selection=actual_selection,
        experience_score=score,
        expectations=expectations,
        today=date(2026, 4, 10),
    )

    assert pathology.has_irrelevant_old is True
    assert pathology.has_too_few_bullets is False


def test_report_generation_is_explainable() -> None:
    result = SelectionCaseResult(
        case_id="case.report",
        description="Report smoke test",
        passed=False,
        overall_score=0.71,
        experience_precision=0.5,
        experience_recall=1.0,
        project_precision=1.0,
        project_recall=0.0,
        bullet_precision=0.5,
        bullet_recall=1.0,
        skill_correctness=0.8,
        diversity_balance_score=0.6,
        average_selection_relevance=0.55,
        pathological=PathologicalDetection(
            has_irrelevant_old=True,
            reasons=["Older experience was selected without enough relevance."]
        ),
        failure_reasons=["project missing required expectation: Developer Provisioning Platform"],
        actual_selection={
            "experiences": [{"label": "Staff Platform Engineer @ RelayOps"}],
            "projects": [],
            "bullets": [{"label": "Built Terraform modules"}],
            "skills": [{"label": "Terraform"}],
        },
    )

    report = render_selection_case_report(result)

    assert "Selected evidence:" in report
    assert "Metrics:" in report
    assert "Pathology checks:" in report
    assert "Failures:" in report


def test_real_selection_pack_runs_and_json_report_is_parseable() -> None:
    summary = run_selection_evaluation("fixtures/evaluation/selection/backend_selection.yaml")
    payload = json.loads(render_selection_summary_json(summary))

    assert summary.total_cases == 3
    assert summary.failed_cases == 0
    assert len(summary.case_results) == 3
    assert payload["total_cases"] == 3
    assert "case_results" in payload
    assert summary.case_results[0].actual_selection["experiences"]
