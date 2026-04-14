from __future__ import annotations

from resume_optimizer.generation.contracts import (
    BulletRewriteInput,
    GenerationStyleMode,
    PageConstraints,
    StoryFocusMode,
    StoryStrategy,
    StylePolicy,
    SelectedBulletEvidence,
)
from resume_optimizer.models import EvidenceStrength, ItemType, VerifiedStatus
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode


def metric_bullet_case() -> BulletRewriteInput:
    return BulletRewriteInput(
        context_id="ctx.rewrite.metric",
        source_profile_id="profile.metric",
        section_id="section.experience",
        source_item_id="exp.metric",
        source_item_type=ItemType.EXPERIENCE,
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
        story_strategy=StoryStrategy(strategy_id="story.metric", focus_mode=StoryFocusMode.EXPERIENCE_FORWARD),
        page_constraints=PageConstraints(target_page_count=1),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
        source_bullets=[
            SelectedBulletEvidence(
                bullet_id="bullet.metric.1",
                source_item_id="exp.metric",
                text="Built Python APIs that reduced latency by 35% on AWS.",
                evidence_unit_ids=["ev.metric.1"],
                tools=["Python", "AWS"],
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        evidence_unit_ids=["ev.metric.1"],
        requested_bullet_count=1,
    )


def non_metric_bullet_case() -> BulletRewriteInput:
    return BulletRewriteInput(
        context_id="ctx.rewrite.nonmetric",
        source_profile_id="profile.nonmetric",
        section_id="section.experience",
        source_item_id="exp.nonmetric",
        source_item_type=ItemType.EXPERIENCE,
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
        story_strategy=StoryStrategy(strategy_id="story.nonmetric", focus_mode=StoryFocusMode.BALANCED),
        page_constraints=PageConstraints(target_page_count=1),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.CONSERVATIVE),
        source_bullets=[
            SelectedBulletEvidence(
                bullet_id="bullet.nonmetric.1",
                source_item_id="exp.nonmetric",
                text="Maintained backend services for internal tooling.",
                evidence_unit_ids=["ev.nonmetric.1"],
                tools=["Python"],
                evidence_strength=EvidenceStrength.MODERATE,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        evidence_unit_ids=["ev.nonmetric.1"],
        requested_bullet_count=1,
    )


def vague_bullet_case() -> BulletRewriteInput:
    return BulletRewriteInput(
        context_id="ctx.rewrite.vague",
        source_profile_id="profile.vague",
        section_id="section.experience",
        source_item_id="exp.vague",
        source_item_type=ItemType.EXPERIENCE,
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
        story_strategy=StoryStrategy(strategy_id="story.vague", focus_mode=StoryFocusMode.BALANCED),
        page_constraints=PageConstraints(target_page_count=1),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.CONSERVATIVE),
        source_bullets=[
            SelectedBulletEvidence(
                bullet_id="bullet.vague.1",
                source_item_id="exp.vague",
                text="Helped with backend work.",
                evidence_unit_ids=["ev.vague.1"],
                evidence_strength=EvidenceStrength.WEAK,
                verified_status=VerifiedStatus.SELF_REPORTED,
            )
        ],
        evidence_unit_ids=["ev.vague.1"],
        requested_bullet_count=1,
    )


def backend_bullet_case() -> BulletRewriteInput:
    return metric_bullet_case()


def frontend_bullet_case() -> BulletRewriteInput:
    return BulletRewriteInput(
        context_id="ctx.rewrite.frontend",
        source_profile_id="profile.frontend",
        section_id="section.experience",
        source_item_id="exp.frontend",
        source_item_type=ItemType.EXPERIENCE,
        role_family=FunctionalRoleFamily.FRONTEND,
        organizational_role_mode=OrganizationalRoleMode.TECH_LEAD,
        story_strategy=StoryStrategy(strategy_id="story.frontend", focus_mode=StoryFocusMode.EXPERIENCE_FORWARD),
        page_constraints=PageConstraints(target_page_count=1),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.DIRECT),
        source_bullets=[
            SelectedBulletEvidence(
                bullet_id="bullet.frontend.1",
                source_item_id="exp.frontend",
                text="Led design system work in React and TypeScript for the web app.",
                evidence_unit_ids=["ev.frontend.1"],
                tools=["React", "TypeScript"],
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        evidence_unit_ids=["ev.frontend.1"],
        requested_bullet_count=1,
    )


def leadership_bullet_case() -> BulletRewriteInput:
    return BulletRewriteInput(
        context_id="ctx.rewrite.leadership",
        source_profile_id="profile.leadership",
        section_id="section.experience",
        source_item_id="exp.leadership",
        source_item_type=ItemType.EXPERIENCE,
        role_family=FunctionalRoleFamily.BACKEND,
        organizational_role_mode=OrganizationalRoleMode.PEOPLE_MANAGER,
        story_strategy=StoryStrategy(strategy_id="story.leadership", focus_mode=StoryFocusMode.EXPERIENCE_FORWARD),
        page_constraints=PageConstraints(target_page_count=1),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.ATS_BALANCED),
        source_bullets=[
            SelectedBulletEvidence(
                bullet_id="bullet.leadership.1",
                source_item_id="exp.leadership",
                text="Managed backend engineers while improving deployment reliability.",
                evidence_unit_ids=["ev.leadership.1"],
                tools=["Python"],
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        evidence_unit_ids=["ev.leadership.1"],
        requested_bullet_count=1,
    )


def devops_bullet_case() -> BulletRewriteInput:
    return BulletRewriteInput(
        context_id="ctx.rewrite.devops",
        source_profile_id="profile.devops",
        section_id="section.experience",
        source_item_id="exp.devops",
        source_item_type=ItemType.EXPERIENCE,
        role_family=FunctionalRoleFamily.DEVOPS,
        organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
        story_strategy=StoryStrategy(strategy_id="story.devops", focus_mode=StoryFocusMode.EXPERIENCE_FORWARD),
        page_constraints=PageConstraints(target_page_count=1),
        style_policy=StylePolicy(style_mode=GenerationStyleMode.DIRECT),
        source_bullets=[
            SelectedBulletEvidence(
                bullet_id="bullet.devops.1",
                source_item_id="exp.devops",
                text="Automated Terraform-based infrastructure deployments in AWS.",
                evidence_unit_ids=["ev.devops.1"],
                tools=["Terraform", "AWS"],
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        evidence_unit_ids=["ev.devops.1"],
        requested_bullet_count=1,
    )
