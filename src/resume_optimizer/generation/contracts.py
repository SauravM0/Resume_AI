"""Bounded generation contracts for Phase 5 text-generation work.

These schemas separate upstream strategic selection from downstream text
generation and final section assembly. They are intentionally narrower than the
current Phase 3 payload so generation code cannot decide resume strategy,
selection breadth, or page-level narrative structure on its own.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from ..models import (
    EvidenceStrength,
    ItemType,
    NonEmptyStr,
    PartialDate,
    RoleType,
    ScoreValue,
    SeniorityLevel,
    StableId,
    StrictModel,
    VerifiedStatus,
)
from ..phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from ..phase3_models import BulletRewriteStrategy, OmissionReason


class GenerationSectionType(StrEnum):
    """Bounded section types the generator may write or assemble."""

    SUMMARY = "summary"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"


class GenerationStyleMode(StrEnum):
    """Approved writing style modes for bounded generation."""

    ATS_BALANCED = "ats_balanced"
    DIRECT = "direct"
    CONSERVATIVE = "conservative"


class StoryFocusMode(StrEnum):
    """Approved story-focus modes decided upstream, not by the generator."""

    BALANCED = "balanced"
    EXPERIENCE_FORWARD = "experience_forward"
    PROJECT_FORWARD = "project_forward"
    SKILLS_FORWARD = "skills_forward"


class QualitySignalSeverity(StrEnum):
    """Severity of a generation-quality signal."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PolicyReasonCode(StrEnum):
    """Stable Phase 5 policy reason codes for generation guardrails."""

    UNSUPPORTED_NUMBER = "unsupported_number"
    UNSUPPORTED_TOOL = "unsupported_tool"
    OWNERSHIP_INFLATION = "ownership_inflation"
    LEADERSHIP_INFLATION = "leadership_inflation"
    SCOPE_INFLATION = "scope_inflation"
    DOMAIN_INFLATION = "domain_inflation"
    FAKE_SPECIALIZATION = "fake_specialization"
    UNSUPPORTED_YEARS_EXPERIENCE = "unsupported_years_experience"


class PolicySignalSeverity(StrEnum):
    """Machine-readable enforcement outcome for a policy violation."""

    HARD_BLOCK = "hard_block"
    SOFT_WARNING = "soft_warning"
    FALLBACK_TO_SOURCE = "fallback_to_source"
    REQUIRES_REGENERATION = "requires_regeneration"


class QualityDimension(StrEnum):
    """Deterministic writing-quality dimensions tracked in Phase 5 QA."""

    REPETITION = "repetition"
    GENERIC_FILLER = "generic_filler"
    KEYWORD_STUFFING = "keyword_stuffing"
    SUMMARY_STRENGTH = "summary_strength"
    BULLET_NATURALNESS = "bullet_naturalness"
    SECTION_BALANCE = "section_balance"
    BULLET_LENGTH = "bullet_length"
    SKILLS_COMPACTNESS = "skills_compactness"
    SUMMARY_DENSITY = "summary_density"
    CLAIM_BOUNDEDNESS = "claim_boundedness"


class ParsedJobOutput(StrictModel):
    """Bounded job context exposed to generation code."""

    job_analysis_id: StableId
    target_role_title: NonEmptyStr | None = None
    role_type: RoleType | None = None
    seniority_level: SeniorityLevel | None = None
    functional_role_family: FunctionalRoleFamily
    organizational_role_mode: OrganizationalRoleMode
    industry_domain: NonEmptyStr | None = None
    must_have_skills: list[NonEmptyStr] = Field(default_factory=list)
    preferred_skills: list[NonEmptyStr] = Field(default_factory=list)
    must_have_requirements: list[NonEmptyStr] = Field(default_factory=list)
    preferred_requirements: list[NonEmptyStr] = Field(default_factory=list)
    company_terminology: list[NonEmptyStr] = Field(default_factory=list)
    action_verbs: list[NonEmptyStr] = Field(default_factory=list)


class StoryStrategy(StrictModel):
    """Upstream story decision that generation must follow, not invent."""

    strategy_id: StableId
    focus_mode: StoryFocusMode
    target_role_title: NonEmptyStr | None = None
    narrative_anchor: NonEmptyStr | None = None
    summary_themes: list[NonEmptyStr] = Field(default_factory=list)
    must_emphasize: list[NonEmptyStr] = Field(default_factory=list)
    avoid_claims: list[NonEmptyStr] = Field(default_factory=list)


