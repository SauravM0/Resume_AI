from __future__ import annotations

from resume_optimizer.generation.contracts import (
    BulletRewriteOutput,
    FullGenerationContext,
    GenerationQualitySignals,
    GenerationSectionType,
    GenerationStyleMode,
    ParsedJobOutput,
    PlannedSection,
    PlannedSectionItem,
    SelectedBulletEvidence,
    SelectedCertificationEvidence,
    SelectedEvidence,
    SelectedExperienceEvidence,
    SelectedProjectEvidence,
    SelectedSkillEvidence,
    SkillGroupPresentation,
    SkillPresentationOutput,
    StoryFocusMode,
    StoryStrategy,
    StylePolicy,
    SummaryGenerationOutput,
)
from resume_optimizer.generation.mappers import build_section_assembly_input
from resume_optimizer.models import (
    EvidenceStrength,
    ItemType,
    PartialDate,
    RoleType,
    SeniorityLevel,
    VerifiedStatus,
)
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from resume_optimizer.phase3_models import BulletRewriteStrategy


def experience_heavy_case() -> tuple[FullGenerationContext, object]:
    context = _base_context(target_page_count=1)
    assembly_input = build_section_assembly_input(
        context,
        summary_output=_summary_output(),
        bullet_outputs=[
            *_experience_bullet_outputs("section.experience", "exp.1", ["exp.1.b1", "exp.1.b2", "exp.1.b3"]),
            *_experience_bullet_outputs("section.experience", "exp.2", ["exp.2.b1", "exp.2.b2", "exp.2.b3"]),
            *_experience_bullet_outputs("section.experience", "exp.3", ["exp.3.b1", "exp.3.b2", "exp.3.b3"]),
            *_project_bullet_outputs("section.projects", "proj.1", ["proj.1.b1"]),
        ],
        skill_presentation_output=_skill_output(),
    )
    return context, assembly_input


def project_heavy_case() -> tuple[FullGenerationContext, object]:
    context = _base_context(target_page_count=1)
    context = context.model_copy(
        update={
            "section_plan": [
                context.section_plan[0],
                PlannedSection(
                    section_id="section.projects",
                    section_type=GenerationSectionType.PROJECTS,
                    title="Projects",
                    items=[
                        PlannedSectionItem(
                            source_item_id="proj.1",
                            source_item_type=ItemType.PROJECT,
                            selected_bullet_ids=["proj.1.b1", "proj.1.b2"],
                            rationale="Primary project evidence",
                        ),
                        PlannedSectionItem(
                            source_item_id="proj.2",
                            source_item_type=ItemType.PROJECT,
                            selected_bullet_ids=["proj.2.b1", "proj.2.b2"],
                            rationale="Secondary project evidence",
                        ),
                    ],
                ),
                PlannedSection(
                    section_id="section.skills",
                    section_type=GenerationSectionType.SKILLS,
                    title="Skills",
                    items=[
                        PlannedSectionItem(
                            source_item_id="skill.python",
                            source_item_type=ItemType.SKILL,
                            rationale="Core skill",
                        )
                    ],
                ),
            ]
        }
    )
    assembly_input = build_section_assembly_input(
        context,
        summary_output=_summary_output(),
        bullet_outputs=[
            *_project_bullet_outputs("section.projects", "proj.1", ["proj.1.b1", "proj.1.b2"]),
            *_project_bullet_outputs("section.projects", "proj.2", ["proj.2.b1", "proj.2.b2"]),
        ],
        skill_presentation_output=_skill_output(),
    )
    return context, assembly_input


def certification_relevant_case() -> tuple[FullGenerationContext, object]:
    context = _base_context(target_page_count=1)
    assembly_input = build_section_assembly_input(
        context,
        summary_output=_summary_output(),
        bullet_outputs=[*_experience_bullet_outputs("section.experience", "exp.1", ["exp.1.b1", "exp.1.b2"])],
        skill_presentation_output=_skill_output(),
    )
    return context, assembly_input


def one_page_constrained_case() -> tuple[FullGenerationContext, object]:
    return experience_heavy_case()


def two_page_allowed_case() -> tuple[FullGenerationContext, object]:
    context, assembly_input = experience_heavy_case()
    expanded_context = context.model_copy(
        update={"page_constraints": context.page_constraints.model_copy(update={"target_page_count": 2})}
    )
    expanded_input = build_section_assembly_input(
        expanded_context,
        summary_output=assembly_input.summary_output,
        bullet_outputs=assembly_input.bullet_outputs,
        skill_presentation_output=assembly_input.skill_presentation_output,
    )
    return expanded_context, expanded_input


