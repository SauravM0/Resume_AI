"""Mappers from current Phase 3 artifacts to the bounded generation contract."""

from __future__ import annotations

from .contracts import (
    BulletRewriteInput,
    BulletRewriteOutput,
    FullGenerationContext,
    GenerationSectionType,
    GenerationStyleMode,
    PageConstraints,
    ParsedJobOutput,
    PlannedSection,
    PlannedSectionItem,
    GenerationQualitySignals,
    SelectedBulletEvidence,
    SelectedCertificationEvidence,
    SelectedEvidence,
    SelectedExperienceEvidence,
    SelectedProjectEvidence,
    SelectedSkillEvidence,
    SectionAssemblyInput,
    SkillPresentationOutput,
    SkillPresentationInput,
    StoryFocusMode,
    StoryStrategy,
    StylePolicy,
    SummaryGenerationInput,
    SummaryGenerationOutput,
)
from ..job_models import NormalizedJobAnalysis
from ..models import ItemType
from ..phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from ..phase3_models import Phase3GenerationPayload
from ..phase3_section_planner import Phase3SectionPlan


def build_full_generation_context(
    *,
    context_id: str,
    source_profile_id: str,
    job_analysis: NormalizedJobAnalysis,
    generation_payload: Phase3GenerationPayload,
    section_plan: Phase3SectionPlan,
    functional_role_family: FunctionalRoleFamily = FunctionalRoleFamily.OTHER,
    organizational_role_mode: OrganizationalRoleMode = OrganizationalRoleMode.UNKNOWN,
    story_focus_mode: StoryFocusMode = StoryFocusMode.BALANCED,
    style_mode: GenerationStyleMode = GenerationStyleMode.ATS_BALANCED,
) -> FullGenerationContext:
    """Map current Phase 3 planning artifacts into the bounded generation contract."""

    parsed_job_output = ParsedJobOutput(
        job_analysis_id=f"job.{source_profile_id}",
        target_role_title=generation_payload.role_context.target_role_title,
        role_type=job_analysis.role_type,
        seniority_level=job_analysis.seniority_level,
        functional_role_family=functional_role_family,
        organizational_role_mode=organizational_role_mode,
        industry_domain=job_analysis.industry_domain,
        must_have_skills=list(generation_payload.role_context.must_have_skills),
        preferred_skills=list(generation_payload.role_context.preferred_skills),
        must_have_requirements=list(generation_payload.role_context.must_have_requirements),
        preferred_requirements=list(generation_payload.role_context.preferred_requirements),
        company_terminology=list(generation_payload.role_context.company_terminology),
        action_verbs=list(generation_payload.role_context.action_verbs),
    )
    selected_evidence = SelectedEvidence(
        experiences=[
            SelectedExperienceEvidence(
                source_item_id=item.id,
                evidence_unit_ids=list(item.evidence_unit_ids),
                relevance_score=item.relevance_score,
                matched_requirements=list(item.matched_requirements),
                selection_reason=item.selection_reason,
                supporting_evidence_ids=list(item.supporting_evidence_ids),
                score_factors=dict(item.score_factors),
                organization=item.organization,
                title=item.title,
                start_date=item.start_date,
                end_date=item.end_date,
                current=item.current,
                tools=list(item.tools),
                bullets=[
                    SelectedBulletEvidence(
                        bullet_id=bullet.id,
                        source_item_id=item.id,
                        text=bullet.text,
                        evidence_unit_ids=list(item.evidence_unit_ids),
                        metric_ids=list(bullet.metric_ids),
                        tools=list(bullet.tools),
                        evidence_strength=bullet.evidence_strength,
                        verified_status=bullet.verified_status,
                        rewrite_allowed=bullet.rewrite_allowed,
                    )
                    for bullet in item.bullets
                ],
            )
            for item in generation_payload.selected_experiences
        ],
        projects=[
            SelectedProjectEvidence(
                source_item_id=item.id,
                evidence_unit_ids=list(item.evidence_unit_ids),
                relevance_score=item.relevance_score,
                matched_requirements=list(item.matched_requirements),
                selection_reason=item.selection_reason,
                supporting_evidence_ids=list(item.supporting_evidence_ids),
                score_factors=dict(item.score_factors),
                name=item.name,
                role=item.role,
                start_date=item.start_date,
                end_date=item.end_date,
                summary=item.summary,
                tools=list(item.tools),
                bullets=[
                    SelectedBulletEvidence(
                        bullet_id=bullet.id,
                        source_item_id=item.id,
                        text=bullet.text,
                        evidence_unit_ids=list(item.evidence_unit_ids),
                        metric_ids=list(bullet.metric_ids),
                        tools=list(bullet.tools),
                        evidence_strength=bullet.evidence_strength,
                        verified_status=bullet.verified_status,
                        rewrite_allowed=bullet.rewrite_allowed,
                    )
                    for bullet in item.bullets
                ],
            )
            for item in generation_payload.selected_projects
        ],
        skills=[
            SelectedSkillEvidence(
                source_item_id=item.id,
                evidence_unit_ids=list(item.supporting_evidence_ids or [item.id]),
                relevance_score=item.relevance_score,
                matched_requirements=list(item.matched_requirements),
                selection_reason=item.selection_reason,
                supporting_evidence_ids=list(item.supporting_evidence_ids),
                score_factors=dict(item.score_factors),
                skill_name=item.skill_name,
                evidence_strength=item.evidence_strength,
                verified_status=item.verified_status,
            )
            for item in generation_payload.matched_skills
        ],
        certifications=[
            SelectedCertificationEvidence(
                source_item_id=item.id,
                evidence_unit_ids=list(item.evidence_unit_ids),
                relevance_score=item.relevance_score,
                name=item.name,
                issuer=item.issuer,
                issue_date=item.issue_date,
                expiration_date=item.expiration_date,
            )
            for item in generation_payload.selected_certifications
        ],
    )
    context = FullGenerationContext(
        context_id=context_id,
        source_profile_id=source_profile_id,
        parsed_job_output=parsed_job_output,
        selected_evidence=selected_evidence,
        section_plan=_map_section_plan(section_plan),
        story_strategy=StoryStrategy(
            strategy_id=f"story.{context_id}",
            focus_mode=story_focus_mode,
            target_role_title=generation_payload.role_context.target_role_title,
            narrative_anchor=generation_payload.headline_hint,
            summary_themes=[hint.theme for hint in generation_payload.summary_hints],
            must_emphasize=list(generation_payload.role_context.must_have_skills[:3]),
            avoid_claims=["unsupported leadership", "invented metrics", "unsupported tools"],
        ),
        page_constraints=PageConstraints(
            target_page_count=(
                generation_payload.length_constraints.target_page_count
                if generation_payload.length_constraints is not None
                and generation_payload.length_constraints.target_page_count is not None
                else 1
            ),
            max_summary_sentences=(
                generation_payload.length_constraints.summary_max_sentences
                if generation_payload.length_constraints is not None
                and generation_payload.length_constraints.summary_max_sentences is not None
                else 3
            ),
            max_experience_bullets_per_item=(
                generation_payload.length_constraints.max_experience_bullets
                if generation_payload.length_constraints is not None
                and generation_payload.length_constraints.max_experience_bullets is not None
                else 3
            ),
            max_project_bullets_per_item=(
                generation_payload.length_constraints.max_project_bullets
                if generation_payload.length_constraints is not None
                and generation_payload.length_constraints.max_project_bullets is not None
                else 2
            ),
        ),
        style_policy=StylePolicy(
            style_mode=style_mode,
            preferred_tone_terms=list(generation_payload.role_context.company_terminology[:3]),
            banned_phrases=["results-driven", "dynamic professional", "strategic thinker"],
        ),
    )
    return context


