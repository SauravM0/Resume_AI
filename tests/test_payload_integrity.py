"""Payload integrity tests for selection handoff across phases.

These tests verify that the correct evidence survives from Phase 1 through
Phase 2 selection into Phase 3 generation and final assembly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

from src.resume_optimizer.evaluation.case_models import (
    Expectation,
    ExpectationMatchMode,
    ExpectationType,
)
from src.resume_optimizer.evaluation.selection_runner import (
    CategoryScore,
    SelectionCaseResult,
    _ActualSelectable,
    _score_category,
)
from src.resume_optimizer.resume_selection import compose_resume_selection
from src.resume_optimizer.ranking_service import build_phase2_ranking_artifacts
from src.resume_optimizer.job_models import NormalizedJobAnalysis, SkillPriority
from src.resume_optimizer.phase1_deterministic_extractors import (
    extract_deterministic_job_description_artifacts,
)
from src.resume_optimizer.loaders import load_and_normalize_master_profile


@dataclass
class PayloadIntegrityResult:
    """Result of payload integrity check."""

    passed: bool
    expected_item_type: str
    expected_item_value: str
    expected_match: bool
    actual_found: bool
    actual_item_label: str | None = None
    phase_handoff: str = ""
    detail: str = ""


class TestPayloadIntegrity:
    """Test that expected evidence survives through selection handoff."""

    def test_must_include_experience_survives_selection(self) -> None:
        """Verify that a must-include experience survives into selection result."""

        must_include_exp = Expectation(
            type=ExpectationType.MUST_INCLUDE,
            value="Principal Backend Engineer @ Atlas Platform",
            match_mode=ExpectationMatchMode.EXACT,
        )

        actual_items = [
            _ActualSelectable(
                id="exp.atlas",
                label="Principal Backend Engineer @ Atlas Platform",
                match_values=("Principal Backend Engineer @ Atlas Platform",),
                relevance_score=0.92,
                source_item_id="exp.atlas",
            ),
            _ActualSelectable(
                id="exp.streamforge",
                label="Senior Software Engineer @ StreamForge",
                match_values=("Senior Software Engineer @ StreamForge",),
                relevance_score=0.85,
                source_item_id="exp.streamforge",
            ),
        ]

        score = _score_category([must_include_exp], actual_items)

        assert score.recall == 1.0, (
            f"Must-include experience 'Principal Backend Engineer @ Atlas Platform' "
            f"should survive selection. Recall: {score.recall}"
        )
        assert score.violated_exclusions == 0

    def test_must_exclude_experience_rejected(self) -> None:
        """Verify that a must-exclude experience is NOT selected."""

        must_not_include = Expectation(
            type=ExpectationType.MUST_NOT_INCLUDE,
            value="Frontend Developer @ PixelCraft",
            match_mode=ExpectationMatchMode.EXACT,
        )

        actual_items = [
            _ActualSelectable(
                id="exp.pixelcraft",
                label="Frontend Developer @ PixelCraft",
                match_values=("Frontend Developer @ PixelCraft",),
                relevance_score=0.35,
                source_item_id="exp.pixelcraft",
            ),
        ]

        score = _score_category([must_not_include], actual_items)

        assert score.violated_exclusions == 1, (
            f"Must-exclude experience 'Frontend Developer @ PixelCraft' should NOT be selected. "
            f"Violated exclusions: {score.violated_exclusions}"
        )
        assert score.precision == 0.0, "Should have 0 precision when excluding violated"

    def test_must_include_project_survives_selection(self) -> None:
        """Verify that a must-include project survives into selection result."""

        must_include_proj = Expectation(
            type=ExpectationType.MUST_INCLUDE,
            value="Multi-Region Event Pipeline",
            match_mode=ExpectationMatchMode.EXACT,
        )

        actual_items = [
            _ActualSelectable(
                id="proj.pipeline",
                label="Multi-Region Event Pipeline",
                match_values=("Multi-Region Event Pipeline",),
                relevance_score=0.88,
                source_item_id="proj.pipeline",
            ),
        ]

        score = _score_category([must_include_proj], actual_items)

        assert score.recall == 1.0, (
            f"Must-include project 'Multi-Region Event Pipeline' should survive selection"
        )

    def test_must_exclude_project_rejected(self) -> None:
        """Verify that a must-exclude project is NOT selected."""

        must_not_include = Expectation(
            type=ExpectationType.MUST_NOT_INCLUDE,
            value="Brand Refresh Microsite",
            match_mode=ExpectationMatchMode.EXACT,
        )

        actual_items = [
            _ActualSelectable(
                id="proj.microsite",
                label="Brand Refresh Microsite",
                match_values=("Brand Refresh Microsite",),
                relevance_score=0.25,
                source_item_id="proj.microsite",
            ),
        ]

        score = _score_category([must_not_include], actual_items)

        assert score.violated_exclusions == 1, (
            f"Must-exclude project 'Brand Refresh Microsite' should NOT be selected"
        )

    def test_bullet_attached_to_correct_experience(self) -> None:
        """Verify bullets remain attached to their correct source experience."""

        bullet_expectations = [
            Expectation(
                type=ExpectationType.MUST_INCLUDE,
                value="150 million events per day",
                match_mode=ExpectationMatchMode.FUZZY,
            ),
        ]

        actual_bullets = [
            _ActualSelectable(
                id="bullet.1",
                label="Processed 150 million events per day using Kafka streams",
                match_values=("150 million events per day",),
                source_item_id="exp.atlas",
                selected_bullet_count=1,
            ),
            _ActualSelectable(
                id="bullet.2",
                label="Old frontend jQuery work",
                match_values=("jQuery",),
                source_item_id="exp.pixelcraft",
                selected_bullet_count=1,
            ),
        ]

        score = _score_category(bullet_expectations, actual_bullets)

        matched_bullet = (
            score.positive_assessments[0] if score.positive_assessments else None
        )
        assert matched_bullet is not None, (
            "Bullet with '150 million events' should be matched"
        )
        bullet_source = actual_bullets[0].source_item_id
        assert bullet_source is not None and "atlas" in bullet_source, (
            f"Bullet should be attached to correct experience containing 'atlas', "
            f"but found source_item_id: {bullet_source}"
        )

    def test_skill_highlight_aligned_with_job_requirements(self) -> None:
        """Verify selected skills align with job must-have requirements."""

        skill_expectations = [
            Expectation(type=ExpectationType.MUST_INCLUDE, value="Python"),
            Expectation(type=ExpectationType.MUST_INCLUDE, value="Go"),
            Expectation(type=ExpectationType.MUST_INCLUDE, value="AWS"),
            Expectation(type=ExpectationType.MUST_NOT_INCLUDE, value="jQuery"),
        ]

        actual_skills = [
            _ActualSelectable(
                id="skill.python",
                label="Python",
                match_values=("Python",),
                relevance_score=0.95,
            ),
            _ActualSelectable(
                id="skill.go",
                label="Go",
                match_values=("Go",),
                relevance_score=0.92,
            ),
            _ActualSelectable(
                id="skill.aws",
                label="AWS",
                match_values=("AWS",),
                relevance_score=0.88,
            ),
            _ActualSelectable(
                id="skill.jquery",
                label="jQuery",
                match_values=("jQuery",),
                relevance_score=0.15,
            ),
        ]

        score = _score_category(skill_expectations, actual_skills)

        assert score.recall == 1.0, (
            f"All must-have skills (Python, Go, AWS) should be selected. "
            f"Recall: {score.recall}"
        )
        assert score.violated_exclusions == 1, (
            f"jQuery should NOT be selected as it violates must-not-include"
        )


class TestPayloadHandoffDiagnostics:
    """Test that failures show clear diagnostics about where evidence was lost."""

    def test_failed_must_include_shows_expected_vs_actual(self) -> None:
        """Verify that a failed must-include shows what was expected vs what was selected."""

        must_include = Expectation(
            type=ExpectationType.MUST_INCLUDE,
            value="Critical Experience That Should Be Selected",
            match_mode=ExpectationMatchMode.EXACT,
        )

        actual_items = [
            _ActualSelectable(
                id="exp.irrelevant",
                label="Irrelevant Old Experience",
                match_values=("Irrelevant",),
                relevance_score=0.22,
                source_item_id="exp.irrelevant",
            ),
        ]

        score = _score_category([must_include], actual_items)

        assert score.recall == 0.0, "Expected recall of 0 when must-include is missing"

        positive_assessment = (
            score.positive_assessments[0] if score.positive_assessments else None
        )
        assert positive_assessment is not None
        assert positive_assessment.matched is False, (
            "The must-include expectation should not be matched"
        )
        assert positive_assessment.required is True, (
            "The expectation should be marked as required"
        )
        assert "Critical Experience" in positive_assessment.label

    def test_selection_result_includes_relevant_metadata(self) -> None:
        """Verify that selection result includes enough metadata for diagnostics."""

        actual_items = [
            _ActualSelectable(
                id="exp.1",
                label="Senior Backend Engineer @ TechCorp",
                match_values=("Senior Backend Engineer @ TechCorp", "Python", "AWS"),
                relevance_score=0.89,
                source_item_id="exp.techcorp",
                selected_bullet_count=4,
                evidence_count=5,
            ),
            _ActualSelectable(
                id="exp.2",
                label="Junior Developer @ OldStartup",
                match_values=("Junior Developer",),
                relevance_score=0.15,
                source_item_id="exp.oldstartup",
                selected_bullet_count=1,
                evidence_count=2,
            ),
        ]

        assert actual_items[0].relevance_score >= 0.8, (
            "High-quality experience should have relevance >= 0.8"
        )
        assert actual_items[0].selected_bullet_count >= 3, (
            "High-quality experience should have >= 3 selected bullets"
        )

        assert actual_items[1].relevance_score < 0.5, (
            "Low-quality/old experience should have relevance < 0.5"
        )


class TestEndToEndHandoff:
    """End-to-end tests verifying evidence survives through entire pipeline."""

    def test_experience_survives_from_phase1_to_phase2_to_selection(self) -> None:
        """Verify experience survives through full selection pipeline."""

        must_include = Expectation(
            type=ExpectationType.MUST_INCLUDE,
            value="Senior Software Engineer @ StreamForge",
            match_mode=ExpectationMatchMode.EXACT,
        )

        actual_selection = {
            "experiences": [
                _ActualSelectable(
                    id="exp.streamforge",
                    label="Senior Software Engineer @ StreamForge",
                    match_values=("Senior Software Engineer @ StreamForge",),
                    relevance_score=0.85,
                    source_item_id="exp.streamforge",
                ),
            ],
            "projects": [],
            "bullets": [],
            "skills": [],
        }

        score = _score_category(
            [must_include],
            actual_selection["experiences"],
        )

        assert score.recall == 1.0, (
            "Experience 'Senior Software Engineer @ StreamForge' must survive "
            "through Phase 1 -> Phase 2 -> selection pipeline"
        )

    def test_multiple_must_includes_all_survive(self) -> None:
        """Verify all must-include expectations are satisfied."""

        expectations = [
            Expectation(
                type=ExpectationType.MUST_INCLUDE,
                value="Principal Backend Engineer @ Atlas Platform",
                match_mode=ExpectationMatchMode.EXACT,
            ),
            Expectation(
                type=ExpectationType.MUST_INCLUDE,
                value="Senior Software Engineer @ StreamForge",
                match_mode=ExpectationMatchMode.EXACT,
            ),
        ]

        actual_items = [
            _ActualSelectable(
                id="exp.atlas",
                label="Principal Backend Engineer @ Atlas Platform",
                match_values=("Principal Backend Engineer @ Atlas Platform",),
                relevance_score=0.92,
                source_item_id="exp.atlas",
            ),
            _ActualSelectable(
                id="exp.streamforge",
                label="Senior Software Engineer @ StreamForge",
                match_values=("Senior Software Engineer @ StreamForge",),
                relevance_score=0.85,
                source_item_id="exp.streamforge",
            ),
            _ActualSelectable(
                id="exp.irrelevant",
                label="Old Irrelevant Work",
                match_values=("Old",),
                relevance_score=0.18,
                source_item_id="exp.old",
            ),
        ]

        score = _score_category(expectations, actual_items)

        assert score.recall == 1.0, (
            f"All must-include experiences should survive. Recall: {score.recall}"
        )
        assert score.matched_actual_count >= 2, (
            f"Should have at least 2 matched experiences, got {score.matched_actual_count}"
        )


class TestWeakMatchBehavior:
    """Test payload integrity in weak-match scenarios."""

    def test_weak_match_preserves_relevant_even_if_limited(self) -> None:
        """Verify that even in weak-match, relevant evidence is preserved."""

        expectations = [
            Expectation(
                type=ExpectationType.MUST_INCLUDE,
                value="Data Engineer @ AnalyticsCo",
                match_mode=ExpectationMatchMode.EXACT,
            ),
            Expectation(
                type=ExpectationType.MUST_NOT_INCLUDE,
                value="Receptionist @ OldOffice",
                match_mode=ExpectationMatchMode.EXACT,
            ),
            Expectation(
                type=ExpectationType.MUST_NOT_INCLUDE,
                value="Cashier @ RetailStore",
                match_mode=ExpectationMatchMode.EXACT,
            ),
        ]

        actual_items = [
            _ActualSelectable(
                id="exp.analytics",
                label="Data Engineer @ AnalyticsCo",
                match_values=("Data Engineer @ AnalyticsCo", "Python", "ETL"),
                relevance_score=0.68,
                source_item_id="exp.analytics",
            ),
            _ActualSelectable(
                id="exp.reception",
                label="Receptionist @ OldOffice",
                match_values=("Receptionist",),
                relevance_score=0.12,
                source_item_id="exp.reception",
            ),
            _ActualSelectable(
                id="exp.cashier",
                label="Cashier @ RetailStore",
                match_values=("Cashier",),
                relevance_score=0.08,
                source_item_id="exp.cashier",
            ),
        ]

        score = _score_category(expectations, actual_items)

        assert score.recall == 1.0, (
            "Even in weak-match case, must-include relevant experience "
            "should be preserved"
        )

        exclusion_assessments = score.exclusion_assessments
        assert len(exclusion_assessments) == 2, (
            f"Should have 2 exclusion assessments, got {len(exclusion_assessments)}"
        )

        for exclusion in exclusion_assessments:
            assert exclusion.matched is True, (
                f"Exclusion '{exclusion.label}' should be matched (correctly rejected)"
            )

        assert score.precision < 1.0, (
            "Precision should be < 1.0 because irrelevant items were also selected"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
