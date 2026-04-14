from __future__ import annotations

from resume_optimizer.generation.contracts import (
    AssembledBulletLine,
    AssembledExperienceItem,
    AssembledExperienceSection,
    AssembledSkillSection,
    AssembledSummary,
    AssemblyBudgetSignals,
    BulletRewriteOutput,
    GenerationQualitySignals,
    GenerationStyleMode,
    SectionAssemblyOutput,
    SkillGroupPresentation,
    SkillPresentationOutput,
    SummaryGenerationOutput,
)
from resume_optimizer.models import ItemType
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from resume_optimizer.phase3_models import BulletRewriteStrategy


def generic_bad_summary_case() -> SummaryGenerationOutput:
    return SummaryGenerationOutput(
        section_id="section.summary",
        summary_text="Results-driven dynamic professional with various experience.",
        source_item_ids=["exp.1"],
        source_bullet_ids=["exp.1.b1"],
        evidence_ids_used=["ev.exp.1"],
        themes_used=["delivery"],
        warnings=[],
        quality_signals=GenerationQualitySignals(),
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
        style_mode=GenerationStyleMode.ATS_BALANCED,
    )


def repeated_bullets_case() -> list[BulletRewriteOutput]:
    return [
        _bullet_output("exp.1.b1", "Built backend APIs in Python for backend services."),
        _bullet_output("exp.1.b2", "Built backend APIs in Python for backend services."),
    ]


def keyword_stuffed_bullets_case() -> list[BulletRewriteOutput]:
    return [
        _bullet_output(
            "exp.2.b1",
            "Built backend backend backend API platform platform services in Python Python on AWS AWS.",
        )
    ]


def oversized_skills_case() -> SkillPresentationOutput:
    return SkillPresentationOutput(
        section_id="section.skills",
        grouped_skills=[
            SkillGroupPresentation(
                group_id="group.skills.1",
                label="Languages",
                skill_names=["Python", "Java", "JavaScript", "TypeScript", "Go"],
                source_item_ids=["skill.1", "skill.2", "skill.3", "skill.4", "skill.5"],
            ),
            SkillGroupPresentation(
                group_id="group.skills.2",
                label="Tools",
                skill_names=["AWS", "Docker", "Kubernetes", "Terraform", "Datadog"],
                source_item_ids=["skill.6", "skill.7", "skill.8", "skill.9", "skill.10"],
            ),
            SkillGroupPresentation(
                group_id="group.skills.3",
                label="Databases",
                skill_names=["PostgreSQL", "Redis", "Snowflake"],
                source_item_ids=["skill.11", "skill.12", "skill.13"],
            ),
        ],
        rendered_skill_lines=[
            "Languages: Python | Java | JavaScript | TypeScript | Go",
            "Tools: AWS | Docker | Kubernetes | Terraform | Datadog",
            "Databases: PostgreSQL | Redis | Snowflake",
        ],
        warnings=[],
        quality_signals=GenerationQualitySignals(),
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
        style_mode=GenerationStyleMode.ATS_BALANCED,
    )


def high_quality_output_case() -> tuple[SummaryGenerationOutput, list[BulletRewriteOutput], SkillPresentationOutput, SectionAssemblyOutput]:
    summary = SummaryGenerationOutput(
        section_id="section.summary",
        summary_text="Backend engineer building Python services on AWS with a focus on reliability.",
        source_item_ids=["exp.1"],
        source_bullet_ids=["exp.1.b1"],
        evidence_ids_used=["ev.exp.1"],
        themes_used=["reliability"],
        warnings=[],
        quality_signals=GenerationQualitySignals(),
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
        style_mode=GenerationStyleMode.ATS_BALANCED,
    )
    bullets = [
        _bullet_output("exp.1.b1", "Built Python APIs on AWS, reducing latency by 35%."),
        _bullet_output("exp.1.b2", "Improved service reliability through targeted backend changes."),
    ]
    skills = SkillPresentationOutput(
        section_id="section.skills",
        grouped_skills=[
            SkillGroupPresentation(
                group_id="group.skills.1",
                label="Languages",
                skill_names=["Python"],
                source_item_ids=["skill.1"],
            ),
            SkillGroupPresentation(
                group_id="group.skills.2",
                label="Cloud/Platforms",
                skill_names=["AWS"],
                source_item_ids=["skill.2"],
            ),
        ],
        rendered_skill_lines=["Languages: Python", "Cloud/Platforms: AWS"],
        warnings=[],
        quality_signals=GenerationQualitySignals(),
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
        style_mode=GenerationStyleMode.ATS_BALANCED,
    )
    assembly = SectionAssemblyOutput(
        context_id="ctx.quality",
        source_profile_id="profile.quality",
        assembled_summary=AssembledSummary(
            section_id="section.summary",
            title="Summary",
            text=summary.summary_text,
        ),
        assembled_experience_sections=[
            AssembledExperienceSection(
                section_id="section.experience",
                title="Experience",
                items=[
                    AssembledExperienceItem(
                        source_item_id="exp.1",
                        title="Backend Engineer",
                        organization="Acme",
                        bullets=[
                            AssembledBulletLine(source_bullet_id="exp.1.b1", text=bullets[0].rewritten_text, evidence_ids_used=["ev.exp.1"]),
                            AssembledBulletLine(source_bullet_id="exp.1.b2", text=bullets[1].rewritten_text, evidence_ids_used=["ev.exp.2"]),
                        ],
                    )
                ],
            )
        ],
        assembled_project_sections=[],
        assembled_skill_section=AssembledSkillSection(
            section_id="section.skills",
            title="Skills",
            grouped_skills=skills.grouped_skills,
            rendered_skill_lines=skills.rendered_skill_lines,
        ),
        assembled_education_section=None,
        assembled_certification_section=None,
        omitted_items_with_reasons=[],
        assembly_warnings=[],
        budget_signals=AssemblyBudgetSignals(
            target_page_count=1,
            max_total_bullets=8,
            used_total_bullets=2,
            remaining_bullet_budget=6,
            within_budget=True,
            omitted_item_ids=[],
        ),
        quality_signals=GenerationQualitySignals(),
    )
    return summary, bullets, skills, assembly


def _bullet_output(source_bullet_id: str, text: str) -> BulletRewriteOutput:
    return BulletRewriteOutput(
        section_id="section.experience",
        source_item_id="exp.1",
        source_item_type=ItemType.EXPERIENCE,
        source_bullet_id=source_bullet_id,
        rewritten_text=text,
        evidence_ids_used=["ev." + source_bullet_id],
        warnings=[],
        rewrite_quality_signals=GenerationQualitySignals(),
        rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
        style_mode=GenerationStyleMode.ATS_BALANCED,
    )
