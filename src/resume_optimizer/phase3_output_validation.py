"""Validation and conservative fallback logic for Phase 3 outputs.

This layer sits between raw LLM JSON and later verification/rendering phases.
It repairs only narrow, source-grounded failures and reports every fallback so
later observability can see what happened.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, ValidationError

from .models import ItemType, NonEmptyStr, StrictModel
from .phase3_headline_summary import assess_headline, assess_summary
from .phase3_models import (
    GeneratedBullet,
    GeneratedExperience,
    GeneratedHeadline,
    GeneratedProject,
    GeneratedSkillHighlight,
    GeneratedSummary,
    GenerationMetadata,
    GenerationWarning,
    OmittedItem,
    Phase3GenerationPayload,
    Phase3GenerationResult,
    SectionEmphasis,
    SourceReference,
    SupportLevel,
    WarningLevel,
)
from .phase3_rewrite_policy import evaluate_bullet_rewrite


class Phase3ValidationIssueCode(StrEnum):
    """Stable validation issue taxonomy for Phase 3 output handling."""

    INVALID_HEADLINE = "invalid_headline"
    INVALID_SUMMARY = "invalid_summary"
    INVALID_EXPERIENCE_ITEM = "invalid_experience_item"
    INVALID_PROJECT_ITEM = "invalid_project_item"
    INVALID_BULLET = "invalid_bullet"
    INVALID_OMISSIONS = "invalid_omissions"
    INVALID_WARNINGS = "invalid_warnings"
    INVALID_SECTION_EMPHASIS = "invalid_section_emphasis"
    EMPTY_CRITICAL_SECTION = "empty_critical_section"
    MISSING_SKILLS = "missing_skills"
    EXCESSIVE_BULLET_COUNT = "excessive_bullet_count"
    SEVERE_FAILURE = "severe_failure"


class Phase3FallbackActionType(StrEnum):
    """Structured fallback actions applied to a Phase 3 artifact."""

    HEADLINE_FALLBACK = "headline_fallback"
    SUMMARY_FALLBACK = "summary_fallback"
    BULLET_SOURCE_FALLBACK = "bullet_source_fallback"
    EXPERIENCE_SOURCE_FALLBACK = "experience_source_fallback"
    PROJECT_SOURCE_FALLBACK = "project_source_fallback"
    SKILL_FALLBACK = "skill_fallback"
    DROP_OPTIONAL_SECTION = "drop_optional_section"
    METADATA_REBUILT = "metadata_rebuilt"


class Phase3ValidationIssue(StrictModel):
    """One validation or fallback issue discovered while finalizing Phase 3 output."""

    code: Phase3ValidationIssueCode
    message: NonEmptyStr
    source_item_id: NonEmptyStr | None = None


class Phase3FallbackAction(StrictModel):
    """One deterministic fallback applied to the generated result."""

    action_type: Phase3FallbackActionType
    message: NonEmptyStr
    source_item_id: NonEmptyStr | None = None


class Phase3ValidationReport(StrictModel):
    """Structured record of Phase 3 validation and fallback behavior."""

    applied_fallbacks: list[Phase3FallbackAction] = Field(default_factory=list)
    issues: list[Phase3ValidationIssue] = Field(default_factory=list)
    severe_failure: bool = False


class Phase3ValidatedOutput(StrictModel):
    """Finalized Phase 3 output plus the validation/fallback report."""

    result: Phase3GenerationResult
    report: Phase3ValidationReport


def validate_and_finalize_phase3_output(
    raw_payload: dict[str, Any],
    generation_payload: Phase3GenerationPayload,
) -> Phase3ValidatedOutput:
    """Validate raw Phase 3 JSON and apply conservative source-grounded fallbacks."""

    report = Phase3ValidationReport()
    headline = _finalize_headline(
        raw_payload.get("headline"), generation_payload, report
    )
    summary = _finalize_summary(raw_payload.get("summary"), generation_payload, report)
    section_emphasis = _finalize_section_emphasis(
        raw_payload.get("section_emphasis"),
        report,
    )
    selected_experiences = _finalize_experiences(
        raw_payload.get("selected_experiences"),
        generation_payload,
        report,
    )
    selected_projects = _finalize_projects(
        raw_payload.get("selected_projects"),
        generation_payload,
        report,
    )
    skills_to_highlight = _finalize_skills(
        raw_payload.get("skills_to_highlight"),
        generation_payload,
        report,
    )
    omitted_items = _finalize_omissions(raw_payload.get("omitted_items"), report)
    warnings = _finalize_warnings(raw_payload.get("warnings"), report)
    metadata = _rebuild_metadata(
        raw_payload.get("metadata"), generation_payload, report
    )

    if generation_payload.selected_experiences and not selected_experiences:
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.EMPTY_CRITICAL_SECTION,
                message="Experience section was empty despite supported evidence.",
            )
        )
        report.severe_failure = True

    if generation_payload.matched_skills and not skills_to_highlight:
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.MISSING_SKILLS,
                message="skills_to_highlight was empty despite supported matched skills.",
            )
        )

    finalized_result = Phase3GenerationResult(
        headline=headline,
        summary=summary,
        section_emphasis=section_emphasis,
        selected_experiences=selected_experiences,
        selected_projects=selected_projects,
        skills_to_highlight=skills_to_highlight,
        omitted_items=omitted_items,
        warnings=warnings,
        metadata=metadata,
    )
    return Phase3ValidatedOutput(result=finalized_result, report=report)


def _finalize_headline(
    raw_headline: Any,
    payload: Phase3GenerationPayload,
    report: Phase3ValidationReport,
) -> GeneratedHeadline | None:
    headline: GeneratedHeadline | None = None
    if raw_headline is not None:
        try:
            headline = GeneratedHeadline.model_validate(raw_headline)
        except ValidationError:
            report.issues.append(
                Phase3ValidationIssue(
                    code=Phase3ValidationIssueCode.INVALID_HEADLINE,
                    message="Headline failed validation and was replaced with a safe fallback.",
                )
            )
    if headline is not None:
        assessment = assess_headline(payload, headline.text)
        if not assessment.hard_fail:
            return headline
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_HEADLINE,
                message="Headline appeared inflated or unsupported and was replaced.",
            )
        )
    fallback = _build_safe_headline(payload)
    report.applied_fallbacks.append(
        Phase3FallbackAction(
            action_type=Phase3FallbackActionType.HEADLINE_FALLBACK,
            message="Headline was replaced with a conservative role-aligned fallback.",
        )
    )
    return fallback


def _finalize_summary(
    raw_summary: Any,
    payload: Phase3GenerationPayload,
    report: Phase3ValidationReport,
) -> GeneratedSummary | None:
    summary: GeneratedSummary | None = None
    if raw_summary is not None:
        try:
            summary = GeneratedSummary.model_validate(raw_summary)
        except ValidationError:
            report.issues.append(
                Phase3ValidationIssue(
                    code=Phase3ValidationIssueCode.INVALID_SUMMARY,
                    message="Summary failed validation and was replaced with a source-grounded fallback when possible.",
                )
            )
    if summary is not None:
        assessment = assess_summary(payload, summary.text)
        if not assessment.hard_fail:
            return summary
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_SUMMARY,
                message="Summary contained unsupported or overly inflated claims and was replaced.",
            )
        )
    fallback = _build_safe_summary(payload)
    if fallback is not None:
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.SUMMARY_FALLBACK,
                message="Summary was replaced with a simpler source-grounded fallback.",
            )
        )
    return fallback


def _finalize_experiences(
    raw_experiences: Any,
    payload: Phase3GenerationPayload,
    report: Phase3ValidationReport,
) -> list[GeneratedExperience]:
    raw_items = raw_experiences if isinstance(raw_experiences, list) else []
    raw_by_source_id = {
        item.get("source_item_id"): item for item in raw_items if isinstance(item, dict)
    }
    finalized: list[GeneratedExperience] = []
    max_bullets = (
        payload.length_constraints.max_experience_bullets
        if payload.length_constraints is not None
        else None
    )
    for source_item in payload.selected_experiences:
        raw_item = raw_by_source_id.get(source_item.id)
        finalized.append(
            _finalize_experience_item(
                raw_item, source_item, report, max_bullets=max_bullets
            )
        )
    return finalized


def _finalize_projects(
    raw_projects: Any,
    payload: Phase3GenerationPayload,
    report: Phase3ValidationReport,
) -> list[GeneratedProject]:
    raw_items = raw_projects if isinstance(raw_projects, list) else []
    raw_by_source_id = {
        item.get("source_item_id"): item for item in raw_items if isinstance(item, dict)
    }
    finalized: list[GeneratedProject] = []
    max_bullets = (
        payload.length_constraints.max_project_bullets
        if payload.length_constraints is not None
        else None
    )
    for source_item in payload.selected_projects:
        finalized.append(
            _finalize_project_item(
                raw_by_source_id.get(source_item.id),
                source_item,
                report,
                max_bullets=max_bullets,
            )
        )
    return finalized


def _finalize_skills(
    raw_skills: Any,
    payload: Phase3GenerationPayload,
    report: Phase3ValidationReport,
) -> list[GeneratedSkillHighlight]:
    raw_items = raw_skills if isinstance(raw_skills, list) else []
    valid_items: list[GeneratedSkillHighlight] = []
    for item in raw_items:
        try:
            valid_item = GeneratedSkillHighlight.model_validate(item)
        except ValidationError:
            continue
        if valid_item.source_item_ids and all(
            source_item_id in payload.validation_metadata.allowed_skill_ids
            for source_item_id in valid_item.source_item_ids
        ):
            valid_items.append(valid_item)

    if valid_items:
        return valid_items[: len(payload.matched_skills)]

    if not payload.matched_skills:
        return []

    report.applied_fallbacks.append(
        Phase3FallbackAction(
            action_type=Phase3FallbackActionType.SKILL_FALLBACK,
            message="skills_to_highlight was rebuilt from supported matched skills.",
        )
    )
    return [
        GeneratedSkillHighlight(
            skill_name=skill.skill_name,
            source_item_ids=[skill.id],
            provenance=[
                SourceReference(
                    source_item_id=skill.id,
                    source_item_type=ItemType.SKILL,
                    support_level=SupportLevel.DIRECT,
                )
            ],
            support_level=SupportLevel.DIRECT,
            confidence_score=skill.relevance_score,
        )
        for skill in payload.matched_skills
    ]


def _finalize_omissions(
    raw_omissions: Any,
    report: Phase3ValidationReport,
) -> list[OmittedItem]:
    if raw_omissions is None:
        return []
    if not isinstance(raw_omissions, list):
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_OMISSIONS,
                message="omitted_items had invalid structure and was dropped.",
            )
        )
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.DROP_OPTIONAL_SECTION,
                message="Dropped invalid omitted_items section.",
            )
        )
        return []
    valid: list[OmittedItem] = []
    for item in raw_omissions:
        try:
            valid.append(OmittedItem.model_validate(item))
        except ValidationError:
            report.issues.append(
                Phase3ValidationIssue(
                    code=Phase3ValidationIssueCode.INVALID_OMISSIONS,
                    message="One or more omitted_items entries were invalid and removed.",
                )
            )
            report.applied_fallbacks.append(
                Phase3FallbackAction(
                    action_type=Phase3FallbackActionType.DROP_OPTIONAL_SECTION,
                    message="Dropped invalid omitted_items entries.",
                )
            )
            return []
    return valid


def _finalize_warnings(
    raw_warnings: Any,
    report: Phase3ValidationReport,
) -> list[GenerationWarning]:
    if raw_warnings is None:
        return []
    if not isinstance(raw_warnings, list):
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_WARNINGS,
                message="warnings had invalid structure and was dropped.",
            )
        )
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.DROP_OPTIONAL_SECTION,
                message="Dropped invalid warnings section.",
            )
        )
        return []
    valid: list[GenerationWarning] = []
    for item in raw_warnings:
        try:
            valid.append(GenerationWarning.model_validate(item))
        except ValidationError:
            report.issues.append(
                Phase3ValidationIssue(
                    code=Phase3ValidationIssueCode.INVALID_WARNINGS,
                    message="One or more warnings entries were invalid and removed.",
                )
            )
            report.applied_fallbacks.append(
                Phase3FallbackAction(
                    action_type=Phase3FallbackActionType.DROP_OPTIONAL_SECTION,
                    message="Dropped invalid warnings entries.",
                )
            )
            return []
    return valid


def _finalize_section_emphasis(
    raw_items: Any,
    report: Phase3ValidationReport,
) -> list[SectionEmphasis]:
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_SECTION_EMPHASIS,
                message="section_emphasis had invalid structure and was dropped.",
            )
        )
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.DROP_OPTIONAL_SECTION,
                message="Dropped invalid section_emphasis section.",
            )
        )
        return []
    valid: list[SectionEmphasis] = []
    for item in raw_items:
        try:
            valid.append(SectionEmphasis.model_validate(item))
        except ValidationError:
            report.issues.append(
                Phase3ValidationIssue(
                    code=Phase3ValidationIssueCode.INVALID_SECTION_EMPHASIS,
                    message="One or more section_emphasis entries were invalid and removed.",
                )
            )
            report.applied_fallbacks.append(
                Phase3FallbackAction(
                    action_type=Phase3FallbackActionType.DROP_OPTIONAL_SECTION,
                    message="Dropped invalid section_emphasis entries.",
                )
            )
            return []
    return valid


def _rebuild_metadata(
    raw_metadata: Any,
    payload: Phase3GenerationPayload,
    report: Phase3ValidationReport,
) -> GenerationMetadata:
    try:
        metadata = GenerationMetadata.model_validate(raw_metadata or {})
    except ValidationError:
        metadata = GenerationMetadata(
            source_profile_id=payload.validation_metadata.profile_id,
            phase2_status=payload.validation_metadata.phase2_status,
        )
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.METADATA_REBUILT,
                message="Metadata was rebuilt from payload validation metadata.",
            )
        )
        return metadata

    if metadata.source_profile_id != payload.validation_metadata.profile_id:
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.METADATA_REBUILT,
                message="Metadata profile identifier was normalized from payload validation metadata.",
            )
        )
        return GenerationMetadata(
            source_profile_id=payload.validation_metadata.profile_id,
            phase2_status=payload.validation_metadata.phase2_status,
            preferences_applied=metadata.preferences_applied,
        )
    return metadata.model_copy(
        update={"phase2_status": payload.validation_metadata.phase2_status}
    )


def _finalize_experience_item(
    raw_item: Any,
    source_item,
    report: Phase3ValidationReport,
    *,
    max_bullets: int | None,
) -> GeneratedExperience:
    if not isinstance(raw_item, dict):
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_EXPERIENCE_ITEM,
                message="Experience item was missing or invalid and was rebuilt from source content.",
                source_item_id=source_item.id,
            )
        )
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.EXPERIENCE_SOURCE_FALLBACK,
                message="Experience item was rebuilt conservatively from source bullets.",
                source_item_id=source_item.id,
            )
        )
        return _build_source_experience(source_item)

    raw_bullets = raw_item.get("generated_bullets")
    generated_bullets = _finalize_generated_bullets(
        raw_bullets,
        source_item=source_item,
        source_item_type=ItemType.EXPERIENCE,
        report=report,
    )
    if len(generated_bullets) > len(source_item.bullets):
        generated_bullets = generated_bullets[: len(source_item.bullets)]
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.EXCESSIVE_BULLET_COUNT,
                message="Experience bullet count exceeded supported bounds and was trimmed.",
                source_item_id=source_item.id,
            )
        )
    if max_bullets is not None and len(generated_bullets) > max_bullets:
        generated_bullets = generated_bullets[:max_bullets]
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.EXCESSIVE_BULLET_COUNT,
                message="Experience bullet count exceeded generation length guidance and was trimmed.",
                source_item_id=source_item.id,
            )
        )
    return GeneratedExperience(
        source_item_id=source_item.id,
        organization=source_item.organization,
        title=source_item.title,
        start_date=source_item.start_date,
        end_date=source_item.end_date,
        current=source_item.current,
        generated_bullets=generated_bullets
        or _fallback_source_bullets(source_item, ItemType.EXPERIENCE, report),
        ranking_relevance_score=source_item.relevance_score,
        support_level=SupportLevel.DIRECT,
        confidence_score=source_item.relevance_score,
    )


def _finalize_project_item(
    raw_item: Any,
    source_item,
    report: Phase3ValidationReport,
    *,
    max_bullets: int | None,
) -> GeneratedProject:
    if not isinstance(raw_item, dict):
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_PROJECT_ITEM,
                message="Project item was missing or invalid and was rebuilt from source content.",
                source_item_id=source_item.id,
            )
        )
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.PROJECT_SOURCE_FALLBACK,
                message="Project item was rebuilt conservatively from source bullets.",
                source_item_id=source_item.id,
            )
        )
        return _build_source_project(source_item)

    generated_bullets = _finalize_generated_bullets(
        raw_item.get("generated_bullets"),
        source_item=source_item,
        source_item_type=ItemType.PROJECT,
        report=report,
    )
    if len(generated_bullets) > len(source_item.bullets):
        generated_bullets = generated_bullets[: len(source_item.bullets)]
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.EXCESSIVE_BULLET_COUNT,
                message="Project bullet count exceeded supported bounds and was trimmed.",
                source_item_id=source_item.id,
            )
        )
    if max_bullets is not None and len(generated_bullets) > max_bullets:
        generated_bullets = generated_bullets[:max_bullets]
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.EXCESSIVE_BULLET_COUNT,
                message="Project bullet count exceeded generation length guidance and was trimmed.",
                source_item_id=source_item.id,
            )
        )
    return GeneratedProject(
        source_item_id=source_item.id,
        name=source_item.name,
        role=source_item.role,
        start_date=source_item.start_date,
        end_date=source_item.end_date,
        generated_bullets=generated_bullets
        or _fallback_source_bullets(source_item, ItemType.PROJECT, report),
        ranking_relevance_score=source_item.relevance_score,
        support_level=SupportLevel.DIRECT,
        confidence_score=source_item.relevance_score,
    )


def _finalize_generated_bullets(
    raw_bullets: Any,
    *,
    source_item,
    source_item_type: ItemType,
    report: Phase3ValidationReport,
) -> list[GeneratedBullet]:
    if not isinstance(raw_bullets, list):
        return _fallback_source_bullets(source_item, source_item_type, report)

    source_bullets_by_id = {bullet.id: bullet for bullet in source_item.bullets}
    finalized: list[GeneratedBullet] = []
    for raw_bullet in raw_bullets:
        try:
            generated_bullet = GeneratedBullet.model_validate(raw_bullet)
        except ValidationError:
            finalized.extend(
                _fallback_source_bullets(source_item, source_item_type, report)
            )
            return _dedupe_bullets(finalized)

        if generated_bullet.source_item_id != source_item.id:
            finalized.extend(
                _fallback_source_bullets(source_item, source_item_type, report)
            )
            return _dedupe_bullets(finalized)

        if any(
            bullet_id not in source_bullets_by_id
            for bullet_id in generated_bullet.source_bullet_ids
        ):
            finalized.extend(
                _fallback_source_bullets(source_item, source_item_type, report)
            )
            return _dedupe_bullets(finalized)

        source_bullets = [
            source_bullets_by_id[bullet_id]
            for bullet_id in generated_bullet.source_bullet_ids
        ]
        assessment = evaluate_bullet_rewrite(
            source_bullets, generated_bullet.rewritten_text
        )
        if assessment.hard_fail:
            finalized.extend(
                _fallback_source_bullets_for_ids(
                    source_item,
                    source_item_type,
                    generated_bullet.source_bullet_ids,
                    report,
                )
            )
            continue
        finalized.append(generated_bullet)
    return _dedupe_bullets(finalized)


def _fallback_source_bullets(
    source_item, source_item_type: ItemType, report: Phase3ValidationReport
) -> list[GeneratedBullet]:
    return _fallback_source_bullets_for_ids(
        source_item,
        source_item_type,
        [bullet.id for bullet in source_item.bullets],
        report,
    )


def _fallback_source_bullets_for_ids(
    source_item,
    source_item_type: ItemType,
    bullet_ids: list[str],
    report: Phase3ValidationReport,
) -> list[GeneratedBullet]:
    source_bullets_by_id = {bullet.id: bullet for bullet in source_item.bullets}
    fallbacks: list[GeneratedBullet] = []
    for bullet_id in bullet_ids:
        source_bullet = source_bullets_by_id.get(bullet_id)
        if source_bullet is None:
            continue
        report.issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.INVALID_BULLET,
                message="A generated bullet was invalid and fell back to source text.",
                source_item_id=source_item.id,
            )
        )
        report.applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.BULLET_SOURCE_FALLBACK,
                message="Replaced invalid rewritten bullet with source bullet text.",
                source_item_id=source_item.id,
            )
        )
        fallbacks.append(
            GeneratedBullet(
                id=f"fallback.{source_item.id}.{source_bullet.id}",
                source_item_id=source_item.id,
                source_item_type=source_item_type,
                source_bullet_ids=[source_bullet.id],
                rewritten_text=source_bullet.text,
                rewrite_strategy="light_rewrite",
                provenance=[
                    SourceReference(
                        source_item_id=source_item.id,
                        source_item_type=source_item_type,
                        source_bullet_id=source_bullet.id,
                        support_level=SupportLevel.DIRECT,
                    )
                ],
                support_level=SupportLevel.DIRECT,
                confidence_score=1.0,
            )
        )
    return fallbacks


def _build_safe_headline(payload: Phase3GenerationPayload) -> GeneratedHeadline | None:
    headline_text = (
        payload.role_context.target_role_title
        or payload.headline_hint
        or next((item.title for item in payload.selected_experiences), None)
    )
    if headline_text is None:
        return None
    refs = _headline_summary_refs(payload)
    if refs is None:
        return None
    return GeneratedHeadline(
        text=headline_text,
        source_item_ids=refs["source_item_ids"],
        source_bullet_ids=[],
        provenance=refs["provenance"],
        support_level=SupportLevel.DIRECT,
        confidence_score=0.8,
    )


def _build_safe_summary(payload: Phase3GenerationPayload) -> GeneratedSummary | None:
    primary_experience = (
        payload.selected_experiences[0] if payload.selected_experiences else None
    )
    primary_project = (
        payload.selected_projects[0] if payload.selected_projects else None
    )

    role_context = payload.role_context
    target_title = role_context.target_role_title or "Engineer"
    must_haves = (
        role_context.must_have_skills[:3] if role_context.must_have_skills else []
    )
    preferred = (
        role_context.preferred_skills[:2] if role_context.preferred_skills else []
    )
    all_skills = must_haves + preferred

    if primary_experience is None and primary_project is None and not all_skills:
        return None

    clauses: list[str] = []

    if primary_experience is not None:
        org = primary_experience.organization
        title = primary_experience.title
        clauses.append(f"{title} at {org}")

    if all_skills:
        skills_str = ", ".join(all_skills[:3])
        if primary_experience:
            clauses.append(f"skilled in {skills_str}")
        else:
            clauses.append(f"engineer with {skills_str} experience")

    if primary_project is not None:
        clauses.append(f"delivered {primary_project.name}")

    text = " ".join(clauses).strip().rstrip(",")

    if len(text) > 120:
        if primary_experience:
            skills_part = (
                f" skilled in {', '.join(all_skills[:2])}" if all_skills else ""
            )
            text = f"{primary_experience.title}{skills_part}"
        elif all_skills:
            text = f"{target_title} with {', '.join(all_skills[:2])} experience"

    text = text.capitalize().rstrip(".") + "."

    refs = _headline_summary_refs(payload)
    if refs is None:
        return None
    return GeneratedSummary(
        text=text,
        source_item_ids=refs["source_item_ids"],
        source_bullet_ids=refs["source_bullet_ids"],
        provenance=refs["provenance"],
        support_level=SupportLevel.DIRECT,
        confidence_score=0.75,
    )


def _headline_summary_refs(payload: Phase3GenerationPayload) -> dict[str, Any] | None:
    source_item_ids: list[str] = []
    source_bullet_ids: list[str] = []
    provenance: list[SourceReference] = []
    for experience in payload.selected_experiences[:1]:
        source_item_ids.append(experience.id)
        for bullet in experience.bullets[:1]:
            source_bullet_ids.append(bullet.id)
            provenance.append(
                SourceReference(
                    source_item_id=experience.id,
                    source_item_type=ItemType.EXPERIENCE,
                    source_bullet_id=bullet.id,
                    support_level=SupportLevel.DIRECT,
                )
            )
    for skill in payload.matched_skills[:1]:
        if skill.id not in source_item_ids:
            source_item_ids.append(skill.id)
            provenance.append(
                SourceReference(
                    source_item_id=skill.id,
                    source_item_type=ItemType.SKILL,
                    support_level=SupportLevel.DIRECT,
                )
            )
    if not provenance and payload.selected_projects:
        project = payload.selected_projects[0]
        source_item_ids.append(project.id)
        if project.bullets:
            source_bullet_ids.append(project.bullets[0].id)
            provenance.append(
                SourceReference(
                    source_item_id=project.id,
                    source_item_type=ItemType.PROJECT,
                    source_bullet_id=project.bullets[0].id,
                    support_level=SupportLevel.DIRECT,
                )
            )
        else:
            provenance.append(
                SourceReference(
                    source_item_id=project.id,
                    source_item_type=ItemType.PROJECT,
                    support_level=SupportLevel.DIRECT,
                )
            )
    if not provenance and payload.selected_certifications:
        certification = payload.selected_certifications[0]
        source_item_ids.append(certification.id)
        provenance.append(
            SourceReference(
                source_item_id=certification.id,
                source_item_type=ItemType.CERTIFICATION,
                support_level=SupportLevel.DIRECT,
            )
        )
    if not provenance:
        return None
    return {
        "source_item_ids": source_item_ids,
        "source_bullet_ids": source_bullet_ids,
        "provenance": provenance,
    }


def _build_source_experience(source_item) -> GeneratedExperience:
    return GeneratedExperience(
        source_item_id=source_item.id,
        organization=source_item.organization,
        title=source_item.title,
        start_date=source_item.start_date,
        end_date=source_item.end_date,
        current=source_item.current,
        generated_bullets=[
            GeneratedBullet(
                id=f"fallback.{source_item.id}.{bullet.id}",
                source_item_id=source_item.id,
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_ids=[bullet.id],
                rewritten_text=bullet.text,
                rewrite_strategy="light_rewrite",
                provenance=[
                    SourceReference(
                        source_item_id=source_item.id,
                        source_item_type=ItemType.EXPERIENCE,
                        source_bullet_id=bullet.id,
                        support_level=SupportLevel.DIRECT,
                    )
                ],
                support_level=SupportLevel.DIRECT,
                confidence_score=1.0,
            )
            for bullet in source_item.bullets
        ],
        ranking_relevance_score=source_item.relevance_score,
        support_level=SupportLevel.DIRECT,
        confidence_score=source_item.relevance_score,
    )


def _build_source_project(source_item) -> GeneratedProject:
    return GeneratedProject(
        source_item_id=source_item.id,
        name=source_item.name,
        role=source_item.role,
        start_date=source_item.start_date,
        end_date=source_item.end_date,
        generated_bullets=[
            GeneratedBullet(
                id=f"fallback.{source_item.id}.{bullet.id}",
                source_item_id=source_item.id,
                source_item_type=ItemType.PROJECT,
                source_bullet_ids=[bullet.id],
                rewritten_text=bullet.text,
                rewrite_strategy="light_rewrite",
                provenance=[
                    SourceReference(
                        source_item_id=source_item.id,
                        source_item_type=ItemType.PROJECT,
                        source_bullet_id=bullet.id,
                        support_level=SupportLevel.DIRECT,
                    )
                ],
                support_level=SupportLevel.DIRECT,
                confidence_score=1.0,
            )
            for bullet in source_item.bullets
        ],
        ranking_relevance_score=source_item.relevance_score,
        support_level=SupportLevel.DIRECT,
        confidence_score=source_item.relevance_score,
    )


def _dedupe_bullets(bullets: list[GeneratedBullet]) -> list[GeneratedBullet]:
    seen: set[str] = set()
    deduped: list[GeneratedBullet] = []
    for bullet in bullets:
        if bullet.id in seen:
            continue
        seen.add(bullet.id)
        deduped.append(bullet)
    return deduped
