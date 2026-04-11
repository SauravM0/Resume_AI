from __future__ import annotations

from resume_optimizer.generation.contracts import (
    GenerationStyleMode,
    PageConstraints,
    ParsedJobOutput,
    StoryFocusMode,
    StoryStrategy,
    StylePolicy,
    SummaryGenerationInput,
)
from resume_optimizer.models import (
    EvidenceStrength,
    PartialDate,
    RoleType,
    SeniorityLevel,
    VerifiedStatus,
)
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from resume_optimizer.generation.contracts import (
    SelectedBulletEvidence,
    SelectedExperienceEvidence,
    SelectedProjectEvidence,
    SelectedSkillEvidence,
)


def backend_senior_ic_case() -> SummaryGenerationInput:
    return SummaryGenerationInput(
        context_id="ctx.summary.backend",
        source_profile_id="profile.backend",
        section_id="section.summary",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.backend",
            target_role_title="Senior Backend Engineer",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            functional_role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            industry_domain="platform infrastructure",
            must_have_skills=["Python", "AWS"],
            must_have_requirements=["backend APIs", "reliability"],
            action_verbs=["build", "improve"],
        ),
        story_strategy=StoryStrategy(
            strategy_id="story.backend",
            focus_mode=StoryFocusMode.EXPERIENCE_FORWARD,
            target_role_title="Senior Backend Engineer",
            narrative_anchor="backend systems and reliability",
            summary_themes=["backend APIs", "reliability"],
        ),
        page_constraints=PageConstraints(target_page_count=1, max_summary_sentences=2),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
        experiences=[
            SelectedExperienceEvidence(
                source_item_id="exp.backend.1",
                evidence_unit_ids=["ev.backend.1"],
                relevance_score=0.95,
                organization="Acme",
                title="Senior Backend Engineer",
                start_date=PartialDate(raw_value="2022-01"),
                current=True,
                tools=["Python", "AWS"],
                bullets=[
                    SelectedBulletEvidence(
                        bullet_id="bullet.backend.1",
                        source_item_id="exp.backend.1",
                        text="Built Python APIs and improved service reliability on AWS.",
                        evidence_unit_ids=["ev.backend.1"],
                        tools=["Python", "AWS"],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    )
                ],
            )
        ],
        skills=[
            SelectedSkillEvidence(
                source_item_id="skill.backend.python",
                evidence_unit_ids=["ev.skill.python"],
                relevance_score=0.9,
                skill_name="Python",
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            ),
            SelectedSkillEvidence(
                source_item_id="skill.backend.aws",
                evidence_unit_ids=["ev.skill.aws"],
                relevance_score=0.88,
                skill_name="AWS",
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            ),
        ],
    )


def frontend_lead_case() -> SummaryGenerationInput:
    return SummaryGenerationInput(
        context_id="ctx.summary.frontend",
        source_profile_id="profile.frontend",
        section_id="section.summary",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.frontend",
            target_role_title="Frontend Lead",
            role_type=RoleType.LEAD,
            seniority_level=SeniorityLevel.STAFF,
            functional_role_family=FunctionalRoleFamily.FRONTEND,
            organizational_role_mode=OrganizationalRoleMode.TECH_LEAD,
            industry_domain="consumer web",
            must_have_skills=["React", "TypeScript"],
            must_have_requirements=["design systems", "frontend architecture"],
        ),
        story_strategy=StoryStrategy(
            strategy_id="story.frontend",
            focus_mode=StoryFocusMode.EXPERIENCE_FORWARD,
            summary_themes=["design systems", "frontend architecture"],
        ),
        page_constraints=PageConstraints(target_page_count=1, max_summary_sentences=2),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.DIRECT),
        experiences=[
            SelectedExperienceEvidence(
                source_item_id="exp.frontend.1",
                evidence_unit_ids=["ev.frontend.1"],
                relevance_score=0.93,
                organization="Pixel",
                title="Frontend Lead",
                start_date=PartialDate(raw_value="2021-03"),
                current=True,
                tools=["React", "TypeScript"],
                bullets=[
                    SelectedBulletEvidence(
                        bullet_id="bullet.frontend.1",
                        source_item_id="exp.frontend.1",
                        text="Led frontend architecture and design system work in React and TypeScript.",
                        evidence_unit_ids=["ev.frontend.1"],
                        tools=["React", "TypeScript"],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    )
                ],
            )
        ],
        skills=[
            SelectedSkillEvidence(
                source_item_id="skill.frontend.react",
                evidence_unit_ids=["ev.skill.react"],
                relevance_score=0.92,
                skill_name="React",
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            ),
            SelectedSkillEvidence(
                source_item_id="skill.frontend.ts",
                evidence_unit_ids=["ev.skill.ts"],
                relevance_score=0.9,
                skill_name="TypeScript",
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            ),
        ],
    )