class PageConstraints(StrictModel):
    """Explicit page and density constraints the generator must obey."""

    target_page_count: int = Field(ge=1, le=2)
    max_summary_sentences: int = Field(default=3, ge=1, le=6)
    max_experience_bullets_per_item: int = Field(default=3, ge=1, le=8)
    max_project_bullets_per_item: int = Field(default=2, ge=1, le=6)
    max_skill_groups: int = Field(default=1, ge=1, le=4)
    max_skills_per_group: int = Field(default=8, ge=1, le=20)


class StylePolicy(StrictModel):
    """Bounded style rules that generation code can apply."""

    style_mode: GenerationStyleMode
    forbid_first_person: bool = True
    require_action_verb_bullets: bool = True
    emphasize_metrics: bool = True
    preserve_chronology: bool = True
    suppress_low_support_content: bool = True
    preferred_tone_terms: list[NonEmptyStr] = Field(default_factory=list)
    banned_phrases: list[NonEmptyStr] = Field(default_factory=list)


class SelectedBulletEvidence(StrictModel):
    """One upstream-approved bullet that generation may cite or rewrite."""

    bullet_id: StableId
    source_item_id: StableId
    text: NonEmptyStr
    evidence_unit_ids: list[StableId] = Field(default_factory=list)
    metric_ids: list[StableId] = Field(default_factory=list)
    tools: list[NonEmptyStr] = Field(default_factory=list)
    evidence_strength: EvidenceStrength
    verified_status: VerifiedStatus
    rewrite_allowed: bool = True


class _BaseSelectedEvidence(StrictModel):
    """Shared provenance-bearing evidence fields."""

    source_item_id: StableId
    evidence_unit_ids: list[StableId] = Field(min_length=1)
    relevance_score: ScoreValue
    matched_requirements: list[NonEmptyStr] = Field(default_factory=list)
    selection_reason: NonEmptyStr | None = None
    supporting_evidence_ids: list[StableId] = Field(default_factory=list)
    score_factors: dict[str, float] = Field(default_factory=dict)


