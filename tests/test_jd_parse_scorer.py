"""Tests for JD Parse Evaluation Scorer.

These tests verify that the scorer correctly evaluates Phase 1 parser output
against expected values with proper scoring logic.
"""

import pytest

from src.resume_optimizer.evaluation.jd_parse_runner import (
    MatchMode,
    FieldScore,
    SkillScore,
    JDParseCaseResult,
    _match_value,
    _fuzzy_overlap,
    _score_field,
    _compute_recall,
    _compute_overall_score,
    _compute_field_accuracy,
    _build_summary,
)
from src.resume_optimizer.evaluation.case_models import (
    Expectation,
    ExpectationType,
    ExpectationMatchMode,
)


class TestMatchValue:
    """Tests for _match_value function."""

    def test_exact_match(self):
        assert _match_value("python", "python", MatchMode.EXACT) is True

    def test_exact_no_match(self):
        assert _match_value("python", "java", MatchMode.EXACT) is False

    def test_exact_case_insensitive(self):
        assert _match_value("Python", "python", MatchMode.EXACT) is True

    def test_fuzzy_match_contains(self):
        assert _match_value("python programming", "python", MatchMode.FUZZY) is True

    def test_fuzzy_no_match(self):
        assert _match_value("java", "python", MatchMode.FUZZY) is False

    def test_subset_match(self):
        assert _match_value("python go sql", "python", MatchMode.SUBSET) is True

    def test_subset_no_match(self):
        assert _match_value("java", "python", MatchMode.SUBSET) is False

    def test_acceptable_match_fuzzy(self):
        assert (
            _match_value(
                "senior software engineer", "software engineer", MatchMode.ACCEPTABLE
            )
            is True
        )


class TestFuzzyOverlap:
    """Tests for _fuzzy_overlap function."""

    def test_identical(self):
        assert _fuzzy_overlap("python", "python") == 1.0

    def test_no_overlap(self):
        assert _fuzzy_overlap("python", "java") == 0.0

    def test_partial_overlap(self):
        overlap = _fuzzy_overlap("python and go", "python developer")
        assert 0.0 < overlap < 1.0


class TestScoreField:
    """Tests for _score_field function."""

    def test_exact_match(self):
        result = _score_field(
            field_name="title",
            expected="Software Engineer",
            actual="Software Engineer",
            match_mode=MatchMode.EXACT,
        )
        assert result.matched is True
        assert result.score == 1.0

    def test_no_match(self):
        result = _score_field(
            field_name="title",
            expected="Software Engineer",
            actual="Data Analyst",
            match_mode=MatchMode.EXACT,
        )
        assert result.matched is False
        assert result.score == 0.0

    def test_actual_none(self):
        result = _score_field(
            field_name="title",
            expected="Software Engineer",
            actual=None,
            match_mode=MatchMode.EXACT,
        )
        assert result.matched is False
        assert result.score == 0.0

    def test_expected_none(self):
        result = _score_field(
            field_name="title",
            expected=None,
            actual="Data Analyst",
            match_mode=MatchMode.EXACT,
        )
        assert result.matched is True
        assert result.score == 1.0


class TestComputeRecall:
    """Tests for _compute_recall function."""

    def test_perfect_recall(self):
        scores = [
            SkillScore("Python", ExpectationType.MUST_INCLUDE, True, 1.0, 1.0),
            SkillScore("Go", ExpectationType.MUST_INCLUDE, True, 0.9, 0.9),
        ]
        assert _compute_recall(scores) == 1.0

    def test_zero_recall(self):
        scores = [
            SkillScore("Python", ExpectationType.MUST_INCLUDE, False, 0.0, 1.0),
        ]
        assert _compute_recall(scores) == 0.0

    def test_partial_recall(self):
        scores = [
            SkillScore("Python", ExpectationType.MUST_INCLUDE, True, 1.0, 1.0),
            SkillScore("Go", ExpectationType.MUST_INCLUDE, False, 0.0, 0.9),
        ]
        recall = _compute_recall(scores)
        assert 0.0 < recall < 1.0


class TestComputeOverallScore:
    """Tests for _compute_overall_score function."""

    def test_perfect_score(self):
        title = FieldScore("title", "Engineer", "Engineer", True, 1.0, 1.0, "matched")
        role = FieldScore("role", "backend", "backend", True, 1.0, 1.0, "matched")
        senior = FieldScore("senior", "senior", "senior", True, 1.0, 1.0, "matched")
        must = [SkillScore("Python", ExpectationType.MUST_INCLUDE, True, 1.0, 1.0)]
        nice = []
        resp = 1.0
        conf = 1.0

        score = _compute_overall_score(title, role, senior, must, nice, resp, conf)

        assert score == 1.0

    def test_zero_score(self):
        title = FieldScore("title", "Engineer", "Analyst", False, 0.0, 1.0, "no match")
        role = FieldScore("role", "backend", "frontend", False, 0.0, 1.0, "no match")
        senior = FieldScore("senior", "senior", "junior", False, 0.0, 1.0, "no match")
        must = [SkillScore("Python", ExpectationType.MUST_INCLUDE, False, 0.0, 1.0)]
        nice = []
        resp = 0.0
        conf = 0.0

        score = _compute_overall_score(title, role, senior, must, nice, resp, conf)

        assert score < 0.2


class TestBuildSummary:
    """Tests for summary building."""

    def test_empty_results(self):
        summary = _build_summary([])

        assert summary.total_cases == 0
        assert summary.passed_cases == 0

    def test_all_pass(self):
        results = [
            JDParseCaseResult("case1", "desc", True, 1.0),
            JDParseCaseResult("case2", "desc", True, 1.0),
        ]

        summary = _build_summary(results)

        assert summary.total_cases == 2
        assert summary.passed_cases == 2
        assert summary.failed_cases == 0

    def test_mixed_results(self):
        results = [
            JDParseCaseResult("case1", "desc", True, 1.0),
            JDParseCaseResult("case2", "desc", False, 0.5),
        ]

        summary = _build_summary(results)

        assert summary.total_cases == 2
        assert summary.passed_cases == 1
        assert summary.failed_cases == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