def omitted_item_tracking_case() -> tuple[FullGenerationContext, object]:
    context, _assembly_input = experience_heavy_case()
    assembly_input = build_section_assembly_input(
        context,
        summary_output=_summary_output(),
        bullet_outputs=[
            *_experience_bullet_outputs("section.experience", "exp.1", ["exp.1.b1", "exp.1.b2"]),
        ],
        skill_presentation_output=_skill_output(),
    )
    return context, assembly_input


def _base_context(*, target_page_count: int) -> FullGenerationContext:
    return FullGenerationContext(
        context_id="ctx.assembly",
        source_profile_id="profile.assembly",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.assembly",
            target_role_title="Senior Backend Engineer",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            functional_role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            must_have_skills=["Python", "AWS", "PostgreSQL"],
        ),
        selected_evidence=SelectedEvidence(
            experiences=[
                _experience("exp.1", "Senior Backend Engineer", "Acme", 0.98, 3),
                _experience("exp.2", "Backend Engineer", "Beta", 0.94, 3),
                _experience("exp.3", "Software Engineer", "Gamma", 0.88, 3),
            ],
            projects=[
                _project("proj.1", "Platform Migration", 0.8, 2),
                _project("proj.2", "Developer Portal", 0.74, 2),
            ],
            skills=[
                _skill("skill.python", "Python", 0.95),
                _skill("skill.aws", "AWS", 0.91),
            ],
            certifications=[
                SelectedCertificationEvidence(
                    source_item_id="cert.1",
                    evidence_unit_ids=["ev.cert.1"],
                    relevance_score=0.8,
                    name="AWS Certified Developer",
                    issuer="Amazon Web Services",
                    issue_date=PartialDate(raw_value="2024-06"),
                )
            ],
        ),
        section_plan=[
            PlannedSection(
                section_id="section.summary",
                section_type=GenerationSectionType.SUMMARY,
                title="Summary",
            ),
            PlannedSection(
                section_id="section.experience",
                section_type=GenerationSectionType.EXPERIENCE,
                title="Experience",
                items=[
                    PlannedSectionItem(
                        source_item_id="exp.1",
                        source_item_type=ItemType.EXPERIENCE,
                        selected_bullet_ids=["exp.1.b1", "exp.1.b2", "exp.1.b3"],
                        rationale="Top experience",
                    ),
                    PlannedSectionItem(
                        source_item_id="exp.2",
                        source_item_type=ItemType.EXPERIENCE,
                        selected_bullet_ids=["exp.2.b1", "exp.2.b2", "exp.2.b3"],
                        rationale="Supporting experience",
                    ),
                    PlannedSectionItem(
                        source_item_id="exp.3",
                        source_item_type=ItemType.EXPERIENCE,
                        selected_bullet_ids=["exp.3.b1", "exp.3.b2", "exp.3.b3"],
                        rationale="Additional experience",
                    ),
                ],
            ),
            PlannedSection(
                section_id="section.projects",
                section_type=GenerationSectionType.PROJECTS,
                title="Projects",
                items=[
                    PlannedSectionItem(
                        source_item_id="proj.1",
                        source_item_type=ItemType.PROJECT,
                        selected_bullet_ids=["proj.1.b1"],
                        rationale="Supporting project",
                    )
                ],
            ),
            PlannedSection(
                section_id="section.skills",
                section_type=GenerationSectionType.SKILLS,
                title="Skills",
                items=[
                    PlannedSectionItem(
                        source_item_id="skill.python",
                        source_item_type=ItemType.SKILL,
                        rationale="Core skill",
                    ),
                    PlannedSectionItem(
                        source_item_id="skill.aws",
                        source_item_type=ItemType.SKILL,
                        rationale="Core skill",
                    ),
                ],
            ),
            PlannedSection(
                section_id="section.certifications",
                section_type=GenerationSectionType.CERTIFICATIONS,
                title="Certifications",
                items=[
                    PlannedSectionItem(
                        source_item_id="cert.1",
                        source_item_type=ItemType.CERTIFICATION,
                        rationale="Relevant certification",
                    )
                ],
            ),
        ],
        story_strategy=StoryStrategy(
            strategy_id="story.assembly",
            focus_mode=StoryFocusMode.EXPERIENCE_FORWARD,
            summary_themes=["backend systems", "reliability"],
        ),
        page_constraints={"target_page_count": target_page_count},
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
    )


