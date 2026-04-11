"""Deterministic assembler for compact Phase 3 generation payloads.

This module is the final handoff point where the richer Phase 3 selection
intelligence becomes generator-facing context. It still accepts the legacy
Phase 2 projection fields for backward compatibility, but it prefers the
resume-level `resume_selection_decision` when available so downstream phases
preserve broader selection breadth and machine-readable explanations.
"""

from __future__ import annotations

from collections import OrderedDict

from .job_models import SkillPriority
from .models import BulletEntry, CertificationEntry, ExperienceEntry, MasterProfile, ProjectEntry
from .phase2_models import (
    Phase2SelectionResult,
    SelectedExperience,
    SelectedProject,
    SelectedSkill,
)
from .phase3_models import (
    GenerationPreferences,
    Phase3JobAnalysisInput,
    Phase3AssemblerInput,
    Phase3GenerationPayload,
    Phase3LengthConstraints,
    Phase3RankingInput,
    Phase3RoleContext,
    Phase3SelectionInput,
    Phase3SelectedBulletPayload,
    Phase3SelectedCertificationPayload,
    Phase3SelectedExperiencePayload,
    Phase3SelectedProjectPayload,
    Phase3SelectedSkillPayload,
    Phase3SourceProfileInput,
    Phase3SummaryHint,
    Phase3ValidationMetadata,
)
from .ranking_models import RankingResponse
from .resume_selection_models import (
    ExperienceAggregateScore,
    ProjectAggregateScore,
    SkillHighlightScore,
)


def assemble_phase3_generation_payload(
    job_analysis: Phase3JobAnalysisInput,
    phase2_selection: Phase3SelectionInput,
    source_profile: Phase3SourceProfileInput,
    phase2_ranking: Phase3RankingInput,
    *,
    generation_preferences: GenerationPreferences | None = None,
) -> Phase3GenerationPayload:
    """Validate upstream artifacts and assemble the compact generator payload."""

    assembler_input = Phase3AssemblerInput(
        job_analysis=job_analysis,
        phase2_selection=phase2_selection,
        phase2_ranking=phase2_ranking,
        source_profile=source_profile,
        generation_preferences=generation_preferences,
    )
    return build_generation_payload(assembler_input)


def build_generation_payload(assembler_input: Phase3AssemblerInput) -> Phase3GenerationPayload:
    """Return a deterministic, generator-safe Phase 3 payload."""

    source_profile = assembler_input.source_profile
    phase2_selection = assembler_input.phase2_selection
    phase2_ranking = assembler_input.phase2_ranking

    selected_experiences = _assemble_selected_experiences(source_profile, phase2_selection)
    selected_projects = _assemble_selected_projects(source_profile, phase2_selection)
    matched_skills = _assemble_matched_skills(source_profile, phase2_selection)
    selected_certifications = _assemble_selected_certifications(source_profile, phase2_ranking)

    return Phase3GenerationPayload(
        role_context=_assemble_role_context(
            assembler_input.job_analysis,
            assembler_input.generation_preferences,
        ),
        selected_experiences=selected_experiences,
        selected_projects=selected_projects,
        matched_skills=matched_skills,
        selected_certifications=selected_certifications,
        headline_hint=phase2_ranking.headline_suggestion,
        summary_hints=[
            Phase3SummaryHint(
                theme=theme.theme,
                supporting_keywords=theme.supporting_keywords,
            )
            for theme in phase2_ranking.summary_brief_themes
        ],
        length_constraints=_assemble_length_constraints(assembler_input.generation_preferences),
        validation_metadata=_assemble_validation_metadata(
            source_profile=source_profile,
            phase2_selection=phase2_selection,
            selected_experiences=selected_experiences,
            selected_projects=selected_projects,
            matched_skills=matched_skills,
            selected_certifications=selected_certifications,
        ),
    )