def data_role_case() -> SummaryGenerationInput:
    return SummaryGenerationInput(
        context_id="ctx.summary.data",
        source_profile_id="profile.data",
        section_id="section.summary",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.data",
            target_role_title="Data Engineer",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            functional_role_family=FunctionalRoleFamily.DATA,
            organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
            industry_domain="data platform",
            must_have_skills=["Python", "Snowflake"],
            must_have_requirements=["data pipelines", "etl"],
        ),
        story_strategy=StoryStrategy(
            strategy_id="story.data",
            focus_mode=StoryFocusMode.BALANCED,
            summary_themes=["data pipelines", "etl"],
        ),
        page_constraints=PageConstraints(target_page_count=1, max_summary_sentences=2),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.CONSERVATIVE),
        experiences=[
            SelectedExperienceEvidence(
                source_item_id="exp.data.1",
                evidence_unit_ids=["ev.data.1"],
                relevance_score=0.91,
                organization="DataCo",
                title="Data Engineer",
                start_date=PartialDate(raw_value="2020-05"),
                current=True,
                tools=["Python", "Snowflake"],
                bullets=[
                    SelectedBulletEvidence(
                        bullet_id="bullet.data.1",
                        source_item_id="exp.data.1",
                        text="Built ETL pipelines in Python and Snowflake for the data platform.",
                        evidence_unit_ids=["ev.data.1"],
                        tools=["Python", "Snowflake"],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    )
                ],
            )
        ],
    )


def management_role_case() -> SummaryGenerationInput:
    return SummaryGenerationInput(
        context_id="ctx.summary.mgmt",
        source_profile_id="profile.mgmt",
        section_id="section.summary",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.mgmt",
            target_role_title="Engineering Manager",
            role_type=RoleType.MANAGER,
            seniority_level=SeniorityLevel.DIRECTOR,
            functional_role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.PEOPLE_MANAGER,
            industry_domain="developer platform",
            must_have_skills=["Python", "AWS"],
            must_have_requirements=["team leadership", "platform reliability"],
        ),
        story_strategy=StoryStrategy(
            strategy_id="story.mgmt",
            focus_mode=StoryFocusMode.EXPERIENCE_FORWARD,
            summary_themes=["platform reliability"],
        ),
        page_constraints=PageConstraints(target_page_count=1, max_summary_sentences=2),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
        experiences=[
            SelectedExperienceEvidence(
                source_item_id="exp.mgmt.1",
                evidence_unit_ids=["ev.mgmt.1"],
                relevance_score=0.94,
                organization="ScaleCo",
                title="Engineering Manager",
                start_date=PartialDate(raw_value="2019-01"),
                current=True,
                tools=["Python", "AWS"],
                bullets=[
                    SelectedBulletEvidence(
                        bullet_id="bullet.mgmt.1",
                        source_item_id="exp.mgmt.1",
                        text="Managed backend engineers and improved platform reliability with Python services on AWS.",
                        evidence_unit_ids=["ev.mgmt.1"],
                        tools=["Python", "AWS"],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    )
                ],
            )
        ],
        projects=[
            SelectedProjectEvidence(
                source_item_id="proj.mgmt.1",
                evidence_unit_ids=["ev.mgmt.proj.1"],
                relevance_score=0.7,
                name="Platform Reliability Program",
                role="Manager",
                tools=["AWS"],
                bullets=[
                    SelectedBulletEvidence(
                        bullet_id="bullet.mgmt.proj.1",
                        source_item_id="proj.mgmt.1",
                        text="Led a platform reliability program across backend services.",
                        evidence_unit_ids=["ev.mgmt.proj.1"],
                        tools=["AWS"],
                        evidence_strength=EvidenceStrength.MODERATE,
                        verified_status=VerifiedStatus.CORROBORATED,
                    )
                ],
            )
        ],
    )
