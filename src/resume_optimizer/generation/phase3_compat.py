"""Compatibility adapters from bounded Phase 5 artifacts to legacy Phase 3 contracts."""

from __future__ import annotations

from collections import defaultdict
import re

from ..models import ItemType
from ..phase2_models import Phase2Status
from ..phase3_models import (
    GeneratedBullet,
    GeneratedExperience,
    GeneratedProject,
    GeneratedSkillHighlight,
    GeneratedSummary,
    GenerationMetadata,
    GenerationWarning,
    OmittedItem,
    Phase3GenerationResult,
    SourceReference,
    SupportLevel,
    WarningLevel,
)
from ..phase3_output_validation import (
    Phase3FallbackAction,
    Phase3FallbackActionType,
    Phase3ValidationIssue,
    Phase3ValidationIssueCode,
    Phase3ValidationReport,
)
from .contracts import (
    BulletRewriteOutput,
    FullGenerationContext,
    GenerationQualitySignals,
    QualitySignal,
    SectionAssemblyOutput,
    SkillPresentationOutput,
    SummaryGenerationOutput,
)


def build_phase3_compat_result(
    *,
    context: FullGenerationContext,
    summary_output: SummaryGenerationOutput | None,
    bullet_outputs: list[BulletRewriteOutput],
    skill_output: SkillPresentationOutput | None,
    assembly_output: SectionAssemblyOutput,
    generation_quality_signals: GenerationQualitySignals,
    phase2_status: Phase2Status = Phase2Status.SUCCESS,
    preferences_applied: list[str] | None = None,
) -> tuple[Phase3GenerationResult, Phase3ValidationReport]:
    """Build legacy Phase 3-compatible result/report from bounded Phase 5 artifacts."""

    experience_by_id = {item.source_item_id: item for item in context.selected_evidence.experiences}
    project_by_id = {item.source_item_id: item for item in context.selected_evidence.projects}
    bullet_output_by_key = {
        (output.section_id, output.source_item_id, output.source_bullet_id): output
        for output in bullet_outputs
    }

    summary = (
        GeneratedSummary(
            text=summary_output.summary_text,
            source_item_ids=summary_output.source_item_ids,
            source_bullet_ids=summary_output.source_bullet_ids,
            provenance=_summary_provenance(context, summary_output),
            support_level=SupportLevel.SYNTHESIZED,
            confidence_score=_confidence_from_quality(summary_output.quality_signals),
        )
        if summary_output is not None
        else None
    )

    generated_experiences: list[GeneratedExperience] = []
    for section in assembly_output.assembled_experience_sections:
        for item in section.items:
            evidence = experience_by_id[item.source_item_id]
            generated_experiences.append(
                GeneratedExperience(
                    source_item_id=evidence.source_item_id,
                    organization=evidence.organization,
                    title=evidence.title,
                    start_date=evidence.start_date,
                    end_date=evidence.end_date,
                    current=evidence.current,
                    generated_bullets=[
                        _generated_bullet(
                            section_id=section.section_id,
                            source_item_id=item.source_item_id,
                            source_item_type=ItemType.EXPERIENCE,
                            assembled_bullet=bullet,
                            bullet_output=bullet_output_by_key.get((section.section_id, item.source_item_id, bullet.source_bullet_id)),
                            item_score=evidence.relevance_score,
                        )
                        for bullet in item.bullets
                    ],
                    ranking_relevance_score=evidence.relevance_score,
                    support_level=SupportLevel.SYNTHESIZED,
                    confidence_score=_confidence_from_quality(assembly_output.quality_signals, fallback=evidence.relevance_score),
                )
            )

    generated_projects: list[GeneratedProject] = []
    for section in assembly_output.assembled_project_sections:
        for item in section.items:
            evidence = project_by_id[item.source_item_id]
            generated_projects.append(
                GeneratedProject(
                    source_item_id=evidence.source_item_id,
                    name=evidence.name,
                    role=evidence.role,
                    start_date=evidence.start_date,
                    end_date=evidence.end_date,
                    generated_bullets=[
                        _generated_bullet(
                            section_id=section.section_id,
                            source_item_id=item.source_item_id,
                            source_item_type=ItemType.PROJECT,
                            assembled_bullet=bullet,
                            bullet_output=bullet_output_by_key.get((section.section_id, item.source_item_id, bullet.source_bullet_id)),
                            item_score=evidence.relevance_score,
                        )
                        for bullet in item.bullets
                    ],
                    ranking_relevance_score=evidence.relevance_score,
                    support_level=SupportLevel.SYNTHESIZED,
                    confidence_score=_confidence_from_quality(assembly_output.quality_signals, fallback=evidence.relevance_score),
                )
            )

    skill_highlights = _build_skill_highlights(skill_output)
    omitted_items = [
        OmittedItem(
            source_item_id=item.source_item_id,
            source_item_type=item.source_item_type,
            source_bullet_ids=item.source_bullet_ids,
            reason=item.reason,
            detail=item.detail,
        )
        for item in assembly_output.omitted_items_with_reasons
    ]
    warnings = _build_generation_warnings(
        summary_output=summary_output,
        bullet_outputs=bullet_outputs,
        skill_output=skill_output,
        assembly_output=assembly_output,
        generation_quality_signals=generation_quality_signals,
    )
    metadata = GenerationMetadata(
        schema_version="phase5.compat.phase3.v1",
        phase="phase5",
        source_profile_id=context.source_profile_id,
        phase2_status=phase2_status,
        preferences_applied=list(preferences_applied or []),
    )
    result = Phase3GenerationResult(
        headline=None,
        summary=summary,
        selected_experiences=generated_experiences,
        selected_projects=generated_projects,
        skills_to_highlight=skill_highlights,
        omitted_items=omitted_items,
        warnings=warnings,
        metadata=metadata,
    )
    report = _build_validation_report(
        summary_output=summary_output,
        bullet_outputs=bullet_outputs,
        skill_output=skill_output,
        assembly_output=assembly_output,
        generation_quality_signals=generation_quality_signals,
        result=result,
    )
    return result, report