def build_summary_generation_input(context: FullGenerationContext) -> SummaryGenerationInput:
    """Extract bounded summary-generation input from the full generation context."""

    summary_section = next(
        (section for section in context.section_plan if section.section_type == GenerationSectionType.SUMMARY),
        None,
    )
    if summary_section is None:
        raise ValueError("full generation context does not contain a summary section")
    return SummaryGenerationInput(
        context_id=context.context_id,
        source_profile_id=context.source_profile_id,
        section_id=summary_section.section_id,
        parsed_job_output=context.parsed_job_output,
        story_strategy=context.story_strategy,
        page_constraints=context.page_constraints,
        style_policy=context.style_policy,
        experiences=context.selected_evidence.experiences[:2],
        projects=context.selected_evidence.projects[:1],
        skills=context.selected_evidence.skills[:3],
    )


def build_bullet_rewrite_inputs(context: FullGenerationContext) -> list[BulletRewriteInput]:
    """Extract one bounded bullet-rewrite input per planned experience/project item."""

    evidence_by_id = {
        **{item.source_item_id: item for item in context.selected_evidence.experiences},
        **{item.source_item_id: item for item in context.selected_evidence.projects},
    }
    inputs: list[BulletRewriteInput] = []
    for section in context.section_plan:
        if section.section_type not in {GenerationSectionType.EXPERIENCE, GenerationSectionType.PROJECTS}:
            continue
        for item in section.items:
            evidence = evidence_by_id[item.source_item_id]
            allowed_bullet_ids = set(item.selected_bullet_ids)
            source_bullets = [
                bullet
                for bullet in evidence.bullets
                if not allowed_bullet_ids or bullet.bullet_id in allowed_bullet_ids
            ]
            inputs.append(
                BulletRewriteInput(
                    context_id=context.context_id,
                    source_profile_id=context.source_profile_id,
                    section_id=section.section_id,
                    source_item_id=evidence.source_item_id,
                    source_item_type=evidence.item_type,
                    role_family=context.parsed_job_output.functional_role_family,
                    organizational_role_mode=context.parsed_job_output.organizational_role_mode,
                    story_strategy=context.story_strategy,
                    page_constraints=context.page_constraints,
                    style_policy=context.style_policy,
                    source_bullets=source_bullets,
                    evidence_unit_ids=list(item.evidence_unit_ids or evidence.evidence_unit_ids),
                    requested_bullet_count=min(
                        len(source_bullets),
                        context.page_constraints.max_experience_bullets_per_item
                        if evidence.item_type == ItemType.EXPERIENCE
                        else context.page_constraints.max_project_bullets_per_item,
                    ),
                )
            )
    return inputs


