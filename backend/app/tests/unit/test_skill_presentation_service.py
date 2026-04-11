from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.tests.fixtures.skill_presentation_cases import (
    backend_heavy_skill_case,
    data_analytics_skill_case,
    frontend_heavy_skill_case,
    fullstack_hybrid_skill_case,
)
from resume_optimizer.generation.skill_presentation_service import present_skills


def test_backend_skill_set_is_compact_deduplicated_and_prioritized() -> None:
    result = present_skills(backend_heavy_skill_case())

    assert result.grouped_skills
    assert any(group.label == "Languages" for group in result.grouped_skills)
    all_skills = [skill for group in result.grouped_skills for skill in group.skill_names]
    assert "PostgreSQL" in all_skills
    assert "Node.js" in all_skills
    assert all_skills.count("JavaScript") == 1


def test_frontend_skill_order_matches_role_family_importance() -> None:
    result = present_skills(frontend_heavy_skill_case())

    assert result.grouped_skills[0].label == "Frameworks"
    first_line = result.rendered_skill_lines[0]
    assert "React" in first_line
    assert "Next.js" in first_line


def test_fullstack_hybrid_groups_cross_stack_skills_cleanly() -> None:
    result = present_skills(fullstack_hybrid_skill_case())

    labels = [group.label for group in result.grouped_skills]
    assert "Languages" in labels
    assert "Frameworks" in labels
    assert any("Node.js" in line for line in result.rendered_skill_lines)


def test_data_role_emphasizes_languages_and_databases() -> None:
    result = present_skills(data_analytics_skill_case())

    labels = [group.label for group in result.grouped_skills]
    assert labels[0] in {"Languages", "Databases"}
    rendered = " ".join(result.rendered_skill_lines)
    assert "Python" in rendered
    assert "SQL" in rendered
    assert "Snowflake" in rendered
