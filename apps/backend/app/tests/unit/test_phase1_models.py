from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.models import RoleType, SeniorityLevel
from resume_optimizer.phase1_legacy_adapter import (
    adapt_phase1_analysis_to_legacy_job_analysis,
)
from resume_optimizer.phase1_models import (
    Phase1JobAnalysis,
    PrioritizedRequirement,
    PrioritizedRequirementTier,
    RequirementConfidenceItem,
    RequirementConfidenceItemType,
)
from resume_optimizer.phase1_role_modeling import (
    FunctionalRoleFamily,
    OrganizationalRoleMode,
)

FIXTURE_PATH = REPO_ROOT / "backend" / "app" / "tests" / "fixtures" / "phase1" / "full_job_analysis.json"


def _fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_phase1_job_analysis_fixture_is_fully_valid() -> None:
    analysis = Phase1JobAnalysis.model_validate(_fixture_payload())

    assert analysis.job_title == "Senior Backend Platform Engineer"
    assert analysis.functional_role_family is FunctionalRoleFamily.PLATFORM
    assert analysis.organizational_role_mode is OrganizationalRoleMode.TECH_LEAD
    assert analysis.education_requirement.minimum_level is not None
    assert analysis.delivery_scope_requirement.scope_level is not None
    assert analysis.recruiter_intent.likely_success_shape is not None
    assert analysis.recruiter_intent.breadth_preference.value == "balanced"
    assert analysis.jd_quality_breakdown.completeness_score == pytest.approx(0.9)
    assert analysis.jd_quality_score == pytest.approx(0.88)
    assert analysis.parser_confidence == pytest.approx(0.84)
    assert len(analysis.prioritized_requirements) == 5


def test_phase1_job_analysis_rejects_overlapping_skill_buckets() -> None:
    payload = _fixture_payload()
    payload["nice_to_have_skills"] = ["Terraform", "Python"]

    with pytest.raises(ValidationError, match="nice_to_have_skills must not repeat must_have_skills"):
        Phase1JobAnalysis.model_validate(payload)


def test_phase1_job_analysis_requires_notes_when_parser_confidence_is_low() -> None:
    payload = _fixture_payload()
    payload["parser_confidence"] = 0.2
    payload["extraction_notes"] = []

    with pytest.raises(ValidationError, match="low-confidence parsed job analyses must include extraction_notes"):
        Phase1JobAnalysis.model_validate(payload)


def test_phase1_job_analysis_rejects_duplicate_requirement_confidence_items() -> None:
    payload = _fixture_payload()
    confidence_items = list(payload["requirement_confidence_by_item"])
    confidence_items.append(
        {
            "item_type": "must_have_skill",
            "item_value": "Python",
            "confidence": 0.91,
        }
    )
    payload["requirement_confidence_by_item"] = confidence_items

    with pytest.raises(ValidationError, match="requirement_confidence_by_item must not contain duplicates"):
        Phase1JobAnalysis.model_validate(payload)


def test_phase1_job_analysis_rejects_duplicate_priority_ranks() -> None:
    payload = _fixture_payload()
    prioritized = list(payload["prioritized_requirements"])
    prioritized[1] = {
        **prioritized[1],
        "priority_rank": 1,
    }
    payload["prioritized_requirements"] = prioritized

    with pytest.raises(ValidationError, match="prioritized_requirements must use unique priority_rank values"):
        Phase1JobAnalysis.model_validate(payload)


def test_phase1_job_analysis_requires_confidence_items_to_match_supported_fields() -> None:
    payload = _fixture_payload()
    confidence_items = list(payload["requirement_confidence_by_item"])
    confidence_items.append(
        {
            "item_type": "business_goal_signal",
            "item_value": "Reduce churn",
            "confidence": 0.55,
        }
    )
    payload["requirement_confidence_by_item"] = confidence_items

    with pytest.raises(ValidationError, match="requirement_confidence_by_item includes values that are not represented"):
        Phase1JobAnalysis.model_validate(payload)


def test_legacy_adapter_maps_new_phase1_contract_into_legacy_job_analysis() -> None:
    analysis = Phase1JobAnalysis.model_validate(_fixture_payload())

    legacy = adapt_phase1_analysis_to_legacy_job_analysis(analysis)

    assert isinstance(legacy, NormalizedJobAnalysis)
    assert legacy.role_type is RoleType.LEAD
    assert legacy.seniority_level is SeniorityLevel.SENIOR
    assert "Python" in legacy.technical_skills
    assert "AWS" in legacy.technical_skills
    assert "Ownership" in legacy.soft_skills
    assert "Python" in [item.skill_name for item in legacy.prioritized_skills]
    assert "Observability" in [item.skill_name for item in legacy.prioritized_skills]


def test_legacy_adapter_maps_manager_like_modes_to_legacy_manager_role() -> None:
    analysis = Phase1JobAnalysis.model_validate(
        {
            **_fixture_payload(),
            "organizational_role_mode": "director_or_head",
            "seniority_level": "director",
        }
    )

    legacy = adapt_phase1_analysis_to_legacy_job_analysis(analysis)

    assert legacy.role_type is RoleType.MANAGER
    assert legacy.seniority_level is SeniorityLevel.DIRECTOR


def test_prioritized_requirement_model_rejects_critical_low_confidence_when_embedded() -> None:
    payload = _fixture_payload()
    payload["prioritized_requirements"] = [
        {
            "requirement_text": "Python",
            "requirement_type": "must_have_skill",
            "priority_rank": 1,
            "priority_tier": "critical",
            "confidence": 0.4,
        }
    ]
    payload["requirement_confidence_by_item"] = [
        {
            "item_type": "must_have_skill",
            "item_value": "Python",
            "confidence": 0.4,
        }
    ]

    with pytest.raises(ValidationError, match="critical prioritized requirements must have confidence >= 0.5"):
        Phase1JobAnalysis.model_validate(payload)


def test_supporting_models_validate_direct_construction() -> None:
    item = RequirementConfidenceItem(
        item_type=RequirementConfidenceItemType.MUST_HAVE_SKILL,
        item_value="Python",
        confidence=0.9,
    )
    prioritized = PrioritizedRequirement(
        requirement_text="Python",
        requirement_type=RequirementConfidenceItemType.MUST_HAVE_SKILL,
        priority_rank=1,
        priority_tier=PrioritizedRequirementTier.MUST_HAVE,
        confidence=0.9,
    )

    assert item.item_type is RequirementConfidenceItemType.MUST_HAVE_SKILL
    assert prioritized.priority_tier is PrioritizedRequirementTier.MUST_HAVE
