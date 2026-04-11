from __future__ import annotations

from resume_optimizer.generation.contracts import (
    GenerationStyleMode,
    PageConstraints,
    ParsedJobOutput,
    SkillPresentationInput,
    StoryFocusMode,
    StoryStrategy,
    StylePolicy,
    SelectedSkillEvidence,
)
from resume_optimizer.models import EvidenceStrength, RoleType, SeniorityLevel, VerifiedStatus
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode


def backend_heavy_skill_case() -> SkillPresentationInput:
    return SkillPresentationInput(
        context_id="ctx.skills.backend",
        source_profile_id="profile.skills.backend",
        section_id="section.skills",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.skills.backend",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            functional_role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            must_have_skills=["Python", "AWS", "PostgreSQL"],
            preferred_skills=["Kafka"],
        ),
        story_strategy=StoryStrategy(strategy_id="story.skills.backend", focus_mode=StoryFocusMode.EXPERIENCE_FORWARD),
        page_constraints=PageConstraints(target_page_count=1, max_skill_groups=3, max_skills_per_group=4),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
        selected_skills=[
            _skill("skill.python", "Python", 0.95),
            _skill("skill.js", "JavaScript", 0.6),
            _skill("skill.aws", "AWS", 0.92),
            _skill("skill.postgres", "Postgres", 0.9),
            _skill("skill.kafka", "Kafka", 0.83),
            _skill("skill.node", "Node", 0.55),
        ],
    )


def frontend_heavy_skill_case() -> SkillPresentationInput:
    return SkillPresentationInput(
        context_id="ctx.skills.frontend",
        source_profile_id="profile.skills.frontend",
        section_id="section.skills",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.skills.frontend",
            role_type=RoleType.LEAD,
            seniority_level=SeniorityLevel.STAFF,
            functional_role_family=FunctionalRoleFamily.FRONTEND,
            organizational_role_mode=OrganizationalRoleMode.TECH_LEAD,
            must_have_skills=["React", "TypeScript"],
            preferred_skills=["Storybook"],
        ),
        story_strategy=StoryStrategy(strategy_id="story.skills.frontend", focus_mode=StoryFocusMode.EXPERIENCE_FORWARD),
        page_constraints=PageConstraints(target_page_count=1, max_skill_groups=2, max_skills_per_group=4),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.DIRECT),
        selected_skills=[
            _skill("skill.react", "ReactJS", 0.96),
            _skill("skill.ts", "TS", 0.94),
            _skill("skill.storybook", "Storybook", 0.82),
            _skill("skill.js", "JS", 0.7),
            _skill("skill.next", "Next.js", 0.89),
        ],
    )


def fullstack_hybrid_skill_case() -> SkillPresentationInput:
    return SkillPresentationInput(
        context_id="ctx.skills.fullstack",
        source_profile_id="profile.skills.fullstack",
        section_id="section.skills",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.skills.fullstack",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            functional_role_family=FunctionalRoleFamily.FULLSTACK,
            organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
            must_have_skills=["TypeScript", "React", "Node.js"],
            preferred_skills=["PostgreSQL"],
        ),
        story_strategy=StoryStrategy(strategy_id="story.skills.fullstack", focus_mode=StoryFocusMode.BALANCED),
        page_constraints=PageConstraints(target_page_count=1, max_skill_groups=3, max_skills_per_group=4),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
        selected_skills=[
            _skill("skill.react", "React", 0.93),
            _skill("skill.ts", "TypeScript", 0.94),
            _skill("skill.node", "Node.js", 0.92),
            _skill("skill.postgres", "PostgreSQL", 0.84),
            _skill("skill.aws", "Amazon Web Services", 0.8),
        ],
    )


def data_analytics_skill_case() -> SkillPresentationInput:
    return SkillPresentationInput(
        context_id="ctx.skills.data",
        source_profile_id="profile.skills.data",
        section_id="section.skills",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.skills.data",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            functional_role_family=FunctionalRoleFamily.DATA,
            organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
            must_have_skills=["Python", "SQL", "Snowflake"],
            preferred_skills=["BigQuery"],
        ),
        story_strategy=StoryStrategy(strategy_id="story.skills.data", focus_mode=StoryFocusMode.SKILLS_FORWARD),
        page_constraints=PageConstraints(target_page_count=1, max_skill_groups=3, max_skills_per_group=4),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.CONSERVATIVE),
        selected_skills=[
            _skill("skill.python", "Python", 0.96),
            _skill("skill.sql", "SQL", 0.95),
            _skill("skill.snowflake", "Snowflake", 0.9),
            _skill("skill.bigquery", "BigQuery", 0.82),
            _skill("skill.etl", "ETL", 0.8),
        ],
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
