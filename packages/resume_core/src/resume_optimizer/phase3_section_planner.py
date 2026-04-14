"""Structural section planning for Phase 3.

This module decides what content should move forward and in what order before any
copy generation or rendering occurs. The goal is deterministic, inspectable planning
that later phases can consume without coupling to visual layout concerns.
"""

from __future__ import annotations

from enum import StrEnum
import re

from pydantic import Field

from .models import NonEmptyStr, StableId, StrictModel
from .phase3_models import (
    OmissionReason,
    Phase3GenerationPayload,
    Phase3SelectedCertificationPayload,
    Phase3SelectedExperiencePayload,
    Phase3SelectedProjectPayload,
    Phase3SelectedSkillPayload,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#./-]*")
_STOPWORDS = {"a", "an", "and", "for", "in", "of", "the", "to", "with"}

# These limits keep the planner compact without encoding rendering details.
_STANDARD_MAX_EXPERIENCES = 3
_COMPACT_MAX_EXPERIENCES = 2
_STANDARD_MAX_PROJECTS = 2
_COMPACT_MAX_PROJECTS = 1
_STANDARD_MAX_SKILLS = 6
_COMPACT_MAX_SKILLS = 4

# Certifications below this relevance score are usually noise unless the profile is sparse.
_CERTIFICATION_RELEVANCE_FLOOR = 0.45

# When one experience dominates relevance, prefer depth there over padding other sections.
_DOMINANT_EXPERIENCE_SCORE_GAP = 0.15

# Overlapping projects above this token-overlap threshold are usually redundant variants.
_PROJECT_OVERLAP_THRESHOLD = 0.6


class PlanningMode(StrEnum):
    """Structural density target for later rendering phases."""

    STANDARD = "standard"
    COMPACT = "compact"


class ProjectEmphasis(StrEnum):
    """How strongly projects should be surfaced relative to experience."""

    EMPHASIZE = "emphasize"
    STANDARD = "standard"
    MINIMIZE = "minimize"


class CertificationVisibility(StrEnum):
    """Whether certifications should appear in the structural plan."""

    SHOW = "show"
    HIDE = "hide"


class PlannedBullet(StrictModel):
    """Bullet selection carried forward by the section planner."""

    bullet_id: StableId
    rationale: NonEmptyStr


class PlannedExperienceItem(StrictModel):
    """Experience item retained in the final structural plan."""

    source_item_id: StableId
    bullet_count: int = Field(ge=0)
    bullets: list[PlannedBullet] = Field(default_factory=list)
    rationale: NonEmptyStr


class PlannedProjectItem(StrictModel):
    """Project item retained in the final structural plan."""

    source_item_id: StableId
    bullet_count: int = Field(ge=0)
    bullets: list[PlannedBullet] = Field(default_factory=list)
    rationale: NonEmptyStr


class PlannedSkillItem(StrictModel):
    """Skill item retained in the final structural plan."""

    source_item_id: StableId
    rationale: NonEmptyStr


class PlannedCertificationItem(StrictModel):
    """Certification item retained in the final structural plan."""

    source_item_id: StableId
    rationale: NonEmptyStr


class PlannedOmission(StrictModel):
    """Explicit omission decision recorded for downstream explanation and verification."""

    source_item_id: StableId
    source_item_type: NonEmptyStr
    reason: OmissionReason
    rationale: NonEmptyStr


class Phase3SectionPlan(StrictModel):
    """Deterministic structural plan for later generation and rendering phases."""

    mode: PlanningMode = PlanningMode.STANDARD
    project_emphasis: ProjectEmphasis = ProjectEmphasis.STANDARD
    certification_visibility: CertificationVisibility = CertificationVisibility.HIDE
    experiences: list[PlannedExperienceItem] = Field(default_factory=list)
    projects: list[PlannedProjectItem] = Field(default_factory=list)
    skills: list[PlannedSkillItem] = Field(default_factory=list)
    certifications: list[PlannedCertificationItem] = Field(default_factory=list)
    omitted_items: list[PlannedOmission] = Field(default_factory=list)


def plan_phase3_sections(
    payload: Phase3GenerationPayload,
    *,
    mode: PlanningMode = PlanningMode.STANDARD,
) -> Phase3SectionPlan:
    """Build a deterministic structural plan from the assembled Phase 3 payload."""

    experience_limit = (
        _COMPACT_MAX_EXPERIENCES if mode == PlanningMode.COMPACT else _STANDARD_MAX_EXPERIENCES
    )
    project_limit = (
        _COMPACT_MAX_PROJECTS if mode == PlanningMode.COMPACT else _STANDARD_MAX_PROJECTS
    )
    skill_limit = _COMPACT_MAX_SKILLS if mode == PlanningMode.COMPACT else _STANDARD_MAX_SKILLS

    sorted_experiences = sorted(
        payload.selected_experiences,
        key=lambda item: (item.relevance_score, item.current, _bullet_density(item.bullets), item.id),
        reverse=True,
    )
    kept_experiences = sorted_experiences[:experience_limit]
    omitted_items: list[PlannedOmission] = [
        PlannedOmission(
            source_item_id=item.id,
            source_item_type="experience",
            reason=OmissionReason.SPACE_CONSTRAINT,
            rationale="Higher-relevance experience content already fills the plan.",
        )
        for item in sorted_experiences[experience_limit:]
    ]

    dominant_experience = _has_dominant_experience(kept_experiences, sorted_experiences)
    planned_experiences = [
        PlannedExperienceItem(
            source_item_id=item.id,
            bullet_count=len(_planned_experience_bullets(item, dominant_experience=dominant_experience, mode=mode)),
            bullets=_planned_experience_bullets(item, dominant_experience=dominant_experience, mode=mode),
            rationale=(
                "Recent and highly relevant experience should anchor the resume."
                if item.current or item == kept_experiences[0]
                else "Relevant supporting experience adds depth without diluting the plan."
            ),
        )
        for item in kept_experiences
    ]

    project_emphasis = _determine_project_emphasis(payload, dominant_experience)
    kept_projects, project_omissions = _plan_projects(
        payload.selected_projects,
        mode=mode,
        emphasis=project_emphasis,
    )
    omitted_items.extend(project_omissions)
    planned_projects = [
        PlannedProjectItem(
            source_item_id=item.id,
            bullet_count=len(_planned_project_bullets(item, emphasis=project_emphasis, mode=mode)),
            bullets=_planned_project_bullets(item, emphasis=project_emphasis, mode=mode),
            rationale=(
                "Project evidence reinforces target-role themes not fully covered by experience."
                if project_emphasis == ProjectEmphasis.EMPHASIZE
                else "Project evidence is included selectively as supporting proof."
            ),
        )
        for item in kept_projects[:project_limit]
    ]
    for item in kept_projects[project_limit:]:
        omitted_items.append(
            PlannedOmission(
                source_item_id=item.id,
                source_item_type="project",
                reason=OmissionReason.SPACE_CONSTRAINT,
                rationale="Project section is intentionally compact for this plan.",
            )
        )

    planned_skills, skill_omissions = _plan_skills(payload.matched_skills, skill_limit)
    omitted_items.extend(skill_omissions)

    planned_certifications, certification_visibility, certification_omissions = _plan_certifications(
        payload.selected_certifications,
        sparse_profile=not planned_experiences and not planned_projects,
    )
    omitted_items.extend(certification_omissions)

    return Phase3SectionPlan(
        mode=mode,
        project_emphasis=project_emphasis,
        certification_visibility=certification_visibility,
        experiences=planned_experiences,
        projects=planned_projects,
        skills=planned_skills,
        certifications=planned_certifications,
        omitted_items=sorted(
            omitted_items,
            key=lambda item: (item.source_item_type, item.reason.value, item.source_item_id),
        ),
    )


def _planned_experience_bullets(
    item: Phase3SelectedExperiencePayload,
    *,
    dominant_experience: bool,
    mode: PlanningMode,
) -> list[PlannedBullet]:
    if dominant_experience and item.relevance_score >= 0.85:
        bullet_limit = 3 if mode == PlanningMode.STANDARD else 2
    else:
        bullet_limit = 2 if mode == PlanningMode.STANDARD else 1
    selected_bullets = item.bullets[:bullet_limit]
    return [
        PlannedBullet(
            bullet_id=bullet.id,
            rationale="Selected for strong relevance and supported factual specificity.",
        )
        for bullet in selected_bullets
    ]


def _planned_project_bullets(
    item: Phase3SelectedProjectPayload,
    *,
    emphasis: ProjectEmphasis,
    mode: PlanningMode,
) -> list[PlannedBullet]:
    if emphasis == ProjectEmphasis.EMPHASIZE:
        bullet_limit = 2 if mode == PlanningMode.STANDARD else 1
    elif emphasis == ProjectEmphasis.MINIMIZE:
        bullet_limit = 1
    else:
        bullet_limit = 1 if mode == PlanningMode.COMPACT else min(2, len(item.bullets))
    return [
        PlannedBullet(
            bullet_id=bullet.id,
            rationale="Selected because it adds differentiated project evidence.",
        )
        for bullet in item.bullets[:bullet_limit]
    ]


def _plan_projects(
    projects: list[Phase3SelectedProjectPayload],
    *,
    mode: PlanningMode,
    emphasis: ProjectEmphasis,
) -> tuple[list[Phase3SelectedProjectPayload], list[PlannedOmission]]:
    sorted_projects = sorted(
        projects,
        key=lambda item: (item.relevance_score, _bullet_density(item.bullets), item.id),
        reverse=True,
    )
    kept: list[Phase3SelectedProjectPayload] = []
    omissions: list[PlannedOmission] = []
    for item in sorted_projects:
        duplicate_of = next((kept_item for kept_item in kept if _projects_overlap(kept_item, item)), None)
        if duplicate_of is not None:
            omissions.append(
                PlannedOmission(
                    source_item_id=item.id,
                    source_item_type="project",
                    reason=OmissionReason.REDUNDANT,
                    rationale=f"Overlaps heavily with retained project {duplicate_of.id}.",
                )
            )
            continue
        if emphasis == ProjectEmphasis.MINIMIZE and item.relevance_score < 0.7:
            omissions.append(
                PlannedOmission(
                    source_item_id=item.id,
                    source_item_type="project",
                    reason=OmissionReason.SPACE_CONSTRAINT,
                    rationale="Projects are intentionally minimized because experience already covers the target fit.",
                )
            )
            continue
        kept.append(item)
    return kept, omissions


def _plan_skills(
    skills: list[Phase3SelectedSkillPayload],
    skill_limit: int,
) -> tuple[list[PlannedSkillItem], list[PlannedOmission]]:
    sorted_skills = sorted(
        skills,
        key=lambda item: (item.relevance_score, item.evidence_strength.value, item.id),
        reverse=True,
    )
    kept = [
        PlannedSkillItem(
            source_item_id=item.id,
            rationale="Selected because it is directly matched and supported upstream.",
        )
        for item in sorted_skills[:skill_limit]
    ]
    omissions = [
        PlannedOmission(
            source_item_id=item.id,
            source_item_type="skill",
            reason=OmissionReason.SPACE_CONSTRAINT,
            rationale="Lower-priority skills were omitted to keep the plan focused.",
        )
        for item in sorted_skills[skill_limit:]
    ]
    return kept, omissions


def _plan_certifications(
    certifications: list[Phase3SelectedCertificationPayload],
    *,
    sparse_profile: bool,
) -> tuple[list[PlannedCertificationItem], CertificationVisibility, list[PlannedOmission]]:
    kept: list[PlannedCertificationItem] = []
    omissions: list[PlannedOmission] = []
    for item in sorted(certifications, key=lambda cert: (cert.relevance_score, cert.id), reverse=True):
        if item.relevance_score < _CERTIFICATION_RELEVANCE_FLOOR and not sparse_profile:
            omissions.append(
                PlannedOmission(
                    source_item_id=item.id,
                    source_item_type="certification",
                    reason=OmissionReason.LOW_RELEVANCE,
                    rationale="Certification is not relevant enough to compete for limited resume space.",
                )
            )
            continue
        kept.append(
            PlannedCertificationItem(
                source_item_id=item.id,
                rationale="Certification adds credible support for a target requirement.",
            )
        )
    visibility = CertificationVisibility.SHOW if kept else CertificationVisibility.HIDE
    return kept, visibility, omissions


def _determine_project_emphasis(
    payload: Phase3GenerationPayload,
    dominant_experience: bool,
) -> ProjectEmphasis:
    if not payload.selected_projects:
        return ProjectEmphasis.MINIMIZE
    if not payload.selected_experiences:
        return ProjectEmphasis.EMPHASIZE
    if dominant_experience:
        return ProjectEmphasis.MINIMIZE
    if any("project" in hint.theme.casefold() for hint in payload.summary_hints):
        return ProjectEmphasis.EMPHASIZE
    if len(payload.selected_projects) >= len(payload.selected_experiences):
        return ProjectEmphasis.STANDARD
    return ProjectEmphasis.MINIMIZE


def _has_dominant_experience(
    kept_experiences: list[Phase3SelectedExperiencePayload],
    sorted_experiences: list[Phase3SelectedExperiencePayload],
) -> bool:
    if len(sorted_experiences) < 2 or not kept_experiences:
        return len(kept_experiences) == 1
    return (
        sorted_experiences[0].relevance_score - sorted_experiences[1].relevance_score
        >= _DOMINANT_EXPERIENCE_SCORE_GAP
    )


def _projects_overlap(
    left: Phase3SelectedProjectPayload,
    right: Phase3SelectedProjectPayload,
) -> bool:
    left_tokens = _project_tokens(left)
    right_tokens = _project_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens.intersection(right_tokens)) / len(left_tokens.union(right_tokens))
    return overlap >= _PROJECT_OVERLAP_THRESHOLD


def _project_tokens(item: Phase3SelectedProjectPayload) -> set[str]:
    text = " ".join([item.name, item.role or "", item.summary or "", *(bullet.text for bullet in item.bullets)])
    return {
        token for token in _TOKEN_PATTERN.findall(text.casefold()) if token not in _STOPWORDS
    }


def _bullet_density(bullets: list[object]) -> int:
    return len(bullets)
