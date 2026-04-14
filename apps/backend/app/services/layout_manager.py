# Compile success is not enough: a valid PDF can still be too long, cramped, or
# poorly balanced for a resume. Layout control is a product-quality problem
# because page fit, section balance, and content priority directly affect the
# usefulness of the final artifact. Deterministic trimming is safer than ad hoc
# overflow fixes because every reduction follows documented rules and produces
# explainable warnings for diagnostics and frontend review.
"""Deterministic layout management and overflow mitigation for Phase 5."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from backend.app.models.render_models import (
    RenderBullet,
    RenderExperience,
    RenderJobInput,
    RenderProject,
    RenderSectionType,
    RenderSkillGroup,
    TargetPagePolicy,
)
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel

__all__ = [
    "LayoutPagePolicy",
    "LayoutPlanResult",
    "LayoutRenderMode",
    "LayoutTrimDecision",
    "SectionTrimMetadata",
    "TrimAction",
    "decide_max_bullets_per_experience",
    "decide_max_projects",
    "estimate_layout_lines",
    "manage_layout",
]


class LayoutPagePolicy(StrEnum):
    """Supported layout policies for deterministic page-fit decisions."""

    ONE_PAGE_STRICT = "one_page_strict"
    ONE_PAGE_FLEX = "one_page_flex"
    TWO_PAGE_MAX = "two_page_max"


class LayoutRenderMode(StrEnum):
    """Rendering density requested by layout management."""

    STANDARD = "standard"
    COMPACT = "compact"


class TrimAction(StrEnum):
    """Types of deterministic content reduction decisions."""

    COMPACT_SECTION = "compact_section"
    TRIM_SUMMARY = "trim_summary"
    TRIM_BULLETS = "trim_bullets"
    REMOVE_PROJECT = "remove_project"
    REMOVE_SKILL_GROUP = "remove_skill_group"
    HIDE_EMPTY_SECTION = "hide_empty_section"


class LayoutTrimDecision(StrictModel):
    """Explainable record for one deterministic layout reduction."""

    action: TrimAction
    section_type: RenderSectionType
    reason: NonEmptyStr
    item_id: StableId | None = None
    removed_bullet_ids: list[StableId] = Field(default_factory=list)
    removed_item_ids: list[StableId] = Field(default_factory=list)
    before_count: int | None = Field(default=None, ge=0)
    after_count: int | None = Field(default=None, ge=0)
    estimated_lines_saved: int = Field(default=0, ge=0)


class SectionTrimMetadata(StrictModel):
    """Section-level metadata describing layout reductions."""

    section_type: RenderSectionType
    render_mode: LayoutRenderMode = LayoutRenderMode.STANDARD
    original_item_count: int = Field(default=0, ge=0)
    adjusted_item_count: int = Field(default=0, ge=0)
    original_bullet_count: int = Field(default=0, ge=0)
    adjusted_bullet_count: int = Field(default=0, ge=0)
    removed_item_ids: list[StableId] = Field(default_factory=list)
    removed_bullet_ids: list[StableId] = Field(default_factory=list)
    estimated_lines_saved: int = Field(default=0, ge=0)
    warnings: list[NonEmptyStr] = Field(default_factory=list)


class LayoutPlanResult(StrictModel):
    """Output from layout management before LaTeX mapping and compilation."""

    adjusted_render_input: RenderJobInput
    page_policy: LayoutPagePolicy
    render_mode: LayoutRenderMode
    estimated_lines_before: int = Field(ge=0)
    estimated_lines_after: int = Field(ge=0)
    max_allowed_lines: int = Field(ge=1)
    overflow_remaining: bool
    truncation_decisions: list[LayoutTrimDecision] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    section_trim_metadata: list[SectionTrimMetadata] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_overflow_state(self) -> Self:
        """Keep overflow flag aligned with estimated layout state."""

        if self.overflow_remaining != (
            self.estimated_lines_after > self.max_allowed_lines
        ):
            raise ValueError("overflow_remaining must match final line estimate")
        return self


# These constants are deliberately simple and centralized. They approximate the
# ATS template from Task 2 using line-equivalents, not real TeX metrics. The
# compiler will provide exact page count later; this layer provides deterministic
# pre-compile guardrails and explainable trimming.
POLICY_LINE_BUDGETS: dict[LayoutPagePolicy, int] = {
    LayoutPagePolicy.ONE_PAGE_STRICT: 46,
    LayoutPagePolicy.ONE_PAGE_FLEX: 52,
    LayoutPagePolicy.TWO_PAGE_MAX: 104,
}
POLICY_MAX_PROJECTS: dict[LayoutPagePolicy, int] = {
    LayoutPagePolicy.ONE_PAGE_STRICT: 1,
    LayoutPagePolicy.ONE_PAGE_FLEX: 2,
    LayoutPagePolicy.TWO_PAGE_MAX: 4,
}
POLICY_MAX_EXPERIENCE_BULLETS: dict[LayoutPagePolicy, int] = {
    LayoutPagePolicy.ONE_PAGE_STRICT: 3,
    LayoutPagePolicy.ONE_PAGE_FLEX: 4,
    LayoutPagePolicy.TWO_PAGE_MAX: 5,
}
POLICY_MIN_EXPERIENCE_BULLETS: dict[LayoutPagePolicy, int] = {
    LayoutPagePolicy.ONE_PAGE_STRICT: 2,
    LayoutPagePolicy.ONE_PAGE_FLEX: 2,
    LayoutPagePolicy.TWO_PAGE_MAX: 2,
}
SUMMARY_COMPACT_MAX_CHARS = 260
SUMMARY_LINE_COST = 3
SUMMARY_COMPACT_LINE_COST = 2
SECTION_HEADER_LINE_COST = 2
PERSONAL_INFO_LINE_COST = 4
EXPERIENCE_BASE_LINE_COST = 2
PROJECT_BASE_LINE_COST = 2
EDUCATION_ITEM_LINE_COST = 2
CERTIFICATION_ITEM_LINE_COST = 2
BULLET_LINE_COST = 1
SKILL_GROUP_STANDARD_LINE_COST = 1
SKILL_GROUP_COMPACT_LINE_COST = 0.65


def manage_layout(
    render_input: RenderJobInput,
    *,
    page_policy: LayoutPagePolicy | TargetPagePolicy | None = None,
) -> LayoutPlanResult:
    """Apply deterministic layout and overflow rules to verified render content."""

    policy = _resolve_page_policy(page_policy or render_input.target_page_policy)
    max_allowed_lines = _max_allowed_lines(render_input, policy)
    adjusted = render_input.model_copy(deep=True)
    decisions: list[LayoutTrimDecision] = []
    warnings: list[str] = []
    compact_sections: set[RenderSectionType] = set()
    original_counts = _section_counts(render_input)

    estimated_before = estimate_layout_lines(adjusted)
    _apply_policy_caps(adjusted, policy, max_allowed_lines, decisions, warnings)

    estimated_after_caps = estimate_layout_lines(adjusted)
    if estimated_after_caps > max_allowed_lines and adjusted.summary is not None:
        _compact_summary(adjusted, decisions, warnings)

    if estimate_layout_lines(adjusted, compact_sections) > max_allowed_lines:
        _compact_skills(compact_sections, decisions, warnings, adjusted)

    while estimate_layout_lines(adjusted, compact_sections) > max_allowed_lines:
        if not _remove_low_priority_project(adjusted, decisions, warnings):
            break

    while estimate_layout_lines(adjusted, compact_sections) > max_allowed_lines:
        if not _trim_experience_bullet(adjusted, policy, decisions, warnings):
            break

    while estimate_layout_lines(adjusted, compact_sections) > max_allowed_lines:
        if not _remove_low_priority_skill_group(adjusted, decisions, warnings):
            break

    _hide_empty_optional_sections(adjusted, decisions, warnings)
    estimated_after = estimate_layout_lines(adjusted, compact_sections)
    if estimated_after > max_allowed_lines:
        warnings.append(
            "Layout overflow remains after all safe deterministic trimming rules."
        )

    return LayoutPlanResult(
        adjusted_render_input=adjusted,
        page_policy=policy,
        render_mode=(
            LayoutRenderMode.COMPACT
            if compact_sections
            else LayoutRenderMode.STANDARD
        ),
        estimated_lines_before=estimated_before,
        estimated_lines_after=estimated_after,
        max_allowed_lines=max_allowed_lines,
        overflow_remaining=estimated_after > max_allowed_lines,
        truncation_decisions=decisions,
        warnings=warnings,
        section_trim_metadata=_build_section_trim_metadata(
            original_counts,
            _section_counts(adjusted),
            decisions,
            compact_sections,
        ),
    )


def decide_max_bullets_per_experience(
    render_input: RenderJobInput,
    *,
    page_policy: LayoutPagePolicy | TargetPagePolicy | None = None,
) -> int:
    """Return the max bullets allowed per experience for the page policy."""

    policy = _resolve_page_policy(page_policy or render_input.target_page_policy)
    configured_max = _section_max_bullets(
        render_input,
        RenderSectionType.EXPERIENCE,
    )
    policy_max = POLICY_MAX_EXPERIENCE_BULLETS[policy]
    if configured_max is None:
        return policy_max
    return min(policy_max, configured_max)


def decide_max_projects(
    render_input: RenderJobInput,
    *,
    page_policy: LayoutPagePolicy | TargetPagePolicy | None = None,
) -> int:
    """Return the max projects allowed for the page policy."""

    policy = _resolve_page_policy(page_policy or render_input.target_page_policy)
    configured_max = _section_max_lines(render_input, RenderSectionType.PROJECTS)
    if configured_max is None:
        return POLICY_MAX_PROJECTS[policy]
    # Project items are estimated as base lines plus one bullet line each.
    configured_project_cap = max(0, configured_max // (PROJECT_BASE_LINE_COST + 1))
    return min(POLICY_MAX_PROJECTS[policy], configured_project_cap)


def estimate_layout_lines(
    render_input: RenderJobInput,
    compact_sections: set[RenderSectionType] | None = None,
) -> int:
    """Estimate resume length in deterministic line-equivalent units."""

    compact = compact_sections or set()
    total = PERSONAL_INFO_LINE_COST

    if render_input.summary is not None:
        total += (
            SUMMARY_COMPACT_LINE_COST
            if RenderSectionType.SUMMARY in compact
            else SUMMARY_LINE_COST
        )

    if render_input.experiences:
        total += SECTION_HEADER_LINE_COST
        total += sum(
            EXPERIENCE_BASE_LINE_COST + (len(experience.bullets) * BULLET_LINE_COST)
            for experience in render_input.experiences
        )

    if render_input.projects:
        total += SECTION_HEADER_LINE_COST
        total += sum(
            PROJECT_BASE_LINE_COST + (len(project.bullets) * BULLET_LINE_COST)
            for project in render_input.projects
        )

    if render_input.skills:
        total += SECTION_HEADER_LINE_COST
        line_cost = (
            SKILL_GROUP_COMPACT_LINE_COST
            if RenderSectionType.SKILLS in compact
            else SKILL_GROUP_STANDARD_LINE_COST
        )
        total += round(len(render_input.skills) * line_cost)

    if render_input.education:
        total += SECTION_HEADER_LINE_COST
        total += len(render_input.education) * EDUCATION_ITEM_LINE_COST

    if render_input.certifications:
        total += SECTION_HEADER_LINE_COST
        total += len(render_input.certifications) * CERTIFICATION_ITEM_LINE_COST

    return total


def _apply_policy_caps(
    render_input: RenderJobInput,
    policy: LayoutPagePolicy,
    max_allowed_lines: int,
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
) -> None:
    """Apply page-policy hard caps before overflow-specific mitigation."""

    max_projects = decide_max_projects(render_input, page_policy=policy)
    if len(render_input.projects) > max_projects:
        kept_projects = _top_priority_items(render_input.projects, max_projects)
        removed_projects = [
            project for project in render_input.projects if project not in kept_projects
        ]
        _set_render_input_field(
            render_input,
            "projects",
            _ordered_by_display_order(kept_projects),
        )
        removed_ids = [project.id for project in removed_projects]
        decisions.append(
            LayoutTrimDecision(
                action=TrimAction.REMOVE_PROJECT,
                section_type=RenderSectionType.PROJECTS,
                reason=f"Page policy {policy.value} limits projects to {max_projects}.",
                removed_item_ids=removed_ids,
                before_count=len(render_input.projects) + len(removed_projects),
                after_count=len(render_input.projects),
                estimated_lines_saved=sum(
                    _estimate_project_lines(project) for project in removed_projects
                ),
            )
        )
        warnings.append(
            "Removed lower-priority projects for page policy limit: "
            + ", ".join(removed_ids)
        )

    if estimate_layout_lines(render_input) > max_allowed_lines:
        _compact_summary(render_input, decisions, warnings)

    max_bullets = decide_max_bullets_per_experience(render_input, page_policy=policy)
    for experience in render_input.experiences:
        _trim_bullets_to_cap(
            experience,
            max_bullets=max_bullets,
            section_type=RenderSectionType.EXPERIENCE,
            decisions=decisions,
            warnings=warnings,
            reason=f"Page policy {policy.value} limits bullets per experience.",
        )

    project_bullet_cap = max(1, max_bullets - 1)
    for project in render_input.projects:
        _trim_bullets_to_cap(
            project,
            max_bullets=project_bullet_cap,
            section_type=RenderSectionType.PROJECTS,
            decisions=decisions,
            warnings=warnings,
            reason=f"Page policy {policy.value} limits bullets per project.",
        )


def _compact_summary(
    render_input: RenderJobInput,
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
) -> None:
    """Compress summary by truncating at a deterministic word boundary."""

    if render_input.summary is None or not render_input.summary.truncation_eligible:
        return
    if len(render_input.summary.text) <= SUMMARY_COMPACT_MAX_CHARS:
        return
    if render_input.summary.text.endswith("..."):
        return

    original_text = render_input.summary.text
    compacted_text = _truncate_text_at_word_boundary(
        original_text,
        SUMMARY_COMPACT_MAX_CHARS,
    )
    _set_render_input_field(
        render_input,
        "summary",
        render_input.summary.model_copy(update={"text": compacted_text}),
    )
    decisions.append(
        LayoutTrimDecision(
            action=TrimAction.TRIM_SUMMARY,
            section_type=RenderSectionType.SUMMARY,
            reason="Summary was shortened before trimming critical experience bullets.",
            before_count=len(original_text),
            after_count=len(compacted_text),
            estimated_lines_saved=1,
        )
    )
    warnings.append("Shortened summary to reduce layout overflow.")


def _compact_skills(
    compact_sections: set[RenderSectionType],
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
    render_input: RenderJobInput,
) -> None:
    """Mark skills for compact rendering before deleting core experience content."""

    if not render_input.skills or RenderSectionType.SKILLS in compact_sections:
        return
    compact_sections.add(RenderSectionType.SKILLS)
    decisions.append(
        LayoutTrimDecision(
            action=TrimAction.COMPACT_SECTION,
            section_type=RenderSectionType.SKILLS,
            reason="Skills were marked compact before trimming experience bullets.",
            before_count=len(render_input.skills),
            after_count=len(render_input.skills),
            estimated_lines_saved=max(1, len(render_input.skills) // 3),
        )
    )
    warnings.append("Compacted skills section before removing core experience content.")


def _remove_low_priority_project(
    render_input: RenderJobInput,
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
) -> bool:
    """Remove the lowest-priority truncation-eligible project, preserving order."""

    candidates = [
        project for project in render_input.projects if project.truncation_eligible
    ]
    if not candidates:
        return False

    section_priority = _section_priority(render_input, RenderSectionType.PROJECTS)
    project_to_remove = min(
        candidates,
        key=lambda project: _trim_priority_key(project, section_priority),
    )
    _set_render_input_field(
        render_input,
        "projects",
        [
            project
            for project in render_input.projects
            if project.id != project_to_remove.id
        ],
    )
    decisions.append(
        LayoutTrimDecision(
            action=TrimAction.REMOVE_PROJECT,
            section_type=RenderSectionType.PROJECTS,
            reason="Lower-priority project removed before trimming experience bullets.",
            item_id=project_to_remove.id,
            removed_item_ids=[project_to_remove.id],
            before_count=len(render_input.projects) + 1,
            after_count=len(render_input.projects),
            estimated_lines_saved=_estimate_project_lines(project_to_remove),
        )
    )
    warnings.append(f"Removed lower-priority project: {project_to_remove.id}.")
    return True


def _trim_experience_bullet(
    render_input: RenderJobInput,
    policy: LayoutPagePolicy,
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
) -> bool:
    """Trim one low-priority eligible experience bullet while preserving minimums."""

    min_bullets = POLICY_MIN_EXPERIENCE_BULLETS[policy]
    candidate_pairs: list[tuple[RenderExperience, RenderBullet]] = []
    section_priority = _section_priority(render_input, RenderSectionType.EXPERIENCE)
    for experience in render_input.experiences:
        section_min = _section_min_bullets(
            render_input,
            RenderSectionType.EXPERIENCE,
        )
        effective_min = max(min_bullets, section_min or 0)
        if len(experience.bullets) <= effective_min:
            continue
        for bullet in experience.bullets:
            if bullet.truncation_eligible:
                candidate_pairs.append((experience, bullet))

    if not candidate_pairs:
        return False

    experience, bullet = min(
        candidate_pairs,
        key=lambda pair: (
            section_priority,
            _score_for_trimming(pair[1].confidence.confidence_score),
            pair[0].display_order,
            pair[1].display_order,
            pair[1].id,
        ),
    )
    experience.bullets = [
        existing_bullet
        for existing_bullet in experience.bullets
        if existing_bullet.id != bullet.id
    ]
    decisions.append(
        LayoutTrimDecision(
            action=TrimAction.TRIM_BULLETS,
            section_type=RenderSectionType.EXPERIENCE,
            reason="Trimmed lowest-priority eligible experience bullet after projects.",
            item_id=experience.id,
            removed_bullet_ids=[bullet.id],
            before_count=len(experience.bullets) + 1,
            after_count=len(experience.bullets),
            estimated_lines_saved=BULLET_LINE_COST,
        )
    )
    warnings.append(
        f"Trimmed lower-priority experience bullet {bullet.id} from {experience.id}."
    )
    return True


def _remove_low_priority_skill_group(
    render_input: RenderJobInput,
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
) -> bool:
    """Remove the lowest-priority skill group after safer compaction attempts."""

    if len(render_input.skills) <= 1:
        return False

    section_priority = _section_priority(render_input, RenderSectionType.SKILLS)
    skill_group = min(
        render_input.skills,
        key=lambda group: _trim_priority_key(group, section_priority),
    )
    _set_render_input_field(
        render_input,
        "skills",
        [group for group in render_input.skills if group.id != skill_group.id],
    )
    decisions.append(
        LayoutTrimDecision(
            action=TrimAction.REMOVE_SKILL_GROUP,
            section_type=RenderSectionType.SKILLS,
            reason="Removed lower-priority skill group after preserving experience.",
            item_id=skill_group.id,
            removed_item_ids=[skill_group.id],
            before_count=len(render_input.skills) + 1,
            after_count=len(render_input.skills),
            estimated_lines_saved=SKILL_GROUP_STANDARD_LINE_COST,
        )
    )
    warnings.append(f"Removed lower-priority skill group: {skill_group.id}.")
    return True


def _trim_bullets_to_cap(
    item: RenderExperience | RenderProject,
    *,
    max_bullets: int,
    section_type: RenderSectionType,
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
    reason: str,
) -> None:
    """Trim bullets to a deterministic cap while preserving high-scoring bullets."""

    if len(item.bullets) <= max_bullets:
        return

    eligible_bullets = [
        bullet for bullet in item.bullets if bullet.truncation_eligible
    ]
    protected_bullets = [
        bullet for bullet in item.bullets if not bullet.truncation_eligible
    ]
    protected_count = len(protected_bullets)
    if protected_count >= max_bullets:
        return

    kept_eligible_count = max_bullets - protected_count
    kept_eligible_bullets = _top_priority_items(eligible_bullets, kept_eligible_count)
    kept_bullet_ids = {bullet.id for bullet in [*protected_bullets, *kept_eligible_bullets]}
    removed_bullets = [
        bullet for bullet in item.bullets if bullet.id not in kept_bullet_ids
    ]
    item.bullets = [
        bullet for bullet in item.bullets if bullet.id in kept_bullet_ids
    ]

    removed_bullet_ids = [bullet.id for bullet in removed_bullets]
    decisions.append(
        LayoutTrimDecision(
            action=TrimAction.TRIM_BULLETS,
            section_type=section_type,
            reason=reason,
            item_id=item.id,
            removed_bullet_ids=removed_bullet_ids,
            before_count=len(item.bullets) + len(removed_bullets),
            after_count=len(item.bullets),
            estimated_lines_saved=len(removed_bullets) * BULLET_LINE_COST,
        )
    )
    warnings.append(
        f"Trimmed bullets from {item.id}: " + ", ".join(removed_bullet_ids)
    )


def _hide_empty_optional_sections(
    render_input: RenderJobInput,
    decisions: list[LayoutTrimDecision],
    warnings: list[str],
) -> None:
    """Hide optional sections that became empty after deterministic trimming."""

    content_counts = {
        RenderSectionType.PROJECTS: len(render_input.projects),
        RenderSectionType.SKILLS: len(render_input.skills),
        RenderSectionType.EDUCATION: len(render_input.education),
        RenderSectionType.CERTIFICATIONS: len(render_input.certifications),
    }
    visibility_updates = dict(render_input.section_visibility)
    for section in render_input.sections:
        if section.section_type not in content_counts:
            continue
        if content_counts[section.section_type] > 0:
            continue
        if not section.visible and not visibility_updates.get(section.section_type, False):
            continue
        section.visible = False
        visibility_updates[section.section_type] = False
        decisions.append(
            LayoutTrimDecision(
                action=TrimAction.HIDE_EMPTY_SECTION,
                section_type=section.section_type,
                reason="Optional section hidden after all content was removed.",
            )
        )
        warnings.append(f"Hidden empty section: {section.section_type.value}.")
    _set_render_input_field(render_input, "section_visibility", visibility_updates)


def _build_section_trim_metadata(
    original_counts: dict[RenderSectionType, tuple[int, int]],
    adjusted_counts: dict[RenderSectionType, tuple[int, int]],
    decisions: list[LayoutTrimDecision],
    compact_sections: set[RenderSectionType],
) -> list[SectionTrimMetadata]:
    """Build section-level trim metadata for diagnostics."""

    metadata: list[SectionTrimMetadata] = []
    for section_type in RenderSectionType:
        original_item_count, original_bullet_count = original_counts.get(section_type, (0, 0))
        adjusted_item_count, adjusted_bullet_count = adjusted_counts.get(section_type, (0, 0))
        section_decisions = [
            decision for decision in decisions if decision.section_type == section_type
        ]
        metadata.append(
            SectionTrimMetadata(
                section_type=section_type,
                render_mode=(
                    LayoutRenderMode.COMPACT
                    if section_type in compact_sections
                    else LayoutRenderMode.STANDARD
                ),
                original_item_count=original_item_count,
                adjusted_item_count=adjusted_item_count,
                original_bullet_count=original_bullet_count,
                adjusted_bullet_count=adjusted_bullet_count,
                removed_item_ids=[
                    item_id
                    for decision in section_decisions
                    for item_id in decision.removed_item_ids
                ],
                removed_bullet_ids=[
                    bullet_id
                    for decision in section_decisions
                    for bullet_id in decision.removed_bullet_ids
                ],
                estimated_lines_saved=sum(
                    decision.estimated_lines_saved for decision in section_decisions
                ),
                warnings=[decision.reason for decision in section_decisions],
            )
        )
    return metadata


def _section_counts(render_input: RenderJobInput) -> dict[RenderSectionType, tuple[int, int]]:
    """Return item and bullet counts for each section."""

    return {
        RenderSectionType.PERSONAL_INFO: (1, 0),
        RenderSectionType.SUMMARY: (1 if render_input.summary else 0, 0),
        RenderSectionType.EXPERIENCE: (
            len(render_input.experiences),
            sum(len(experience.bullets) for experience in render_input.experiences),
        ),
        RenderSectionType.PROJECTS: (
            len(render_input.projects),
            sum(len(project.bullets) for project in render_input.projects),
        ),
        RenderSectionType.SKILLS: (len(render_input.skills), 0),
        RenderSectionType.EDUCATION: (len(render_input.education), 0),
        RenderSectionType.CERTIFICATIONS: (len(render_input.certifications), 0),
    }


def _resolve_page_policy(
    page_policy: LayoutPagePolicy | TargetPagePolicy,
) -> LayoutPagePolicy:
    """Map external render page policies to layout manager policies."""

    if isinstance(page_policy, LayoutPagePolicy):
        return page_policy
    if page_policy == TargetPagePolicy.STRICT_ONE_PAGE:
        return LayoutPagePolicy.ONE_PAGE_STRICT
    if page_policy in {TargetPagePolicy.PREFER_ONE_PAGE, TargetPagePolicy.AUTO}:
        return LayoutPagePolicy.ONE_PAGE_FLEX
    if page_policy == TargetPagePolicy.TWO_PAGE_MAX:
        return LayoutPagePolicy.TWO_PAGE_MAX
    raise ValueError(f"Unsupported page policy: {page_policy}")


def _max_allowed_lines(
    render_input: RenderJobInput,
    policy: LayoutPagePolicy,
) -> int:
    """Resolve page line budget from policy and optional input constraints."""

    policy_budget = POLICY_LINE_BUDGETS[policy]
    max_page_budget = policy_budget
    if render_input.layout_constraints.max_pages is not None:
        max_page_budget = min(
            policy_budget,
            render_input.layout_constraints.max_pages
            * POLICY_LINE_BUDGETS[LayoutPagePolicy.ONE_PAGE_FLEX],
        )
    if render_input.layout_constraints.max_lines is None:
        return max_page_budget
    return min(max_page_budget, render_input.layout_constraints.max_lines)


def _section_for_type(
    render_input: RenderJobInput,
    section_type: RenderSectionType,
):
    """Return section metadata for a section type if present."""

    for section in render_input.sections:
        if section.section_type == section_type:
            return section
    return None


def _section_max_bullets(
    render_input: RenderJobInput,
    section_type: RenderSectionType,
) -> int | None:
    """Read section-level max bullet constraint."""

    section = _section_for_type(render_input, section_type)
    if section is None:
        return None
    return section.layout_constraints.max_bullets


def _section_min_bullets(
    render_input: RenderJobInput,
    section_type: RenderSectionType,
) -> int | None:
    """Read section-level minimum bullet constraint."""

    section = _section_for_type(render_input, section_type)
    if section is None:
        return None
    return section.layout_constraints.min_bullets


def _section_max_lines(
    render_input: RenderJobInput,
    section_type: RenderSectionType,
) -> int | None:
    """Read section-level max line constraint."""

    section = _section_for_type(render_input, section_type)
    if section is None:
        return None
    return section.layout_constraints.max_lines


def _section_priority(
    render_input: RenderJobInput,
    section_type: RenderSectionType,
) -> int:
    """Read section priority; lower values are easier to trim."""

    section = _section_for_type(render_input, section_type)
    if section is None:
        return 50
    return section.layout_constraints.priority


def _top_priority_items(items: list, limit: int) -> list:
    """Keep high-priority items by confidence and original display order."""

    if limit <= 0:
        return []
    prioritized = sorted(
        items,
        key=lambda item: (
            _score_for_keeping(item.confidence.confidence_score),
            -item.display_order,
            item.id,
        ),
        reverse=True,
    )
    return prioritized[:limit]


def _trim_priority_key(item, section_priority: int) -> tuple[int, float, int, str]:
    """Sort key for selecting lower-value content to trim first."""

    return (
        section_priority,
        _score_for_trimming(item.confidence.confidence_score),
        -item.display_order,
        item.id,
    )


def _score_for_keeping(score: float | None) -> float:
    """Treat missing relevance/confidence as medium priority."""

    return 0.5 if score is None else score


def _score_for_trimming(score: float | None) -> float:
    """Lower score means safer to trim."""

    return 0.5 if score is None else score


def _estimate_project_lines(project: RenderProject) -> int:
    """Estimate line-equivalent cost for one project."""

    return PROJECT_BASE_LINE_COST + len(project.bullets) * BULLET_LINE_COST


def _ordered_by_display_order(items: list) -> list:
    """Return items in original deterministic display order."""

    return sorted(items, key=lambda item: (item.display_order, item.id))


def _set_render_input_field(
    render_input: RenderJobInput,
    field_name: str,
    value: object,
) -> None:
    """Update the internal adjusted copy without validating transient states."""

    object.__setattr__(render_input, field_name, value)


def _truncate_text_at_word_boundary(text: str, max_chars: int) -> str:
    """Trim text at a word boundary without inventing replacement content."""

    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0].strip()
    if not truncated:
        truncated = text[:max_chars].strip()
    return truncated.rstrip(".,;:") + "..."
