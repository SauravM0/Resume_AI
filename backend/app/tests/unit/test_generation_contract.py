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

from resume_optimizer.generation.contracts import (
    BulletRewriteOutput,
    FullGenerationContext,
    GenerationQualitySignals,
    GenerationSectionType,
    GenerationStyleMode,
    PageConstraints,
    ParsedJobOutput,
    PlannedSection,
    PlannedSectionItem,
    SectionAssemblyInput,
    SelectedBulletEvidence,
    SelectedEvidence,
    SelectedExperienceEvidence,
    SelectedProjectEvidence,
    SelectedSkillEvidence,
    SkillGroupPresentation,
    SkillPresentationOutput,
    StoryFocusMode,
    StoryStrategy,
    StylePolicy,
    SummaryGenerationInput,
    SummaryGenerationOutput,
)
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


def _valid_context() -> FullGenerationContext:
    return FullGenerationContext(
        context_id="ctx.test",
        source_profile_id="profile.test",
        parsed_job_output=ParsedJobOutput(
            job_analysis_id="job.test",
            target_role_title="Senior Backend Engineer",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            functional_role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            must_have_skills=["Python", "AWS"],
            must_have_requirements=["Build backend APIs"],
            action_verbs=["build", "improve"],
        ),
        selected_evidence=SelectedEvidence(
            experiences=[
                SelectedExperienceEvidence(
                    source_item_id="exp.1",
                    evidence_unit_ids=["ev.exp.1"],
                    relevance_score=0.92,
                    organization="Acme",
                    title="Backend Engineer",
                    start_date=PartialDate(raw_value="2023-01"),
                    current=True,
                    bullets=[
                        SelectedBulletEvidence(
                            bullet_id="bullet.exp.1",
                            source_item_id="exp.1",
                            text="Built backend APIs in Python.",
                            evidence_unit_ids=["ev.exp.1"],
                            tools=["Python"],
                            evidence_strength=EvidenceStrength.STRONG,
                            verified_status=VerifiedStatus.CORROBORATED,
                        )
                    ],
                )
            ],
            projects=[
                SelectedProjectEvidence(
                    source_item_id="proj.1",
                    evidence_unit_ids=["ev.proj.1"],
                    relevance_score=0.74,
                    name="Platform Migration",
                    role="Lead Engineer",
                    bullets=[
                        SelectedBulletEvidence(
                            bullet_id="bullet.proj.1",
                            source_item_id="proj.1",
                            text="Migrated services to AWS.",
                            evidence_unit_ids=["ev.proj.1"],
                            tools=["AWS"],
                            evidence_strength=EvidenceStrength.STRONG,
                            verified_status=VerifiedStatus.CORROBORATED,
                        )
                    ],
                )
            ],
            skills=[
                SelectedSkillEvidence(
                    source_item_id="skill.1",
                    evidence_unit_ids=["ev.skill.1"],
                    relevance_score=0.9,
                    skill_name="Python",
                    evidence_strength=EvidenceStrength.STRONG,
                    verified_status=VerifiedStatus.CORROBORATED,
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
                        selected_bullet_ids=["bullet.exp.1"],
                        rationale="Anchor experience.",
                    )
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
                        selected_bullet_ids=["bullet.proj.1"],
                        rationale="Supporting project.",
                    )
                ],
            ),
            PlannedSection(
                section_id="section.skills",
                section_type=GenerationSectionType.SKILLS,
                title="Skills",
                items=[
                    PlannedSectionItem(
                        source_item_id="skill.1",
                        source_item_type=ItemType.SKILL,
                        rationale="Matched core skill.",
                    )
                ],
            ),
        ],
        story_strategy=StoryStrategy(
            strategy_id="story.1",
            focus_mode=StoryFocusMode.EXPERIENCE_FORWARD,
            target_role_title="Senior Backend Engineer",
            narrative_anchor="Backend delivery and reliability",
            summary_themes=["backend systems", "delivery reliability"],
        ),
        page_constraints=PageConstraints(target_page_count=1),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
    )