def _assemble_role_context(
    job_analysis: Phase3JobAnalysisInput,
    generation_preferences: GenerationPreferences | None,
) -> Phase3RoleContext:
    must_have_skills: list[str] = []
    preferred_skills: list[str] = []
    if job_analysis.prioritized_skills:
        for skill in job_analysis.prioritized_skills:
            if skill.priority == SkillPriority.CORE:
                must_have_skills.append(skill.skill_name)
            else:
                preferred_skills.append(skill.skill_name)
    else:
        must_have_skills.extend(job_analysis.technical_skills)

    return Phase3RoleContext(
        target_role_title=(
            generation_preferences.target_role_title
            if generation_preferences is not None and generation_preferences.target_role_title
            else None
        ),
        target_role_type=(
            job_analysis.role_type.value if job_analysis.role_type is not None else None
        ),
        target_seniority=(
            job_analysis.seniority_level.value
            if job_analysis.seniority_level is not None
            else None
        ),
        target_industry_domain=job_analysis.industry_domain,
        must_have_skills=_stable_unique(must_have_skills),
        preferred_skills=_stable_unique(preferred_skills),
        must_have_requirements=_stable_unique(job_analysis.must_have_requirements),
        preferred_requirements=_stable_unique(job_analysis.nice_to_have_requirements),
        company_terminology=_stable_unique(job_analysis.company_culture_signals),
        action_verbs=_stable_unique(job_analysis.key_action_verbs),
    )


def _assemble_length_constraints(
    generation_preferences: GenerationPreferences | None,
) -> Phase3LengthConstraints | None:
    if generation_preferences is None:
        return None

    return Phase3LengthConstraints(
        target_page_count=generation_preferences.target_page_count,
        headline_max_words=generation_preferences.headline_max_words,
        summary_max_sentences=generation_preferences.summary_max_sentences,
        max_experience_bullets=generation_preferences.max_experience_bullets,
        max_project_bullets=generation_preferences.max_project_bullets,
    )


def _assemble_selected_experiences(
    source_profile: MasterProfile,
    phase2_selection: Phase2SelectionResult,
) -> list[Phase3SelectedExperiencePayload]:
    experience_by_id = {entry.id: entry for entry in source_profile.experience}
    scored_evidence_by_id = {item.id: item for item in phase2_selection.scored_evidence}
    decision_lookup = _experience_decision_lookup(phase2_selection)
    grouped: OrderedDict[str, dict[str, object]] = OrderedDict()

    # Prefer the rebuilt resume-level selection output when present, but keep the
    # projected legacy fields valid for older callers and persisted artifacts.
    for selected in _selected_experience_items(phase2_selection):
        if selected.source_item_id in experience_by_id:
            source_entry = _require_source_experience(experience_by_id, selected.source_item_id)
            evidence_unit_ids = (
                selected.evidence_unit_ids
                or [
                    item.id
                    for item in phase2_selection.scored_evidence
                    if item.source_item_id == selected.source_item_id
                ]
            )
        else:
            scored_item = _require_scored_evidence(scored_evidence_by_id, selected.source_item_id)
            source_entry = _require_source_experience(experience_by_id, scored_item.source_item_id)
            evidence_unit_ids = selected.evidence_unit_ids or [scored_item.id]
        group = grouped.setdefault(
            source_entry.id,
            {
                "entry": source_entry,
                "evidence_unit_ids": [],
                "selected_bullet_ids": [],
                "relevance_score": 0.0,
                "decision": decision_lookup.get(source_entry.id),
            },
        )
        group["evidence_unit_ids"].extend(evidence_unit_ids)
        group["selected_bullet_ids"].extend(selected.selected_bullet_ids)
        group["relevance_score"] = max(group["relevance_score"], selected.relevance_score)

    assembled: list[Phase3SelectedExperiencePayload] = []
    for group in grouped.values():
        entry = group["entry"]
        decision = group["decision"]
        selected_bullet_ids = _resolve_selected_bullet_ids(
            source_bullets=entry.bullets,
            selected_bullet_ids=_stable_unique(group["selected_bullet_ids"]),
            evidence_unit_ids=_stable_unique(group["evidence_unit_ids"]),
        )
        assembled.append(
            Phase3SelectedExperiencePayload(
                id=entry.id,
                evidence_unit_ids=_stable_unique(group["evidence_unit_ids"]),
                organization=entry.organization,
                title=entry.title,
                start_date=entry.start_date,
                end_date=entry.end_date,
                current=entry.current,
                tools=_stable_unique(entry.tools),
                bullets=_assemble_selected_bullets(entry.bullets, selected_bullet_ids),
                relevance_score=round(float(group["relevance_score"]), 4),
                matched_requirements=_matched_requirements(decision),
                selection_reason=_selection_reason(decision),
                supporting_evidence_ids=_supporting_evidence_ids(decision, group["evidence_unit_ids"]),
                score_factors=_score_factors(decision),
            )
        )
    return assembled


