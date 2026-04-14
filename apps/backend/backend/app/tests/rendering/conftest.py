from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.models.render_models import (  # noqa: E402
    ConfidenceMetadata,
    LayoutConstraints,
    RenderBullet,
    RenderCertification,
    RenderEducation,
    RenderExperience,
    RenderJobInput,
    RenderPersonalInfo,
    RenderProject,
    RenderSection,
    RenderSectionType,
    RenderSkillGroup,
    RenderSourceProvenance,
    RenderSummary,
    TargetPagePolicy,
)


def make_bullet(
    index: int,
    source_item_id: str,
    *,
    text: str | None = None,
    confidence: float = 0.75,
    truncation_eligible: bool = True,
) -> RenderBullet:
    source_bullet_id = f"src-bullet-{index}"
    return RenderBullet(
        id=f"bullet-{index}",
        text=text or f"Delivered verified impact for initiative {index}.",
        selected_bullet_ids=[source_bullet_id],
        provenance=RenderSourceProvenance(
            source_item_ids=[source_item_id],
            source_bullet_ids=[source_bullet_id],
        ),
        display_order=index,
        truncation_eligible=truncation_eligible,
        confidence=ConfidenceMetadata(confidence_score=confidence),
    )


def base_sections(*, include_optional_empty: bool = False) -> list[RenderSection]:
    sections = [
        RenderSection(
            id="section-personal",
            section_type=RenderSectionType.PERSONAL_INFO,
            title="Personal Info",
            display_order=0,
        ),
        RenderSection(
            id="section-summary",
            section_type=RenderSectionType.SUMMARY,
            title="Summary",
            display_order=1,
            truncation_eligible=True,
        ),
        RenderSection(
            id="section-experience",
            section_type=RenderSectionType.EXPERIENCE,
            title="Experience",
            display_order=2,
            layout_constraints=LayoutConstraints(min_bullets=2, priority=90),
        ),
        RenderSection(
            id="section-projects",
            section_type=RenderSectionType.PROJECTS,
            title="Projects",
            display_order=3,
            layout_constraints=LayoutConstraints(priority=40),
        ),
        RenderSection(
            id="section-skills",
            section_type=RenderSectionType.SKILLS,
            title="Skills",
            display_order=4,
            layout_constraints=LayoutConstraints(priority=50),
        ),
        RenderSection(
            id="section-education",
            section_type=RenderSectionType.EDUCATION,
            title="Education",
            display_order=5,
        ),
        RenderSection(
            id="section-certifications",
            section_type=RenderSectionType.CERTIFICATIONS,
            title="Certifications",
            display_order=6,
        ),
    ]
    if include_optional_empty:
        for section in sections:
            if section.section_type in {
                RenderSectionType.PROJECTS,
                RenderSectionType.CERTIFICATIONS,
            }:
                section.visible = False
    return sections


