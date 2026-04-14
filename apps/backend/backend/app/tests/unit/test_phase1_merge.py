from __future__ import annotations

from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from resume_optimizer.phase1_deterministic_extractors import (
    extract_deterministic_job_description_artifacts,
)
from resume_optimizer.phase1_merge import merge_phase1_deterministic_and_llm
from resume_optimizer.phase1_models import RequirementConfidenceItemType

FIXTURE_DIR = REPO_ROOT / "backend" / "app" / "tests" / "fixtures" / "phase1"
CASES = json.loads((FIXTURE_DIR / "merged_phase1_cases.json").read_text(encoding="utf-8"))


def _confidence_for(result, item_type: RequirementConfidenceItemType, item_value: str) -> float:
    for item in result.requirement_confidence_by_item:
        if item.item_type == item_type and item.item_value == item_value:
            return item.confidence
    raise AssertionError(f"Missing confidence item for {item_type.value}:{item_value}")


def test_merge_preserves_explicit_deterministic_title_and_surfaces_conflict() -> None:
    case = CASES["conflicting_title_case"]
    deterministic = extract_deterministic_job_description_artifacts(case["raw_jd"])

    result = merge_phase1_deterministic_and_llm(
        deterministic=deterministic,
        llm_payload=case["llm_payload"],
    )

    assert result.job_title == "Senior Backend Engineer"
    assert any("Conflict: deterministic title" in note for note in result.extraction_notes)
    assert _confidence_for(
        result,
        RequirementConfidenceItemType.JOB_TITLE,
        "Senior Backend Engineer",
    ) >= 0.8


def test_merge_marks_recruiter_intent_as_inferred_when_not_explicit() -> None:
    case = CASES["conflicting_title_case"]
    deterministic = extract_deterministic_job_description_artifacts(case["raw_jd"])

    result = merge_phase1_deterministic_and_llm(
        deterministic=deterministic,
        llm_payload=case["llm_payload"],
    )

    recruiter_item = next(
        item
        for item in result.requirement_confidence_by_item
        if item.item_type == RequirementConfidenceItemType.BUSINESS_GOAL_SIGNAL
    )
    assert recruiter_item.item_value == "Improve platform reliability for payment workflows"
    assert any("inferred" in note.casefold() for note in recruiter_item.notes)
    assert recruiter_item.confidence < _confidence_for(
        result,
        RequirementConfidenceItemType.MUST_HAVE_SKILL,
        "Python",
    )


def test_merge_surfaces_ambiguity_and_lowers_parser_confidence_for_weak_jd() -> None:
    case = CASES["ambiguous_vague_case"]
    deterministic = extract_deterministic_job_description_artifacts(case["raw_jd"])

    result = merge_phase1_deterministic_and_llm(
        deterministic=deterministic,
        llm_payload=case["llm_payload"],
    )

    assert any("Ambiguity:" in note for note in result.extraction_notes)
    assert result.parser_confidence < case["llm_payload"]["parser_confidence"]
    assert _confidence_for(
        result,
        RequirementConfidenceItemType.FUNCTIONAL_ROLE_FAMILY,
        result.functional_role_family.value,
    ) < 0.6


def test_merge_backfills_prioritized_requirements_and_keeps_grounded_ordering() -> None:
    case = CASES["conflicting_title_case"]
    deterministic = extract_deterministic_job_description_artifacts(case["raw_jd"])

    result = merge_phase1_deterministic_and_llm(
        deterministic=deterministic,
        llm_payload=case["llm_payload"],
    )

    assert result.prioritized_requirements
    assert result.prioritized_requirements[0].requirement_text == "Python"
    assert any(
        item.requirement_text == "AWS"
        and item.requirement_type == RequirementConfidenceItemType.REQUIRED_TOOL_PLATFORM
        for item in result.prioritized_requirements
    )