def _assemble_selected_projects(
    source_profile: MasterProfile,
    phase2_selection: Phase2SelectionResult,
) -> list[Phase3SelectedProjectPayload]:
    project_by_id = {entry.id: entry for entry in source_profile.projects}
    scored_evidence_by_id = {item.id: item for item in phase2_selection.scored_evidence}
    decision_lookup = _project_decision_lookup(phase2_selection)
    grouped: OrderedDict[str, dict[str, object]] = OrderedDict()

    # Preserve first-seen ranking order while deduplicating repeated evidence units.
    for selected in _selected_project_items(phase2_selection):
        if selected.source_item_id in project_by_id:
            source_entry = _require_source_project(project_by_id, selected.source_item_id)
            evidence_unit_ids = (
                selected.evidence_unit_ids
                or [
                    item.id
                    for item in phase2_selection.scored_evidence
                    if item.source_item_id == selected.source_item_id
                ]
            )
        else:
            scored_item = _require_scored_evidence(scored_evidence_by_id, selected.source_item_id)
            source_entry = _require_source_project(project_by_id, scored_item.source_item_id)
            evidence_unit_ids = selected.evidence_unit_ids or [scored_item.id]
        group = grouped.setdefault(
            source_entry.id,
            {
                "entry": source_entry,
                "evidence_unit_ids": [],
                "selected_bullet_ids": [],
                "relevance_score": 0.0,
                "decision": decision_lookup.get(source_entry.id),
            },
        )
        group["evidence_unit_ids"].extend(evidence_unit_ids)
        group["selected_bullet_ids"].extend(selected.selected_bullet_ids)
        group["relevance_score"] = max(group["relevance_score"], selected.relevance_score)

    assembled: list[Phase3SelectedProjectPayload] = []
    for group in grouped.values():
        entry = group["entry"]
        decision = group["decision"]
        selected_bullet_ids = _resolve_selected_bullet_ids(
            source_bullets=entry.bullets,
            selected_bullet_ids=_stable_unique(group["selected_bullet_ids"]),
            evidence_unit_ids=_stable_unique(group["evidence_unit_ids"]),
        )
        assembled.append(
            Phase3SelectedProjectPayload(
                id=entry.id,
                evidence_unit_ids=_stable_unique(group["evidence_unit_ids"]),
                name=entry.name,
                role=entry.role,
                start_date=entry.start_date,
                end_date=entry.end_date,
                summary=entry.summary,
                tools=_stable_unique(entry.tools),
                bullets=_assemble_selected_bullets(entry.bullets, selected_bullet_ids),
                relevance_score=round(float(group["relevance_score"]), 4),
                matched_requirements=_matched_requirements(decision),
                selection_reason=_selection_reason(decision),
                supporting_evidence_ids=_supporting_evidence_ids(decision, group["evidence_unit_ids"]),
                score_factors=_score_factors(decision),
            )
        )
    return assembled


def _assemble_matched_skills(
    source_profile: MasterProfile,
    phase2_selection: Phase2SelectionResult,
) -> list[Phase3SelectedSkillPayload]:
    skill_by_id = {entry.id: entry for entry in source_profile.skills}
    decision_lookup = _skill_decision_lookup(phase2_selection)
    selected_skill_ids: set[str] = set()
    assembled: list[Phase3SelectedSkillPayload] = []

    for selected in _selected_skill_items(phase2_selection):
        if selected.source_item_id in selected_skill_ids:
            continue
        source_entry = skill_by_id.get(selected.source_item_id)
        if source_entry is None:
            continue
        selected_skill_ids.add(selected.source_item_id)
        decision = decision_lookup.get(source_entry.id)
        assembled.append(
            Phase3SelectedSkillPayload(
                id=source_entry.id,
                skill_name=source_entry.name,
                relevance_score=selected.relevance_score,
                evidence_strength=source_entry.evidence_strength,
                verified_status=source_entry.verified_status,
                matched_requirements=_matched_requirements(decision),
                selection_reason=_selection_reason(decision),
                supporting_evidence_ids=_supporting_evidence_ids(decision),
                score_factors=_score_factors(decision),
            )
        )
    return assembled


def _selected_experience_items(
    phase2_selection: Phase2SelectionResult,
):
    if phase2_selection.selected_experiences:
        return phase2_selection.selected_experiences
    decision = phase2_selection.resume_selection_decision
    if decision is None:
        return []
    return [
        SelectedExperience.model_validate(
            {
                "id": f"legacy.selection.{item.source_item_id}",
                "source_item_id": item.source_item_id,
                "evidence_unit_ids": list(item.evidence_score_ids),
                "relevance_score": item.relevance_score,
                "ranking_explanation": item.ranking_explanation.model_dump(
                    exclude_computed_fields=True
                ),
                "selected_bullet_ids": list(item.selected_bullet_ids),
            }
        )
        for item in decision.selected_experiences
    ]


