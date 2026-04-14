from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.models.render_models import RenderSectionType, TemplatePlaceholder  # noqa: E402
from backend.app.services.latex_mapper import (  # noqa: E402
    escape_latex_text,
    render_placeholder_fragments,
    render_section_fragments,
)
from backend.app.services.layout_manager import (  # noqa: E402
    LayoutPagePolicy,
    TrimAction,
    manage_layout,
)


def test_mapper_escapes_special_characters(special_character_resume) -> None:
    fragments = render_placeholder_fragments(special_character_resume)
    combined = "\n".join(fragments.values())

    assert "Ada\\_Dev \\& Co" in combined
    assert "99\\% uptime \\& \\$0" in combined
    assert "Python\\_ETL \\& reporting" in combined
    assert "C\\#" in combined


def test_mapper_preserves_unicode_text(unicode_resume) -> None:
    fragments = render_placeholder_fragments(unicode_resume)
    combined = "\n".join(fragments.values())

    assert "Zoë Nguyễn" in combined
    assert "São Paulo" in combined
    assert "München" in combined
    assert "Zürich" in combined


def test_mapper_respects_section_order_and_empty_optional_sections(empty_optional_resume) -> None:
    results = render_section_fragments(empty_optional_resume)
    section_order = [result.section_type for result in results]
    fragments = render_placeholder_fragments(empty_optional_resume)

    assert section_order == [
        RenderSectionType.PERSONAL_INFO,
        RenderSectionType.SUMMARY,
        RenderSectionType.EXPERIENCE,
        RenderSectionType.SKILLS,
        RenderSectionType.EDUCATION,
    ]
    assert fragments[TemplatePlaceholder.PROJECTS_SECTION] == ""
    assert fragments[TemplatePlaceholder.CERTIFICATIONS_SECTION] == ""


def test_escape_latex_text_handles_common_control_characters() -> None:
    value = r"a_b & 50% $x #1 {ok} ~ ^ \ path"

    escaped = escape_latex_text(value)

    assert r"a\_b" in escaped
    assert r"\&" in escaped
    assert r"50\%" in escaped
    assert r"\$x" in escaped
    assert r"\#1" in escaped
    assert r"\{" in escaped
    assert r"\textasciitilde{}" in escaped
    assert r"\textasciicircum{}" in escaped
    assert r"\textbackslash{}" in escaped


def test_layout_trimming_is_deterministic_and_warns(long_bullet_resume) -> None:
    first = manage_layout(long_bullet_resume, page_policy=LayoutPagePolicy.ONE_PAGE_STRICT)
    second = manage_layout(long_bullet_resume, page_policy=LayoutPagePolicy.ONE_PAGE_STRICT)

    first_decisions = [decision.model_dump(mode="json") for decision in first.truncation_decisions]
    second_decisions = [decision.model_dump(mode="json") for decision in second.truncation_decisions]
    actions = [decision.action for decision in first.truncation_decisions]

    assert first_decisions == second_decisions
    assert TrimAction.REMOVE_PROJECT in actions
    assert TrimAction.TRIM_BULLETS in actions
    assert first.warnings
    assert first.overflow_remaining is (
        first.estimated_lines_after > first.max_allowed_lines
    )
    assert len(long_bullet_resume.projects) == 4
    assert len(long_bullet_resume.experiences[0].bullets) == 8
