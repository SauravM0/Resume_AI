from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.tests.fixtures.section_assembly_cases import (
    certification_relevant_case,
    experience_heavy_case,
    omitted_item_tracking_case,
    one_page_constrained_case,
    project_heavy_case,
    two_page_allowed_case,
)
from resume_optimizer.phase3_models import OmissionReason
from resume_optimizer.generation.section_assembly_service import SectionAssemblyService


def test_experience_heavy_resume_preserves_item_order_and_caps() -> None:
    context, assembly_input = experience_heavy_case()

    result = SectionAssemblyService().assemble(assembly_input, context)

    assert result.assembled_experience_sections
    item_ids = [item.source_item_id for item in result.assembled_experience_sections[0].items]
    assert item_ids[:2] == ["exp.1", "exp.2"]
    assert all(len(item.bullets) <= context.page_constraints.max_experience_bullets_per_item for item in result.assembled_experience_sections[0].items)


def test_project_heavy_resume_assembles_project_sections() -> None:
    context, assembly_input = project_heavy_case()

    result = SectionAssemblyService().assemble(assembly_input, context)

    assert result.assembled_project_sections
    assert [item.source_item_id for item in result.assembled_project_sections[0].items] == ["proj.1", "proj.2"]
    assert all(item.bullets for item in result.assembled_project_sections[0].items)


def test_certification_relevant_resume_includes_certification_section() -> None:
    context, assembly_input = certification_relevant_case()

    result = SectionAssemblyService().assemble(assembly_input, context)

    assert result.assembled_certification_section is not None
    assert result.assembled_certification_section.items[0].name == "AWS Certified Developer"


def test_one_page_constraints_trigger_deterministic_budget_omissions() -> None:
    context, assembly_input = one_page_constrained_case()

    result = SectionAssemblyService().assemble(assembly_input, context)

    assert result.budget_signals.target_page_count == 1
    assert result.budget_signals.max_total_bullets == 8
    assert result.budget_signals.used_total_bullets == 8
    assert result.omitted_items_with_reasons
    assert any(item.reason == OmissionReason.SPACE_CONSTRAINT for item in result.omitted_items_with_reasons)


def test_two_page_mode_allows_more_content() -> None:
    context, assembly_input = two_page_allowed_case()

    result = SectionAssemblyService().assemble(assembly_input, context)

    assert result.budget_signals.target_page_count == 2
    assert result.budget_signals.max_total_bullets == 14
    assert result.budget_signals.used_total_bullets >= 10
    assert not any(
        item.source_item_id == "proj.1" and item.reason == OmissionReason.SPACE_CONSTRAINT
        for item in result.omitted_items_with_reasons
    )


def test_omitted_item_tracking_records_missing_rewrites_and_budget_drops() -> None:
    context, assembly_input = omitted_item_tracking_case()

    result = SectionAssemblyService().assemble(assembly_input, context)

    assert result.assembly_warnings
    assert any("source text was used during assembly" in warning for warning in result.assembly_warnings)
    assert any(item.source_item_id == "proj.1" for item in result.omitted_items_with_reasons)