def build_skill_presentation_input(context: FullGenerationContext) -> SkillPresentationInput:
    """Extract bounded skill-presentation input from the full generation context."""

    skill_section = next(
        (section for section in context.section_plan if section.section_type == GenerationSectionType.SKILLS),
        None,
    )
    if skill_section is None:
        raise ValueError("full generation context does not contain a skills section")
    selected_skill_ids = {item.source_item_id for item in skill_section.items}
    selected_skills = [
        skill for skill in context.selected_evidence.skills if skill.source_item_id in selected_skill_ids
    ]
    return SkillPresentationInput(
        context_id=context.context_id,
        source_profile_id=context.source_profile_id,
        section_id=skill_section.section_id,
        parsed_job_output=context.parsed_job_output,
        story_strategy=context.story_strategy,
        page_constraints=context.page_constraints,
        style_policy=context.style_policy,
        selected_skills=selected_skills,
    )


def build_section_assembly_input(
    context: FullGenerationContext,
    *,
    summary_output: SummaryGenerationOutput | None = None,
    bullet_outputs: list[BulletRewriteOutput] | None = None,
    skill_presentation_output: SkillPresentationOutput | None = None,
    quality_signals: GenerationQualitySignals | None = None,
) -> SectionAssemblyInput:
    """Build bounded section-assembly input from prior Phase 5 generation outputs."""

    return SectionAssemblyInput(
        context_id=context.context_id,
        source_profile_id=context.source_profile_id,
        section_plan=context.section_plan,
        summary_output=summary_output,
        bullet_outputs=list(bullet_outputs or []),
        skill_presentation_output=skill_presentation_output,
        quality_signals=quality_signals or GenerationQualitySignals(),
    )


def _map_section_plan(section_plan: Phase3SectionPlan) -> list[PlannedSection]:
    sections = [
        PlannedSection(
            section_id="section.summary.main",
            section_type=GenerationSectionType.SUMMARY,
            title="Summary",
            visible=True,
            rationale="Summary is generated from bounded evidence and story strategy.",
        ),
        PlannedSection(
            section_id="section.experience.main",
            section_type=GenerationSectionType.EXPERIENCE,
            title="Experience",
            visible=bool(section_plan.experiences),
            items=[
                PlannedSectionItem(
                    source_item_id=item.source_item_id,
                    source_item_type=ItemType.EXPERIENCE,
                    selected_bullet_ids=[bullet.bullet_id for bullet in item.bullets],
                    rationale=item.rationale,
                )
                for item in section_plan.experiences
            ],
            rationale="Experience inclusion and bullet scope were decided upstream.",
        ),
        PlannedSection(
            section_id="section.projects.main",
            section_type=GenerationSectionType.PROJECTS,
            title="Projects",
            visible=bool(section_plan.projects),
            items=[
                PlannedSectionItem(
                    source_item_id=item.source_item_id,
                    source_item_type=ItemType.PROJECT,
                    selected_bullet_ids=[bullet.bullet_id for bullet in item.bullets],
                    rationale=item.rationale,
                )
                for item in section_plan.projects
            ],
            rationale="Project inclusion and bullet scope were decided upstream.",
        ),
        PlannedSection(
            section_id="section.skills.main",
            section_type=GenerationSectionType.SKILLS,
            title="Skills",
            visible=bool(section_plan.skills),
            items=[
                PlannedSectionItem(
                    source_item_id=item.source_item_id,
                    source_item_type=ItemType.SKILL,
                    rationale=item.rationale,
                )
                for item in section_plan.skills
            ],
            rationale="Skill inclusion was decided upstream.",
        ),
        PlannedSection(
            section_id="section.certifications.main",
            section_type=GenerationSectionType.CERTIFICATIONS,
            title="Certifications",
            visible=bool(section_plan.certifications),
            items=[
                PlannedSectionItem(
                    source_item_id=item.source_item_id,
                    source_item_type=ItemType.CERTIFICATION,
                    rationale=item.rationale,
                )
                for item in section_plan.certifications
            ],
            rationale="Certification inclusion was decided upstream.",
        ),
    ]
    return sections
