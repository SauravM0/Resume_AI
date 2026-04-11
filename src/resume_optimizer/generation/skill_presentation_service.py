"""Deterministic skill presentation module for Phase 5."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import (
    GenerationQualitySignals,
    GenerationStyleMode,
    QualitySignal,
    QualitySignalSeverity,
    SkillGroupPresentation,
    SkillPresentationInput,
    SkillPresentationOutput,
)
from .quality_validator import merge_quality_signals, validate_skill_presentation_quality
from ..models import NonEmptyStr
from ..phase1_role_modeling import FunctionalRoleFamily

_TAXONOMY_DIR = Path(__file__).resolve().parents[1] / "config" / "taxonomy"

_GROUP_PRIORITY_BY_ROLE_FAMILY: dict[FunctionalRoleFamily, list[str]] = {
    FunctionalRoleFamily.BACKEND: ["Languages", "Frameworks", "Cloud/Platforms", "Databases", "Tools"],
    FunctionalRoleFamily.FRONTEND: ["Frameworks", "Languages", "Tools", "Cloud/Platforms", "Methodologies"],
    FunctionalRoleFamily.FULLSTACK: ["Languages", "Frameworks", "Cloud/Platforms", "Databases", "Tools"],
    FunctionalRoleFamily.DATA: ["Languages", "Databases", "Cloud/Platforms", "Tools", "Methodologies"],
    FunctionalRoleFamily.ANALYTICS: ["Databases", "Languages", "Tools", "Cloud/Platforms", "Methodologies"],
    FunctionalRoleFamily.ML: ["Languages", "Frameworks", "Cloud/Platforms", "Tools", "Methodologies"],
    FunctionalRoleFamily.DEVOPS: ["Cloud/Platforms", "Tools", "Languages", "Methodologies", "Databases"],
    FunctionalRoleFamily.PLATFORM: ["Cloud/Platforms", "Tools", "Languages", "Databases", "Methodologies"],
    FunctionalRoleFamily.SECURITY: ["Tools", "Cloud/Platforms", "Languages", "Methodologies", "Databases"],
    FunctionalRoleFamily.MOBILE: ["Frameworks", "Languages", "Tools", "Cloud/Platforms", "Methodologies"],
    FunctionalRoleFamily.PRODUCT: ["Methodologies", "Tools", "Languages", "Frameworks", "Cloud/Platforms"],
    FunctionalRoleFamily.DESIGN: ["Tools", "Methodologies", "Frameworks", "Languages", "Cloud/Platforms"],
    FunctionalRoleFamily.QA: ["Tools", "Languages", "Frameworks", "Methodologies", "Cloud/Platforms"],
    FunctionalRoleFamily.SUPPORT: ["Tools", "Cloud/Platforms", "Methodologies", "Languages", "Databases"],
    FunctionalRoleFamily.OTHER: ["Languages", "Frameworks", "Cloud/Platforms", "Databases", "Tools"],
}

_METHODOLOGY_TERMS = {
    "Agile": {"agile"},
    "CI/CD": {"ci/cd", "cicd"},
    "Microservices": {"microservices"},
    "REST APIs": {"rest", "rest api", "rest apis"},
    "ETL": {"etl"},
    "A/B Testing": {"a/b testing", "ab testing"},
}


def present_skills(skill_input: SkillPresentationInput) -> SkillPresentationOutput:
    """Convert upstream-selected skills into compact grouped presentation text."""

    taxonomy = _load_taxonomy()
    normalized_skills, warnings = _normalize_and_dedupe_skills(skill_input, taxonomy)
    ranked_skills = _rank_skills(skill_input, normalized_skills)
    grouped_skills, grouping_warnings = _group_skills(skill_input, ranked_skills, taxonomy)
    warnings.extend(grouping_warnings)
    rendered_skill_lines = _render_skill_lines(skill_input, grouped_skills)
    quality_signals = _build_quality_signals(skill_input, grouped_skills, rendered_skill_lines, warnings)

    result = SkillPresentationOutput(
        section_id=skill_input.section_id,
        grouped_skills=grouped_skills,
        rendered_skill_lines=rendered_skill_lines,
        warnings=warnings,
        quality_signals=quality_signals,
        role_family=skill_input.parsed_job_output.functional_role_family,
        organizational_role_mode=skill_input.parsed_job_output.organizational_role_mode,
        style_mode=skill_input.style_policy.style_mode,
    )
    return result.model_copy(
        update={
            "quality_signals": merge_quality_signals(
                result.quality_signals,
                validate_skill_presentation_quality(result),
            )
        }
    )


def _load_taxonomy() -> dict[str, dict[str, set[str]]]:
    return {
        "Languages": _load_canonical_terms("programming_languages.json"),
        "Frameworks": _load_canonical_terms("frameworks.json"),
        "Cloud/Platforms": {
            **_load_canonical_terms("cloud_services.json"),
            **_load_canonical_terms("tool_platforms.json"),
        },
        "Databases": {
            canonical: synonyms
            for canonical, synonyms in _load_canonical_terms("tool_platforms.json").items()
            if canonical in {"PostgreSQL", "Redis", "Snowflake", "BigQuery", "MySQL", "MongoDB"}
        },
        "Tools": _load_canonical_terms("tool_platforms.json"),
        "Methodologies": {canonical: set(synonyms) for canonical, synonyms in _METHODOLOGY_TERMS.items()},
    }


def _load_canonical_terms(filename: str) -> dict[str, set[str]]:
    payload = json.loads((_TAXONOMY_DIR / filename).read_text(encoding="utf-8"))
    return {
        canonical: {canonical.casefold(), *(value.casefold() for value in aliases)}
        for canonical, aliases in payload.get("canonical_terms", {}).items()
    }


def _normalize_and_dedupe_skills(
    skill_input: SkillPresentationInput,
    taxonomy: dict[str, dict[str, set[str]]],
) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    seen: set[str] = set()
    normalized: list[dict[str, object]] = []

    for skill in skill_input.selected_skills:
        canonical_name = _canonical_skill_name(skill.skill_name, taxonomy)
        normalized_key = canonical_name.casefold()
        if normalized_key in seen:
            warnings.append(f"deduplicated overlapping skill naming for {canonical_name}")
            continue
        seen.add(normalized_key)
        normalized.append(
            {
                "canonical_name": canonical_name,
                "source_item_id": skill.source_item_id,
                "relevance_score": skill.relevance_score,
                "matched_requirements": list(skill.matched_requirements),
            }
        )
    return normalized, warnings


def _canonical_skill_name(skill_name: str, taxonomy: dict[str, dict[str, set[str]]]) -> str:
    normalized = skill_name.casefold()
    for groups in taxonomy.values():
        for canonical, aliases in groups.items():
            if normalized in aliases:
                return canonical
    if normalized in {"js", "javascript"}:
        return "JavaScript"
    if normalized in {"node", "nodejs", "node.js"}:
        return "Node.js"
    return skill_name.strip()


def _rank_skills(
    skill_input: SkillPresentationInput,
    normalized_skills: list[dict[str, object]],
) -> list[dict[str, object]]:
    must_have = {skill.casefold() for skill in skill_input.parsed_job_output.must_have_skills}
    preferred = {skill.casefold() for skill in skill_input.parsed_job_output.preferred_skills}

    def sort_key(skill: dict[str, object]) -> tuple[int, float, str]:
        canonical = str(skill["canonical_name"]).casefold()
        if canonical in must_have:
            priority = 0
        elif canonical in preferred:
            priority = 1
        else:
            priority = 2
        return (priority, -float(skill["relevance_score"]), canonical)

    return sorted(normalized_skills, key=sort_key)


def _group_skills(
    skill_input: SkillPresentationInput,
    ranked_skills: list[dict[str, object]],
    taxonomy: dict[str, dict[str, set[str]]],
) -> tuple[list[SkillGroupPresentation], list[str]]:
    warnings: list[str] = []
    grouped: dict[str, list[dict[str, object]]] = {group: [] for group in taxonomy}
    overflow: list[dict[str, object]] = []

    for skill in ranked_skills:
        assigned = False
        canonical = str(skill["canonical_name"])
        for group_name, group_taxonomy in taxonomy.items():
            if canonical in group_taxonomy:
                grouped[group_name].append(skill)
                assigned = True
                break
        if not assigned:
            overflow.append(skill)

    if overflow:
        grouped["Tools"].extend(overflow)
        warnings.append("some skills did not match a known taxonomy group and were placed under Tools")

    priority_order = _GROUP_PRIORITY_BY_ROLE_FAMILY[skill_input.parsed_job_output.functional_role_family]
    max_groups = skill_input.page_constraints.max_skill_groups
    max_skills_per_group = skill_input.page_constraints.max_skills_per_group

    presentations: list[SkillGroupPresentation] = []
    for index, group_name in enumerate(priority_order):
        skills = grouped.get(group_name, [])
        if not skills:
            continue
        selected = skills[:max_skills_per_group]
        presentations.append(
            SkillGroupPresentation(
                group_id=f"group.skills.{index + 1}",
                label=group_name,
                skill_names=[str(skill["canonical_name"]) for skill in selected],
                source_item_ids=[str(skill["source_item_id"]) for skill in selected],
            )
        )
        if len(presentations) >= max_groups:
            break

    if not presentations:
        raise ValueError("skill presentation requires at least one renderable grouped skill")
    return presentations, warnings


def _render_skill_lines(
    skill_input: SkillPresentationInput,
    groups: list[SkillGroupPresentation],
) -> list[NonEmptyStr]:
    style_mode = skill_input.style_policy.style_mode
    lines: list[str] = []
    for group in groups:
        if style_mode == GenerationStyleMode.DIRECT:
            lines.append(f"{group.label}: {', '.join(group.skill_names)}")
        else:
            lines.append(f"{group.label}: " + " | ".join(group.skill_names))
    return lines


def _build_quality_signals(
    skill_input: SkillPresentationInput,
    groups: list[SkillGroupPresentation],
    rendered_skill_lines: list[str],
    warnings: list[str],
) -> GenerationQualitySignals:
    warning_signals: list[QualitySignal] = [
        QualitySignal(
            signal_id=f"quality.skills.warning.{index + 1}",
            severity=QualitySignalSeverity.WARNING,
            message=warning,
            section_id=skill_input.section_id,
        )
        for index, warning in enumerate(warnings)
    ]

    if len(rendered_skill_lines) > skill_input.page_constraints.max_skill_groups:
        warning_signals.append(
            QualitySignal(
                signal_id=f"quality.skills.compactness.{skill_input.section_id}",
                severity=QualitySignalSeverity.WARNING,
                message="skill rendering is less compact than the configured group target",
                section_id=skill_input.section_id,
            )
        )

    style_alignment_score = 0.95 - (0.06 * len(warning_signals))
    return GenerationQualitySignals(
        warnings=warning_signals,
        provenance_coverage_score=1.0,
        style_alignment_score=round(max(0.0, min(1.0, style_alignment_score)), 4),
    )
