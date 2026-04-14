from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.tests.fixtures.quality_validation_cases import (
    generic_bad_summary_case,
    high_quality_output_case,
    keyword_stuffed_bullets_case,
    oversized_skills_case,
    repeated_bullets_case,
)
from resume_optimizer.generation.contracts import QualityDimension
from resume_optimizer.generation.quality_validator import (
    validate_bullet_outputs_quality,
    validate_generation_quality,
    validate_section_assembly_quality,
    validate_skill_presentation_quality,
    validate_summary_quality,
)


def test_generic_bad_summary_is_flagged() -> None:
    signals = validate_summary_quality(generic_bad_summary_case())

    assert not signals.passed
    assert any(issue.quality_dimension == QualityDimension.GENERIC_FILLER for issue in signals.warnings)
    assert any(issue.quality_dimension == QualityDimension.SUMMARY_STRENGTH for issue in signals.warnings)


def test_repeated_and_keyword_stuffed_bullets_are_flagged() -> None:
    repeated = validate_bullet_outputs_quality("section.experience", repeated_bullets_case())
    stuffed = validate_bullet_outputs_quality("section.experience", keyword_stuffed_bullets_case())

    assert any(issue.quality_dimension == QualityDimension.REPETITION for issue in repeated.warnings)
    assert any(issue.quality_dimension == QualityDimension.KEYWORD_STUFFING for issue in stuffed.warnings)


def test_oversized_skills_output_is_flagged() -> None:
    signals = validate_skill_presentation_quality(oversized_skills_case())

    assert any(issue.quality_dimension == QualityDimension.SKILLS_COMPACTNESS for issue in signals.warnings)
    assert signals.dimension_scores[QualityDimension.SKILLS_COMPACTNESS] < 0.5


def test_high_quality_output_passes_validator() -> None:
    summary, bullets, skills, assembly = high_quality_output_case()
    summary_signals = validate_summary_quality(summary)
    bullet_signals = validate_bullet_outputs_quality("section.experience", bullets)
    skill_signals = validate_skill_presentation_quality(skills)
    assembly_signals = validate_section_assembly_quality(assembly)
    aggregate = validate_generation_quality(
        summary_output=summary,
        bullet_outputs_by_section={"section.experience": bullets},
        skill_output=skills,
        assembly_output=assembly,
    )

    assert summary_signals.passed
    assert bullet_signals.passed
    assert skill_signals.passed
    assert assembly_signals.passed
    assert aggregate.passed
    assert not aggregate.hard_failures


def test_quality_issues_include_fallback_actions_and_locations() -> None:
    signals = validate_bullet_outputs_quality("section.experience", keyword_stuffed_bullets_case())

    issue = next(issue for issue in signals.warnings if issue.quality_dimension == QualityDimension.KEYWORD_STUFFING)
    assert issue.suggested_fallback_action is not None
    assert issue.section_id == "section.experience"