def test_valid_generation_input_shape() -> None:
    context = _valid_context()

    assert context.parsed_job_output.functional_role_family is FunctionalRoleFamily.BACKEND
    assert context.style_policy.style_mode is GenerationStyleMode.ATS_BALANCED
    assert len(context.section_plan) == 4


def test_missing_required_fields_fail_validation() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SummaryGenerationInput.model_validate(
            {
                "context_id": "ctx.test",
                "source_profile_id": "profile.test",
                "parsed_job_output": _valid_context().parsed_job_output.model_dump(mode="json"),
                "story_strategy": _valid_context().story_strategy.model_dump(mode="json"),
                "page_constraints": _valid_context().page_constraints.model_dump(mode="json"),
                "style_policy": _valid_context().style_policy.model_dump(mode="json"),
                "experiences": [],
                "projects": [],
                "skills": [],
            }
        )

    assert "section_id" in str(exc_info.value)


def test_invalid_role_family_and_style_values_fail_validation() -> None:
    payload = _valid_context().model_dump(mode="json")
    payload["parsed_job_output"]["functional_role_family"] = "invalid_family"
    with pytest.raises(ValidationError):
        FullGenerationContext.model_validate(payload)

    style_payload = _valid_context().style_policy.model_dump(mode="json")
    style_payload["style_mode"] = "loud_and_vague"
    with pytest.raises(ValidationError):
        StylePolicy.model_validate(style_payload)


def test_invalid_provenance_references_fail_validation() -> None:
    payload = _valid_context().model_dump(mode="json")
    payload["section_plan"][1]["items"][0]["selected_bullet_ids"] = ["missing.bullet"]

    with pytest.raises(ValidationError) as exc_info:
        FullGenerationContext.model_validate(payload)

    assert "unknown bullet ids" in str(exc_info.value)


def test_invalid_section_assembly_payloads_fail_validation() -> None:
    context = _valid_context()

    with pytest.raises(ValidationError) as exc_info:
        SectionAssemblyInput(
            context_id=context.context_id,
            source_profile_id=context.source_profile_id,
            section_plan=context.section_plan,
            summary_output=SummaryGenerationOutput(
                section_id="section.summary",
                summary_text="Backend engineer with Python experience.",
                source_item_ids=["exp.1"],
                source_bullet_ids=["bullet.exp.1"],
                evidence_ids_used=["ev.exp.1"],
                themes_used=["backend APIs"],
                warnings=[],
                quality_signals=GenerationQualitySignals(),
                role_family=FunctionalRoleFamily.BACKEND,
                organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
                style_mode=GenerationStyleMode.ATS_BALANCED,
            ),
            bullet_outputs=[
                BulletRewriteOutput(
                    section_id="section.experience",
                    source_item_id="exp.unknown",
                    source_item_type=ItemType.EXPERIENCE,
                    source_bullet_id="bullet.exp.1",
                    rewritten_text="Built backend APIs in Python.",
                    evidence_ids_used=["ev.exp.1"],
                    warnings=[],
                    rewrite_quality_signals=GenerationQualitySignals(),
                    rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
                    role_family=FunctionalRoleFamily.BACKEND,
                    organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
                    style_mode=GenerationStyleMode.ATS_BALANCED,
                )
            ],
            skill_presentation_output=SkillPresentationOutput(
                section_id="section.skills",
                grouped_skills=[
                    SkillGroupPresentation(
                        group_id="group.skills.1",
                        label="Skills",
                        skill_names=["Python"],
                        source_item_ids=["skill.1"],
                    )
                ],
                rendered_skill_lines=["Skills: Python"],
                warnings=[],
                quality_signals=GenerationQualitySignals(),
                role_family=FunctionalRoleFamily.BACKEND,
                organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
                style_mode=GenerationStyleMode.ATS_BALANCED,
            ),
            quality_signals=GenerationQualitySignals(),
        )

    assert "not present in section_plan" in str(exc_info.value)