def _generated_bullet(
    *,
    section_id: str,
    source_item_id: str,
    source_item_type: ItemType,
    assembled_bullet,
    bullet_output: BulletRewriteOutput | None,
    item_score: float,
) -> GeneratedBullet:
    output = bullet_output
    return GeneratedBullet(
        id=f"gen.{source_item_id}.{assembled_bullet.source_bullet_id}",
        source_item_id=source_item_id,
        source_item_type=source_item_type,
        source_bullet_ids=[assembled_bullet.source_bullet_id],
        rewritten_text=assembled_bullet.text,
        rewrite_strategy=output.rewrite_strategy if output is not None else "light_rewrite",
        provenance=[
            SourceReference(
                source_item_id=source_item_id,
                source_item_type=source_item_type,
                source_bullet_id=assembled_bullet.source_bullet_id,
                support_level=SupportLevel.DIRECT,
                support_score=item_score,
            )
        ],
        support_level=SupportLevel.SYNTHESIZED if output is not None else SupportLevel.DIRECT,
        confidence_score=_confidence_from_quality(
            output.rewrite_quality_signals if output is not None else None,
            fallback=item_score,
        ),
    )


def _summary_provenance(
    context: FullGenerationContext,
    summary_output: SummaryGenerationOutput,
) -> list[SourceReference]:
    provenance: list[SourceReference] = []
    bullet_item_lookup: dict[str, str] = {}
    for item in [*context.selected_evidence.experiences, *context.selected_evidence.projects]:
        for bullet in item.bullets:
            bullet_item_lookup[bullet.bullet_id] = item.source_item_id

    for bullet_id in summary_output.source_bullet_ids:
        source_item_id = bullet_item_lookup.get(bullet_id)
        if source_item_id is None:
            continue
        provenance.append(
            SourceReference(
                source_item_id=source_item_id,
                source_item_type=_source_item_type(context, source_item_id),
                source_bullet_id=bullet_id,
                support_level=SupportLevel.SYNTHESIZED,
                support_score=0.9,
            )
        )
    covered_item_ids = {reference.source_item_id for reference in provenance}
    for source_item_id in summary_output.source_item_ids:
        if source_item_id in covered_item_ids:
            continue
        provenance.append(
            SourceReference(
                source_item_id=source_item_id,
                source_item_type=_source_item_type(context, source_item_id),
                support_level=SupportLevel.SYNTHESIZED,
                support_score=0.9,
            )
        )
    return provenance


def _source_item_type(context: FullGenerationContext, source_item_id: str) -> ItemType:
    for item in context.selected_evidence.experiences:
        if item.source_item_id == source_item_id:
            return ItemType.EXPERIENCE
    for item in context.selected_evidence.projects:
        if item.source_item_id == source_item_id:
            return ItemType.PROJECT
    for item in context.selected_evidence.skills:
        if item.source_item_id == source_item_id:
            return ItemType.SKILL
    for item in context.selected_evidence.certifications:
        if item.source_item_id == source_item_id:
            return ItemType.CERTIFICATION
    raise ValueError(f"unknown source_item_id for phase3 compatibility mapping: {source_item_id}")


def _build_skill_highlights(skill_output: SkillPresentationOutput | None) -> list[GeneratedSkillHighlight]:
    if skill_output is None:
        return []
    highlights: list[GeneratedSkillHighlight] = []
    seen: set[str] = set()
    source_ids_by_skill: dict[str, list[str]] = defaultdict(list)
    for group in skill_output.grouped_skills:
        for skill_name, source_item_id in zip(group.skill_names, group.source_item_ids, strict=False):
            source_ids_by_skill[skill_name].append(source_item_id)
    for group in skill_output.grouped_skills:
        for skill_name in group.skill_names:
            normalized = skill_name.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            source_item_ids = sorted(set(source_ids_by_skill.get(skill_name, [])))
            highlights.append(
                GeneratedSkillHighlight(
                    skill_name=skill_name,
                    source_item_ids=source_item_ids or group.source_item_ids,
                    provenance=[
                        SourceReference(
                            source_item_id=source_item_id,
                            source_item_type=ItemType.SKILL,
                            support_level=SupportLevel.DIRECT,
                            support_score=0.95,
                        )
                        for source_item_id in (source_item_ids or group.source_item_ids)
                    ],
                    support_level=SupportLevel.DIRECT,
                    confidence_score=_confidence_from_quality(skill_output.quality_signals, fallback=0.95),
                )
            )
    return highlights