def _experience(
    source_item_id: str,
    title: str,
    organization: str,
    relevance_score: float,
    bullet_count: int,
) -> SelectedExperienceEvidence:
    bullets = [
        SelectedBulletEvidence(
            bullet_id=f"{source_item_id}.b{index}",
            source_item_id=source_item_id,
            text=f"Delivered backend work {index} in Python on AWS.",
            evidence_unit_ids=[f"ev.{source_item_id}.{index}"],
            tools=["Python", "AWS"],
            evidence_strength=EvidenceStrength.STRONG,
            verified_status=VerifiedStatus.CORROBORATED,
        )
        for index in range(1, bullet_count + 1)
    ]
    return SelectedExperienceEvidence(
        source_item_id=source_item_id,
        evidence_unit_ids=[f"ev.{source_item_id}"],
        relevance_score=relevance_score,
        organization=organization,
        title=title,
        start_date=PartialDate(raw_value="2022-01"),
        current=True,
        tools=["Python", "AWS"],
        bullets=bullets,
    )


def _project(source_item_id: str, name: str, relevance_score: float, bullet_count: int) -> SelectedProjectEvidence:
    bullets = [
        SelectedBulletEvidence(
            bullet_id=f"{source_item_id}.b{index}",
            source_item_id=source_item_id,
            text=f"Built project capability {index} with Python and AWS.",
            evidence_unit_ids=[f"ev.{source_item_id}.{index}"],
            tools=["Python", "AWS"],
            evidence_strength=EvidenceStrength.STRONG,
            verified_status=VerifiedStatus.CORROBORATED,
        )
        for index in range(1, bullet_count + 1)
    ]
    return SelectedProjectEvidence(
        source_item_id=source_item_id,
        evidence_unit_ids=[f"ev.{source_item_id}"],
        relevance_score=relevance_score,
        name=name,
        role="Engineer",
        tools=["Python", "AWS"],
        bullets=bullets,
    )


def _skill(source_item_id: str, name: str, relevance_score: float) -> SelectedSkillEvidence:
    return SelectedSkillEvidence(
        source_item_id=source_item_id,
        evidence_unit_ids=[f"ev.{source_item_id}"],
        relevance_score=relevance_score,
        skill_name=name,
        evidence_strength=EvidenceStrength.STRONG,
        verified_status=VerifiedStatus.CORROBORATED,
    )


def _summary_output() -> SummaryGenerationOutput:
    return SummaryGenerationOutput(
        section_id="section.summary",
        summary_text="Backend engineer with experience building Python services on AWS.",
        source_item_ids=["exp.1"],
        source_bullet_ids=["exp.1.b1"],
        evidence_ids_used=["ev.exp.1.1"],
        themes_used=["backend systems"],
        warnings=[],
        quality_signals=GenerationQualitySignals(),
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
        style_mode=GenerationStyleMode.ATS_BALANCED,
    )


def _skill_output() -> SkillPresentationOutput:
    return SkillPresentationOutput(
        section_id="section.skills",
        grouped_skills=[
            SkillGroupPresentation(
                group_id="group.skills.1",
                label="Languages",
                skill_names=["Python"],
                source_item_ids=["skill.python"],
            ),
            SkillGroupPresentation(
                group_id="group.skills.2",
                label="Cloud/Platforms",
                skill_names=["AWS"],
                source_item_ids=["skill.aws"],
            ),
        ],
        rendered_skill_lines=["Languages: Python", "Cloud/Platforms: AWS"],
        warnings=[],
        quality_signals=GenerationQualitySignals(),
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
        style_mode=GenerationStyleMode.ATS_BALANCED,
    )


def _experience_bullet_outputs(section_id: str, source_item_id: str, bullet_ids: list[str]) -> list[BulletRewriteOutput]:
    return [
        BulletRewriteOutput(
            section_id=section_id,
            source_item_id=source_item_id,
            source_item_type=ItemType.EXPERIENCE,
            source_bullet_id=bullet_id,
            rewritten_text=f"Rewritten {bullet_id}.",
            evidence_ids_used=[f"ev.{bullet_id}"],
            warnings=[],
            rewrite_quality_signals=GenerationQualitySignals(),
            rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
            role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            style_mode=GenerationStyleMode.ATS_BALANCED,
        )
        for bullet_id in bullet_ids
    ]


def _project_bullet_outputs(section_id: str, source_item_id: str, bullet_ids: list[str]) -> list[BulletRewriteOutput]:
    return [
        BulletRewriteOutput(
            section_id=section_id,
            source_item_id=source_item_id,
            source_item_type=ItemType.PROJECT,
            source_bullet_id=bullet_id,
            rewritten_text=f"Rewritten {bullet_id}.",
            evidence_ids_used=[f"ev.{bullet_id}"],
            warnings=[],
            rewrite_quality_signals=GenerationQualitySignals(),
            rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
            role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            style_mode=GenerationStyleMode.ATS_BALANCED,
        )
        for bullet_id in bullet_ids
    ]