class SelectedExperienceEvidence(_BaseSelectedEvidence):
    """Upstream-approved experience item for bounded generation."""

    item_type: Literal[ItemType.EXPERIENCE] = ItemType.EXPERIENCE
    organization: NonEmptyStr
    title: NonEmptyStr
    start_date: PartialDate
    end_date: PartialDate | None = None
    current: bool = False
    tools: list[NonEmptyStr] = Field(default_factory=list)
    bullets: list[SelectedBulletEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bullet_ownership(self) -> Self:
        invalid_ids = [
            bullet.bullet_id for bullet in self.bullets if bullet.source_item_id != self.source_item_id
        ]
        if invalid_ids:
            raise ValueError(
                "experience bullets must reference the parent source_item_id: "
                + ", ".join(invalid_ids)
            )
        return self


class SelectedProjectEvidence(_BaseSelectedEvidence):
    """Upstream-approved project item for bounded generation."""

    item_type: Literal[ItemType.PROJECT] = ItemType.PROJECT
    name: NonEmptyStr
    role: NonEmptyStr | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    summary: NonEmptyStr | None = None
    tools: list[NonEmptyStr] = Field(default_factory=list)
    bullets: list[SelectedBulletEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bullet_ownership(self) -> Self:
        invalid_ids = [
            bullet.bullet_id for bullet in self.bullets if bullet.source_item_id != self.source_item_id
        ]
        if invalid_ids:
            raise ValueError(
                "project bullets must reference the parent source_item_id: "
                + ", ".join(invalid_ids)
            )
        return self


class SelectedSkillEvidence(_BaseSelectedEvidence):
    """Upstream-approved skill signal for bounded generation."""

    item_type: Literal[ItemType.SKILL] = ItemType.SKILL
    skill_name: NonEmptyStr
    evidence_strength: EvidenceStrength
    verified_status: VerifiedStatus


class SelectedCertificationEvidence(_BaseSelectedEvidence):
    """Upstream-approved certification signal for bounded generation."""

    item_type: Literal[ItemType.CERTIFICATION] = ItemType.CERTIFICATION
    name: NonEmptyStr
    issuer: NonEmptyStr
    issue_date: PartialDate | None = None
    expiration_date: PartialDate | None = None


class SelectedEvidence(StrictModel):
    """All upstream-approved evidence the generator may touch."""

    experiences: list[SelectedExperienceEvidence] = Field(default_factory=list)
    projects: list[SelectedProjectEvidence] = Field(default_factory=list)
    skills: list[SelectedSkillEvidence] = Field(default_factory=list)
    certifications: list[SelectedCertificationEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_source_ids(self) -> Self:
        source_ids = [
            *[item.source_item_id for item in self.experiences],
            *[item.source_item_id for item in self.projects],
            *[item.source_item_id for item in self.skills],
            *[item.source_item_id for item in self.certifications],
        ]
        duplicates = sorted({item_id for item_id in source_ids if source_ids.count(item_id) > 1})
        if duplicates:
            raise ValueError("selected evidence source_item_id values must be unique: " + ", ".join(duplicates))
        return self


class PlannedSectionItem(StrictModel):
    """One upstream-approved item reference inside a planned section."""

    source_item_id: StableId
    source_item_type: ItemType
    selected_bullet_ids: list[StableId] = Field(default_factory=list)
    evidence_unit_ids: list[StableId] = Field(default_factory=list)
    rationale: NonEmptyStr


class PlannedSection(StrictModel):
    """One planned section boundary the generator must respect."""

    section_id: StableId
    section_type: GenerationSectionType
    title: NonEmptyStr
    visible: bool = True
    items: list[PlannedSectionItem] = Field(default_factory=list)
    rationale: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_item_shape(self) -> Self:
        if self.section_type == GenerationSectionType.SUMMARY and self.items:
            raise ValueError("summary sections must not contain planned item references")
        return self


class FullGenerationContext(StrictModel):
    """Complete bounded generation contract for Phase 5 generation work."""

    schema_version: NonEmptyStr = "phase5.generation.context.v1"
    context_id: StableId
    source_profile_id: StableId
    parsed_job_output: ParsedJobOutput
    selected_evidence: SelectedEvidence
    section_plan: list[PlannedSection] = Field(min_length=1)
    story_strategy: StoryStrategy
    page_constraints: PageConstraints
    style_policy: StylePolicy

    @model_validator(mode="after")
    def validate_section_plan_references(self) -> Self:
        section_ids = [section.section_id for section in self.section_plan]
        duplicate_sections = sorted({section_id for section_id in section_ids if section_ids.count(section_id) > 1})
        if duplicate_sections:
            raise ValueError("section_plan section_id values must be unique: " + ", ".join(duplicate_sections))

        evidence_by_id = {
            **{item.source_item_id: item for item in self.selected_evidence.experiences},
            **{item.source_item_id: item for item in self.selected_evidence.projects},
            **{item.source_item_id: item for item in self.selected_evidence.skills},
            **{item.source_item_id: item for item in self.selected_evidence.certifications},
        }

        for section in self.section_plan:
            for item in section.items:
                evidence = evidence_by_id.get(item.source_item_id)
                if evidence is None:
                    raise ValueError(
                        f"section_plan item references unknown source_item_id '{item.source_item_id}'"
                    )
                if item.source_item_type != evidence.item_type:
                    raise ValueError(
                        "section_plan item_type does not match selected evidence for "
                        f"source_item_id '{item.source_item_id}'"
                    )
                if section.section_type == GenerationSectionType.EXPERIENCE and evidence.item_type != ItemType.EXPERIENCE:
                    raise ValueError("experience sections may only reference selected experiences")
                if section.section_type == GenerationSectionType.PROJECTS and evidence.item_type != ItemType.PROJECT:
                    raise ValueError("projects sections may only reference selected projects")
                if section.section_type == GenerationSectionType.SKILLS and evidence.item_type != ItemType.SKILL:
                    raise ValueError("skills sections may only reference selected skills")
                if section.section_type == GenerationSectionType.CERTIFICATIONS and evidence.item_type != ItemType.CERTIFICATION:
                    raise ValueError("certifications sections may only reference selected certifications")

                if item.selected_bullet_ids:
                    if not hasattr(evidence, "bullets"):
                        raise ValueError(
                            f"section_plan item '{item.source_item_id}' cannot carry selected_bullet_ids"
                        )
                    allowed_bullet_ids = {bullet.bullet_id for bullet in evidence.bullets}
                    invalid_bullet_ids = [
                        bullet_id for bullet_id in item.selected_bullet_ids if bullet_id not in allowed_bullet_ids
                    ]
                    if invalid_bullet_ids:
                        raise ValueError(
                            "section_plan item references unknown bullet ids for "
                            f"source_item_id '{item.source_item_id}': " + ", ".join(invalid_bullet_ids)
                        )
        return self


class SummaryGenerationInput(StrictModel):
    """Bounded input for summary generation only."""

    context_id: StableId
    source_profile_id: StableId
    section_id: StableId
    parsed_job_output: ParsedJobOutput
    story_strategy: StoryStrategy
    page_constraints: PageConstraints
    style_policy: StylePolicy
    experiences: list[SelectedExperienceEvidence] = Field(default_factory=list)
    projects: list[SelectedProjectEvidence] = Field(default_factory=list)
    skills: list[SelectedSkillEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_presence(self) -> Self:
        if not self.experiences and not self.projects and not self.skills:
            raise ValueError("summary generation requires at least one bounded evidence source")
        return self


class BulletRewriteInput(StrictModel):
    """Bounded input for rewriting bullets for one selected item."""

    context_id: StableId
    source_profile_id: StableId
    section_id: StableId
    source_item_id: StableId
    source_item_type: Literal[ItemType.EXPERIENCE, ItemType.PROJECT]
    role_family: FunctionalRoleFamily
    organizational_role_mode: OrganizationalRoleMode
    story_strategy: StoryStrategy
    page_constraints: PageConstraints
    style_policy: StylePolicy
    source_bullets: list[SelectedBulletEvidence] = Field(min_length=1)
    evidence_unit_ids: list[StableId] = Field(min_length=1)
    requested_bullet_count: int = Field(ge=1, le=8)

    @model_validator(mode="after")
    def validate_source_bullets(self) -> Self:
        invalid_ids = [
            bullet.bullet_id for bullet in self.source_bullets if bullet.source_item_id != self.source_item_id
        ]
        if invalid_ids:
            raise ValueError(
                "bullet rewrite source_bullets must reference the parent source_item_id: "
                + ", ".join(invalid_ids)
            )
        return self


class SkillPresentationInput(StrictModel):
    """Bounded input for presenting already-selected skills."""

    context_id: StableId
    source_profile_id: StableId
    section_id: StableId
    parsed_job_output: ParsedJobOutput
    story_strategy: StoryStrategy
    page_constraints: PageConstraints
    style_policy: StylePolicy
    selected_skills: list[SelectedSkillEvidence] = Field(min_length=1)


class QualitySignal(StrictModel):
    """One structured quality signal produced by generation-time validators."""

    signal_id: StableId
    severity: QualitySignalSeverity
    message: NonEmptyStr
    reason_code: PolicyReasonCode | None = None
    policy_severity: PolicySignalSeverity | None = None
    quality_dimension: QualityDimension | None = None
    suggested_fallback_action: NonEmptyStr | None = None
    section_id: StableId | None = None
    source_item_id: StableId | None = None
    source_bullet_ids: list[StableId] = Field(default_factory=list)


class GenerationQualitySignals(StrictModel):
    """Structured quality signals attached to bounded generation artifacts."""

    hard_failures: list[QualitySignal] = Field(default_factory=list)
    warnings: list[QualitySignal] = Field(default_factory=list)
    blocked_section_ids: list[StableId] = Field(default_factory=list)
    dimension_scores: dict[QualityDimension, ScoreValue] = Field(default_factory=dict)
    passed: bool = True
    provenance_coverage_score: ScoreValue | None = None
    style_alignment_score: ScoreValue | None = None


class SummaryGenerationOutput(StrictModel):
    """Tightly structured summary output."""

    section_id: StableId
    summary_text: NonEmptyStr
    source_item_ids: list[StableId] = Field(min_length=1)
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    evidence_ids_used: list[StableId] = Field(default_factory=list)
    themes_used: list[NonEmptyStr] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    quality_signals: GenerationQualitySignals = Field(default_factory=GenerationQualitySignals)
    role_family: FunctionalRoleFamily
    organizational_role_mode: OrganizationalRoleMode
    style_mode: GenerationStyleMode


class BulletRewriteOutput(StrictModel):
    """Tightly structured output for one rewritten bullet."""

    section_id: StableId
    source_item_id: StableId
    source_item_type: Literal[ItemType.EXPERIENCE, ItemType.PROJECT]
    source_bullet_id: StableId
    rewritten_text: NonEmptyStr
    evidence_ids_used: list[StableId] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    rewrite_quality_signals: GenerationQualitySignals = Field(default_factory=GenerationQualitySignals)
    rewrite_strategy: BulletRewriteStrategy
    role_family: FunctionalRoleFamily
    organizational_role_mode: OrganizationalRoleMode
    style_mode: GenerationStyleMode

    @model_validator(mode="after")
    def validate_output_shape(self) -> Self:
        if not self.evidence_ids_used:
            raise ValueError("bullet rewrite output must include at least one evidence id")
        return self


class SkillGroupPresentation(StrictModel):
    """One display-ready skill group."""

    group_id: StableId
    label: NonEmptyStr
    skill_names: list[NonEmptyStr] = Field(min_length=1)
    source_item_ids: list[StableId] = Field(min_length=1)


class SkillPresentationOutput(StrictModel):
    """Tightly structured skill-presentation output."""

    section_id: StableId
    grouped_skills: list[SkillGroupPresentation] = Field(min_length=1)
    rendered_skill_lines: list[NonEmptyStr] = Field(min_length=1)
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    quality_signals: GenerationQualitySignals = Field(default_factory=GenerationQualitySignals)
    role_family: FunctionalRoleFamily
    organizational_role_mode: OrganizationalRoleMode
    style_mode: GenerationStyleMode


class AssembledSectionEntry(StrictModel):
    """One assembled entry inside a final section payload."""

    source_item_id: StableId
    source_item_type: ItemType
    generated_bullet_ids: list[StableId] = Field(default_factory=list)
    skill_group_ids: list[StableId] = Field(default_factory=list)


class AssembledSection(StrictModel):
    """One fully assembled section derived from bounded generation artifacts."""

    section_id: StableId
    section_type: GenerationSectionType
    title: NonEmptyStr
    summary_text: NonEmptyStr | None = None
    entries: list[AssembledSectionEntry] = Field(default_factory=list)


class AssembledSummary(StrictModel):
    """Render-ready summary payload."""

    section_id: StableId
    title: NonEmptyStr
    text: NonEmptyStr


class AssembledBulletLine(StrictModel):
    """Render-ready bullet line with provenance anchors."""

    source_bullet_id: StableId
    text: NonEmptyStr
    evidence_ids_used: list[StableId] = Field(default_factory=list)


class AssembledExperienceItem(StrictModel):
    """Render-ready experience block."""

    source_item_id: StableId
    title: NonEmptyStr
    organization: NonEmptyStr
    bullets: list[AssembledBulletLine] = Field(default_factory=list)


class AssembledProjectItem(StrictModel):
    """Render-ready project block."""

    source_item_id: StableId
    name: NonEmptyStr
    role: NonEmptyStr | None = None
    bullets: list[AssembledBulletLine] = Field(default_factory=list)


class AssembledExperienceSection(StrictModel):
    """Render-ready experience section."""

    section_id: StableId
    title: NonEmptyStr
    items: list[AssembledExperienceItem] = Field(default_factory=list)


class AssembledProjectSection(StrictModel):
    """Render-ready project section."""

    section_id: StableId
    title: NonEmptyStr
    items: list[AssembledProjectItem] = Field(default_factory=list)


class AssembledSkillSection(StrictModel):
    """Render-ready skill section."""

    section_id: StableId
    title: NonEmptyStr
    grouped_skills: list[SkillGroupPresentation] = Field(default_factory=list)
    rendered_skill_lines: list[NonEmptyStr] = Field(default_factory=list)


class AssembledEducationSection(StrictModel):
    """Render-ready education section placeholder for deterministic downstream renderers."""

    section_id: StableId
    title: NonEmptyStr
    entries: list[NonEmptyStr] = Field(default_factory=list)


class AssembledCertificationItem(StrictModel):
    """Render-ready certification block."""

    source_item_id: StableId
    name: NonEmptyStr
    issuer: NonEmptyStr
    details: NonEmptyStr | None = None


class AssembledCertificationSection(StrictModel):
    """Render-ready certification section."""

    section_id: StableId
    title: NonEmptyStr
    items: list[AssembledCertificationItem] = Field(default_factory=list)


class OmittedAssemblyItem(StrictModel):
    """Explicitly tracked omitted content during deterministic assembly."""

    source_item_id: StableId
    source_item_type: ItemType
    reason: OmissionReason
    detail: NonEmptyStr
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    section_id: StableId | None = None


class AssemblyBudgetSignals(StrictModel):
    """Deterministic content-budget diagnostics for section assembly."""

    target_page_count: int = Field(ge=1, le=2)
    max_total_bullets: int = Field(ge=0)
    used_total_bullets: int = Field(ge=0)
    remaining_bullet_budget: int = Field(ge=0)
    within_budget: bool = True
    omitted_item_ids: list[StableId] = Field(default_factory=list)


class SectionAssemblyOutput(StrictModel):
    """Final structured assembly output before deterministic rendering."""

    schema_version: NonEmptyStr = "phase5.section.assembly.v1"
    context_id: StableId
    source_profile_id: StableId
    assembled_summary: AssembledSummary | None = None
    assembled_experience_sections: list[AssembledExperienceSection] = Field(default_factory=list)
    assembled_project_sections: list[AssembledProjectSection] = Field(default_factory=list)
    assembled_skill_section: AssembledSkillSection | None = None
    assembled_education_section: AssembledEducationSection | None = None
    assembled_certification_section: AssembledCertificationSection | None = None
    omitted_items_with_reasons: list[OmittedAssemblyItem] = Field(default_factory=list)
    assembly_warnings: list[NonEmptyStr] = Field(default_factory=list)
    budget_signals: AssemblyBudgetSignals
    quality_signals: GenerationQualitySignals = Field(default_factory=GenerationQualitySignals)


class SectionAssemblyInput(StrictModel):
    """Bounded input for final section assembly only."""

    context_id: StableId
    source_profile_id: StableId
    section_plan: list[PlannedSection] = Field(min_length=1)
    summary_output: SummaryGenerationOutput | None = None
    bullet_outputs: list[BulletRewriteOutput] = Field(default_factory=list)
    skill_presentation_output: SkillPresentationOutput | None = None
    quality_signals: GenerationQualitySignals = Field(default_factory=GenerationQualitySignals)

    @model_validator(mode="after")
    def validate_against_plan(self) -> Self:
        section_by_id = {section.section_id: section for section in self.section_plan}
        bullet_output_item_ids = {output.source_item_id for output in self.bullet_outputs}

        if self.summary_output is not None:
            summary_section = section_by_id.get(self.summary_output.section_id)
            if summary_section is None:
                raise ValueError("summary_output.section_id must exist in section_plan")
            if summary_section.section_type != GenerationSectionType.SUMMARY:
                raise ValueError("summary_output.section_id must reference a summary section")

        if self.skill_presentation_output is not None:
            skill_section = section_by_id.get(self.skill_presentation_output.section_id)
            if skill_section is None:
                raise ValueError("skill_presentation_output.section_id must exist in section_plan")
            if skill_section.section_type != GenerationSectionType.SKILLS:
                raise ValueError("skill_presentation_output.section_id must reference a skills section")

        planned_item_ids = {
            item.source_item_id
            for section in self.section_plan
            for item in section.items
        }
        for output in self.bullet_outputs:
            section = section_by_id.get(output.section_id)
            if section is None:
                raise ValueError(
                    f"bullet output section_id '{output.section_id}' must exist in section_plan"
                )
            if section.section_type not in {GenerationSectionType.EXPERIENCE, GenerationSectionType.PROJECTS}:
                raise ValueError(
                    f"bullet output section_id '{output.section_id}' must reference an experience or projects section"
                )
            if output.source_item_id not in planned_item_ids:
                raise ValueError(
                    "bullet output references source_item_id not present in section_plan: "
                    f"{output.source_item_id}"
                )

        if bullet_output_item_ids and not any(
            section.section_type in {GenerationSectionType.EXPERIENCE, GenerationSectionType.PROJECTS}
            for section in self.section_plan
        ):
            raise ValueError("bullet_outputs were provided but section_plan has no bullet-owning sections")

        return self
