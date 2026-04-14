from __future__ import annotations

from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.models.render_models import (  # noqa: E402
    RenderBullet,
    RenderExperience,
    RenderPersonalInfo,
    RenderSection,
    RenderSectionType,
    RenderSourceProvenance,
    TargetPagePolicy,
)
from backend.app.services.template_registry import (  # noqa: E402
    REQUIRED_TEMPLATE_PLACEHOLDERS,
    TemplateRegistryError,
    get_active_template,
    validate_template_placeholders,
)


def test_render_model_requires_personal_required_fields() -> None:
    with pytest.raises(ValidationError):
        RenderPersonalInfo(full_name="", email="ada@example.com")

    with pytest.raises(ValidationError):
        RenderPersonalInfo(full_name="Ada Lovelace", email="")


def test_render_model_rejects_duplicate_bullet_ids() -> None:
    bullet = RenderBullet(
        id="bullet-duplicate",
        text="Built reliable APIs.",
        selected_bullet_ids=["source-bullet-1"],
        provenance=RenderSourceProvenance(
            source_item_ids=["experience-source-1"],
            source_bullet_ids=["source-bullet-1"],
        ),
        display_order=0,
    )

    with pytest.raises(ValidationError, match="duplicate experience bullet ids"):
        RenderExperience(
            id="experience-render-1",
            source_item_id="experience-source-1",
            organization="Example Co",
            title="Engineer",
            start_date="2020",
            bullets=[bullet, bullet.model_copy(update={"display_order": 1})],
            display_order=0,
        )


def test_render_model_rejects_invalid_page_policy(normal_resume) -> None:
    payload = normal_resume.model_dump(mode="json")
    payload["target_page_policy"] = "three_pages_maybe"

    with pytest.raises(ValidationError):
        type(normal_resume)(**payload)


def test_render_model_rejects_duplicate_section_order(normal_resume) -> None:
    payload = normal_resume.model_dump(mode="json")
    payload["sections"][1]["display_order"] = payload["sections"][0]["display_order"]

    with pytest.raises(ValidationError, match="duplicate display_order"):
        type(normal_resume)(**payload)


def test_template_registry_validates_required_placeholders() -> None:
    loaded_template = get_active_template()

    assert loaded_template.metadata.template_id == "ats_standard"
    assert loaded_template.metadata.ats_safe is True
    assert set(REQUIRED_TEMPLATE_PLACEHOLDERS).issubset(
        set(loaded_template.discovered_placeholders)
    )

    with pytest.raises(TemplateRegistryError, match="Missing required"):
        validate_template_placeholders("% PLACEHOLDER: PERSONAL_INFO\n")

    with pytest.raises(TemplateRegistryError, match="Malformed"):
        validate_template_placeholders("% PLACEHOLDER personal_info\n")

    duplicate_content = loaded_template.content.replace(
        "\\end{document}",
        "% PLACEHOLDER: PERSONAL_INFO\n\\end{document}",
    )
    with pytest.raises(TemplateRegistryError, match="Duplicate"):
        validate_template_placeholders(duplicate_content)


def test_empty_optional_sections_can_be_hidden(empty_optional_resume) -> None:
    visible_sections = {
        section.section_type
        for section in empty_optional_resume.sections
        if section.visible
    }

    assert RenderSectionType.PROJECTS not in visible_sections
    assert RenderSectionType.CERTIFICATIONS not in visible_sections
    assert empty_optional_resume.section_visibility[RenderSectionType.PROJECTS] is False
    assert empty_optional_resume.target_page_policy is TargetPagePolicy.PREFER_ONE_PAGE