def _selected_project_items(
    phase2_selection: Phase2SelectionResult,
):
    if phase2_selection.selected_projects:
        return phase2_selection.selected_projects
    decision = phase2_selection.resume_selection_decision
    if decision is None:
        return []
    return [
        SelectedProject.model_validate(
            {
                "id": f"legacy.selection.{item.source_item_id}",
                "source_item_id": item.source_item_id,
                "evidence_unit_ids": list(item.evidence_score_ids),
                "relevance_score": item.relevance_score,
                "ranking_explanation": item.ranking_explanation.model_dump(
                    exclude_computed_fields=True
                ),
                "selected_bullet_ids": list(item.selected_bullet_ids),
            }
        )
        for item in decision.selected_projects
    ]


def _selected_skill_items(
    phase2_selection: Phase2SelectionResult,
):
    if phase2_selection.selected_skills:
        return phase2_selection.selected_skills
    decision = phase2_selection.resume_selection_decision
    if decision is None:
        return []
    return [
        SelectedSkill.model_validate(
            {
                "id": f"legacy.selection.{item.source_item_id}",
                "source_item_id": item.source_item_id,
                "relevance_score": item.relevance_score,
                "skill_name": item.skill_name,
                "ranking_explanation": item.ranking_explanation.model_dump(
                    exclude_computed_fields=True
                ),
            }
        )
        for item in decision.selected_skills
    ]


def _experience_decision_lookup(
    phase2_selection: Phase2SelectionResult,
) -> dict[str, ExperienceAggregateScore]:
    if phase2_selection.resume_selection_decision is None:
        return {}
    return {
        item.source_item_id: item
        for item in phase2_selection.resume_selection_decision.selected_experiences
    }


def _project_decision_lookup(
    phase2_selection: Phase2SelectionResult,
) -> dict[str, ProjectAggregateScore]:
    if phase2_selection.resume_selection_decision is None:
        return {}
    return {
        item.source_item_id: item
        for item in phase2_selection.resume_selection_decision.selected_projects
    }


def _skill_decision_lookup(
    phase2_selection: Phase2SelectionResult,
) -> dict[str, SkillHighlightScore]:
    if phase2_selection.resume_selection_decision is None:
        return {}
    return {
        item.source_item_id: item
        for item in phase2_selection.resume_selection_decision.selected_skills
    }


def _matched_requirements(
    selection_item: ExperienceAggregateScore | ProjectAggregateScore | SkillHighlightScore | None,
) -> list[str]:
    if selection_item is None:
        return []
    return list(selection_item.selection_audit.matched_requirements)


def _selection_reason(
    selection_item: ExperienceAggregateScore | ProjectAggregateScore | SkillHighlightScore | None,
) -> str | None:
    if selection_item is None:
        return None
    return selection_item.selection_audit.selection_reason


def _supporting_evidence_ids(
    selection_item: ExperienceAggregateScore | ProjectAggregateScore | SkillHighlightScore | None,
    fallback_ids: list[str] | None = None,
) -> list[str]:
    if selection_item is None:
        return list(fallback_ids or [])
    return list(selection_item.selection_audit.supporting_evidence_ids or (fallback_ids or []))


def _score_factors(
    selection_item: ExperienceAggregateScore | ProjectAggregateScore | SkillHighlightScore | None,
) -> dict[str, float]:
    if selection_item is None:
        return {}
    return dict(selection_item.selection_audit.score_factors)


def _assemble_selected_certifications(
    source_profile: MasterProfile,
    phase2_ranking: RankingResponse,
) -> list[Phase3SelectedCertificationPayload]:
    certification_by_id = {entry.id: entry for entry in source_profile.certifications}
    grouped: OrderedDict[str, dict[str, object]] = OrderedDict()

    for ranked in phase2_ranking.ranked_certifications:
        if ranked.source_item_id is None:
            continue
        source_entry = certification_by_id.get(ranked.source_item_id)
        if source_entry is None:
            continue
        group = grouped.setdefault(
            source_entry.id,
            {
                "entry": source_entry,
                "evidence_unit_ids": [],
                "relevance_score": 0.0,
            },
        )
        group["evidence_unit_ids"].append(ranked.id)
        group["relevance_score"] = max(group["relevance_score"], ranked.relevance_score)

    assembled: list[Phase3SelectedCertificationPayload] = []
    for group in grouped.values():
        entry = group["entry"]
        assembled.append(
            Phase3SelectedCertificationPayload(
                id=entry.id,
                evidence_unit_ids=_stable_unique(group["evidence_unit_ids"]),
                name=entry.name,
                issuer=entry.issuer,
                issue_date=entry.issue_date,
                expiration_date=entry.expiration_date,
                relevance_score=round(float(group["relevance_score"]), 4),
            )
        )
    return assembled


