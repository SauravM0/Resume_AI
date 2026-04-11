"""Compatibility adapters from the rebuilt Phase 1 schema to legacy contracts."""

from __future__ import annotations

from .job_models import (
    NormalizedJobAnalysis,
    NormalizedSkillRequirement,
    SkillPriority,
)
from .models import RoleType, SeniorityLevel
from .phase1_models import (
    Phase1JobAnalysis,
    PrioritizedRequirementTier,
)
from .phase1_role_modeling import OrganizationalRoleMode

_ROLE_MODE_TO_LEGACY_ROLE_TYPE: dict[OrganizationalRoleMode, RoleType] = {
    OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR: RoleType.INDIVIDUAL_CONTRIBUTOR,
    OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR: RoleType.INDIVIDUAL_CONTRIBUTOR,
    OrganizationalRoleMode.TECH_LEAD: RoleType.LEAD,
    OrganizationalRoleMode.PEOPLE_MANAGER: RoleType.MANAGER,
    OrganizationalRoleMode.DIRECTOR_OR_HEAD: RoleType.MANAGER,
    OrganizationalRoleMode.FOUNDER_OR_GENERALIST: RoleType.FOUNDER,
    OrganizationalRoleMode.CONSULTANT: RoleType.CONSULTANT,
    OrganizationalRoleMode.RESEARCHER: RoleType.RESEARCHER,
}

_SENIORITY_TO_LEGACY: dict[str, SeniorityLevel] = {
    "intern": SeniorityLevel.INTERN,
    "junior": SeniorityLevel.JUNIOR,
    "mid": SeniorityLevel.MID,
    "senior": SeniorityLevel.SENIOR,
    "staff": SeniorityLevel.STAFF,
    "principal": SeniorityLevel.PRINCIPAL,
    "director": SeniorityLevel.DIRECTOR,
    "executive": SeniorityLevel.EXECUTIVE,
}


def adapt_phase1_analysis_to_legacy_job_analysis(
    analysis: Phase1JobAnalysis,
) -> NormalizedJobAnalysis:
    """Project the rebuilt Phase 1 schema into the legacy Phase 2+ contract.

    This adapter preserves compatibility for existing consumers that still expect
    `NormalizedJobAnalysis` while the richer schema rolls out incrementally.
    """

    technical_skills = _stable_unique(
        [
            *analysis.must_have_skills,
            *analysis.nice_to_have_skills,
            *analysis.required_tools_platforms,
        ]
    )
    must_have_requirements = _stable_unique(
        [
            *analysis.primary_responsibility_clusters,
            *analysis.must_have_skills,
            *analysis.must_have_behaviors,
            *[
                item.requirement_text
                for item in analysis.prioritized_requirements
                if item.priority_tier
                in {
                    PrioritizedRequirementTier.CRITICAL,
                    PrioritizedRequirementTier.MUST_HAVE,
                }
            ],
        ]
    )
    nice_to_have_requirements = _stable_unique(
        [
            *analysis.nice_to_have_skills,
            *analysis.business_goal_signals,
            *analysis.impact_signals,
            *[
                item.requirement_text
                for item in analysis.prioritized_requirements
                if item.priority_tier
                in {
                    PrioritizedRequirementTier.IMPORTANT,
                    PrioritizedRequirementTier.NICE_TO_HAVE,
                }
            ],
        ]
    )

    return NormalizedJobAnalysis(
        role_type=_legacy_role_type(analysis.organizational_role_mode),
        seniority_level=_legacy_seniority(analysis.seniority_level),
        industry_domain=analysis.industry_domain,
        technical_skills=technical_skills,
        soft_skills=_stable_unique(analysis.must_have_behaviors),
        key_action_verbs=_stable_unique(analysis.key_action_verbs),
        must_have_requirements=must_have_requirements,
        nice_to_have_requirements=nice_to_have_requirements,
        company_culture_signals=_stable_unique(
            [*analysis.work_model_signals, *analysis.extraction_notes]
        ),
        years_experience_required=analysis.years_experience_requirement,
        prioritized_skills=_build_prioritized_skills(analysis),
    )


def _build_prioritized_skills(
    analysis: Phase1JobAnalysis,
) -> list[NormalizedSkillRequirement]:
    items: list[NormalizedSkillRequirement] = []
    seen: set[str] = set()

    for skill in analysis.must_have_skills:
        key = skill.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            NormalizedSkillRequirement(
                skill_name=skill,
                priority=SkillPriority.CORE,
            )
        )

    for skill in analysis.nice_to_have_skills:
        key = skill.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            NormalizedSkillRequirement(
                skill_name=skill,
                priority=SkillPriority.NICE_TO_HAVE,
            )
        )

    for skill in analysis.required_tools_platforms:
        key = skill.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            NormalizedSkillRequirement(
                skill_name=skill,
                priority=SkillPriority.IMPORTANT,
            )
        )

    return items


def _legacy_role_type(value: OrganizationalRoleMode | None) -> RoleType | None:
    if value is None:
        return None
    return _ROLE_MODE_TO_LEGACY_ROLE_TYPE.get(value)


def _legacy_seniority(value) -> SeniorityLevel | None:
    if value is None:
        return None
    return _SENIORITY_TO_LEGACY.get(value.value)


def _stable_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