def make_render_input(
    *,
    render_job_id: str = "render-test-001",
    personal_name: str = "Ada Lovelace",
    summary_text: str = "Backend engineer focused on reliable APIs.",
    bullet_texts: list[str] | None = None,
    project_count: int = 1,
    skill_values: list[str] | None = None,
    include_optional_empty: bool = False,
    max_lines: int | None = None,
) -> RenderJobInput:
    bullet_texts = bullet_texts or [
        "Built Python APIs with PostgreSQL-backed data workflows.",
        "Improved service reliability with deterministic validation checks.",
        "Partnered with product teams to ship measurable backend improvements.",
    ]
    source_item_id = "exp-source-001"
    bullets = [
        make_bullet(index, source_item_id, text=text, confidence=0.9 - index * 0.1)
        for index, text in enumerate(bullet_texts)
    ]
    projects = [
        RenderProject(
            id=f"project-{index}",
            source_item_id=f"project-source-{index}",
            name=f"Project {index}",
            role="Backend Developer",
            bullets=[
                make_bullet(
                    100 + index,
                    f"project-source-{index}",
                    text=f"Delivered project milestone {index}.",
                    confidence=0.4 + index * 0.1,
                )
            ],
            tools=["Python", "LaTeX"],
            display_order=index,
            confidence=ConfidenceMetadata(confidence_score=0.4 + index * 0.1),
        )
        for index in range(project_count)
    ]
    education = [
        RenderEducation(
            id="education-001",
            source_item_id="education-source-001",
            institution="State University",
            degree="B.S.",
            field_of_study="Computer Science",
            start_date="2016",
            end_date="2020",
            display_order=0,
        )
    ]
    certifications = [] if include_optional_empty else [
        RenderCertification(
            id="certification-001",
            source_item_id="certification-source-001",
            name="Cloud Practitioner",
            issuer="Example Cloud",
            issued_date="2024",
            display_order=0,
        )
    ]
    return RenderJobInput(
        render_job_id=render_job_id,
        source_profile_id="profile-test-001",
        template_id="ats_standard",
        target_page_policy=TargetPagePolicy.PREFER_ONE_PAGE,
        layout_constraints=LayoutConstraints(max_lines=max_lines),
        personal_info=RenderPersonalInfo(
            full_name=personal_name,
            headline="Senior Backend Engineer",
            email="ada@example.com",
            location="Remote",
            links=["https://example.com/ada"],
        ),
        summary=RenderSummary(
            text=summary_text,
            provenance=RenderSourceProvenance(source_item_ids=[source_item_id]),
        ),
        experiences=[
            RenderExperience(
                id="experience-001",
                source_item_id=source_item_id,
                organization="Example Co",
                title="Senior Backend Engineer",
                start_date="2020",
                current=True,
                location="Remote",
                bullets=bullets,
                display_order=0,
                confidence=ConfidenceMetadata(confidence_score=0.95),
            )
        ],
        projects=projects,
        skills=[
            RenderSkillGroup(
                id="skills-001",
                label="Languages",
                skills=skill_values or ["Python", "SQL", "LaTeX"],
                display_order=0,
            )
        ],
        education=education,
        certifications=certifications,
        sections=base_sections(include_optional_empty=include_optional_empty),
        section_visibility={
            RenderSectionType.PROJECTS: not include_optional_empty,
            RenderSectionType.CERTIFICATIONS: not include_optional_empty,
        }
        if include_optional_empty
        else {},
    )


@pytest.fixture()
def normal_resume() -> RenderJobInput:
    return make_render_input()


@pytest.fixture()
def special_character_resume() -> RenderJobInput:
    return make_render_input(
        render_job_id="render-special-001",
        personal_name="Ada_Dev & Co",
        summary_text="Built APIs with 99% uptime & $0 incidents in C#.",
        bullet_texts=[
            "Owned Python_ETL & reporting for 20% faster decisions.",
            "Reduced cost from $5k to $3k while preserving C# services.",
        ],
    )


@pytest.fixture()
def unicode_resume() -> RenderJobInput:
    return make_render_input(
        render_job_id="render-unicode-001",
        personal_name="Zoë Nguyễn",
        summary_text="Built résumé tooling for São Paulo and München teams.",
        bullet_texts=["Led café analytics rollout across München and Zürich."],
    )


@pytest.fixture()
def long_bullet_resume() -> RenderJobInput:
    long_bullets = [
        " ".join([f"Long verified impact statement {index}"] * 14)
        for index in range(8)
    ]
    return make_render_input(
        render_job_id="render-long-001",
        summary_text=" ".join(["Verified summary detail"] * 40),
        bullet_texts=long_bullets,
        project_count=4,
        skill_values=["Python", "SQL", "FastAPI", "PostgreSQL", "LaTeX"],
        max_lines=20,
    )


@pytest.fixture()
def empty_optional_resume() -> RenderJobInput:
    return make_render_input(
        render_job_id="render-empty-optional-001",
        include_optional_empty=True,
        project_count=0,
    )