def _build_generation_warnings(
    *,
    summary_output: SummaryGenerationOutput | None,
    bullet_outputs: list[BulletRewriteOutput],
    skill_output: SkillPresentationOutput | None,
    assembly_output: SectionAssemblyOutput,
    generation_quality_signals: GenerationQualitySignals,
) -> list[GenerationWarning]:
    warnings: list[GenerationWarning] = []
    message_index = 0
    for message in [
        *(summary_output.warnings if summary_output is not None else []),
        *[warning for output in bullet_outputs for warning in output.warnings],
        *(skill_output.warnings if skill_output is not None else []),
        *assembly_output.assembly_warnings,
    ]:
        message_index += 1
        warnings.append(
            GenerationWarning(
                code=f"phase5.warning.{message_index}",
                level=WarningLevel.WARNING,
                message=message,
            )
        )
    for signal in [*generation_quality_signals.hard_failures, *generation_quality_signals.warnings]:
        warnings.append(_warning_from_quality_signal(signal))
    return warnings


def _warning_from_quality_signal(signal: QualitySignal) -> GenerationWarning:
    level = WarningLevel.ERROR if signal.severity == "error" else WarningLevel.WARNING
    return GenerationWarning(
        code=signal.signal_id,
        level=level,
        message=signal.message,
        source_item_ids=[signal.source_item_id] if signal.source_item_id is not None else [],
        source_bullet_ids=list(signal.source_bullet_ids),
    )


def _build_validation_report(
    *,
    summary_output: SummaryGenerationOutput | None,
    bullet_outputs: list[BulletRewriteOutput],
    skill_output: SkillPresentationOutput | None,
    assembly_output: SectionAssemblyOutput,
    generation_quality_signals: GenerationQualitySignals,
    result: Phase3GenerationResult,
) -> Phase3ValidationReport:
    applied_fallbacks: list[Phase3FallbackAction] = []
    if summary_output is None:
        applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.SUMMARY_FALLBACK,
                message="Summary generation was skipped so the rest of the resume could still be built.",
            )
        )
    if summary_output is not None and any(
        phrase in warning.casefold()
        for warning in summary_output.warnings
        for phrase in {"fallback", "failed deterministic qa", "did not return any valid bounded evidence ids"}
    ):
        applied_fallbacks.append(
            Phase3FallbackAction(
                action_type=Phase3FallbackActionType.SUMMARY_FALLBACK,
                message="Summary was replaced with a bounded fallback during Phase 5 generation.",
            )
        )
    for output in bullet_outputs:
        if any(
            phrase in warning.casefold()
            for warning in output.warnings
            for phrase in {"source text", "normalized source text", "preserved"}
        ):
            applied_fallbacks.append(
                Phase3FallbackAction(
                    action_type=Phase3FallbackActionType.BULLET_SOURCE_FALLBACK,
                    message="Bullet rewrite fell back to source text during Phase 5 generation.",
                    source_item_id=output.source_item_id,
                )
            )
    issues: list[Phase3ValidationIssue] = []
    for signal in generation_quality_signals.hard_failures:
        issues.append(
            Phase3ValidationIssue(
                code=_map_quality_signal_to_issue_code(signal),
                message=signal.message,
                source_item_id=signal.source_item_id,
            )
        )
    for signal in generation_quality_signals.warnings:
        issues.append(
            Phase3ValidationIssue(
                code=_map_quality_signal_to_issue_code(signal),
                message=signal.message,
                source_item_id=signal.source_item_id,
            )
        )
    if skill_output is None and result.skills_to_highlight == []:
        issues.append(
            Phase3ValidationIssue(
                code=Phase3ValidationIssueCode.MISSING_SKILLS,
                message="No skill presentation output was available for selected skills.",
            )
        )
    severe_failure = not bool(result.selected_experiences) and bool(result.selected_projects) is False
    return Phase3ValidationReport(
        applied_fallbacks=applied_fallbacks,
        issues=issues,
        severe_failure=severe_failure,
    )


def _map_quality_signal_to_issue_code(signal: QualitySignal) -> Phase3ValidationIssueCode:
    if signal.section_id and "summary" in signal.section_id:
        return Phase3ValidationIssueCode.INVALID_SUMMARY
    if signal.source_bullet_ids:
        return Phase3ValidationIssueCode.INVALID_BULLET
    if signal.section_id and "skills" in signal.section_id:
        return Phase3ValidationIssueCode.MISSING_SKILLS
    return Phase3ValidationIssueCode.SEVERE_FAILURE


def _confidence_from_quality(signals: GenerationQualitySignals | None, fallback: float = 0.88) -> float:
    if signals is None:
        return round(min(1.0, max(0.0, fallback)), 4)
    if signals.style_alignment_score is not None:
        return signals.style_alignment_score
    return round(min(1.0, max(0.0, fallback)), 4)