def _assemble_selected_bullets(
    source_bullets: list[BulletEntry],
    selected_bullet_ids: list[str],
) -> list[Phase3SelectedBulletPayload]:
    bullet_ids = set(selected_bullet_ids)
    bullets: list[Phase3SelectedBulletPayload] = []

    # Keep profile bullet order stable even if upstream selection order shifts.
    for bullet in source_bullets:
        if bullet.id not in bullet_ids:
            continue
        bullets.append(
            Phase3SelectedBulletPayload(
                id=bullet.id,
                text=bullet.text,
                tools=_stable_unique(bullet.tools),
                metric_ids=[metric.id for metric in bullet.metrics],
                evidence_strength=bullet.evidence_strength,
                verified_status=bullet.verified_status,
                rewrite_allowed=bullet.rewrite_allowed,
            )
        )

    if len(bullets) != len(bullet_ids):
        found_ids = {bullet.id for bullet in bullets}
        missing_ids = [bullet_id for bullet_id in selected_bullet_ids if bullet_id not in found_ids]
        raise ValueError(
            "selected bullet ids were not found in source profile: "
            + ", ".join(sorted(set(missing_ids)))
        )

    return bullets


def _resolve_selected_bullet_ids(
    *,
    source_bullets: list[BulletEntry],
    selected_bullet_ids: list[str],
    evidence_unit_ids: list[str],
) -> list[str]:
    if not source_bullets:
        return []

    resolved = list(selected_bullet_ids)
    desired_minimum = min(len(source_bullets), max(1, min(len(evidence_unit_ids), 3)))
    if len(resolved) >= desired_minimum:
        return resolved

    selected_set = set(resolved)
    for bullet in source_bullets:
        if bullet.id in selected_set:
            continue
        resolved.append(bullet.id)
        selected_set.add(bullet.id)
        if len(resolved) >= desired_minimum:
            break
    return resolved


def _assemble_validation_metadata(
    *,
    source_profile: MasterProfile,
    phase2_selection: Phase2SelectionResult,
    selected_experiences: list[Phase3SelectedExperiencePayload],
    selected_projects: list[Phase3SelectedProjectPayload],
    matched_skills: list[Phase3SelectedSkillPayload],
    selected_certifications: list[Phase3SelectedCertificationPayload],
) -> Phase3ValidationMetadata:
    allowed_bullet_ids = [
        bullet.id
        for item in [*selected_experiences, *selected_projects]
        for bullet in item.bullets
    ]
    return Phase3ValidationMetadata(
        profile_id=source_profile.id,
        phase2_status=phase2_selection.diagnostics.status,
        allowed_experience_ids=[item.id for item in selected_experiences],
        allowed_project_ids=[item.id for item in selected_projects],
        allowed_certification_ids=[item.id for item in selected_certifications],
        allowed_skill_ids=[item.id for item in matched_skills],
        allowed_bullet_ids=_stable_unique(allowed_bullet_ids),
    )


def _require_scored_evidence(
    scored_evidence_by_id: dict[str, ScoredEvidenceUnit],
    evidence_unit_id: str,
) -> ScoredEvidenceUnit:
    scored_item = scored_evidence_by_id.get(evidence_unit_id)
    if scored_item is None:
        raise ValueError(f"selected item references unknown scored evidence: {evidence_unit_id}")
    if scored_item.source_item_id is None:
        raise ValueError(f"scored evidence is missing source_item_id: {evidence_unit_id}")
    return scored_item


def _require_source_experience(
    experience_by_id: dict[str, ExperienceEntry],
    experience_id: str,
) -> ExperienceEntry:
    entry = experience_by_id.get(experience_id)
    if entry is None:
        raise ValueError(f"selected experience source item not found in profile: {experience_id}")
    return entry


def _require_source_project(
    project_by_id: dict[str, ProjectEntry],
    project_id: str,
) -> ProjectEntry:
    entry = project_by_id.get(project_id)
    if entry is None:
        raise ValueError(f"selected project source item not found in profile: {project_id}")
    return entry


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped
