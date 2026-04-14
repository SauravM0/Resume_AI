"""Deterministic Phase 5 section assembly service."""

from __future__ import annotations

from dataclasses import dataclass
import re

from ..models import ItemType
from ..phase3_models import OmissionReason
from .contracts import (
    AssembledBulletLine,
    AssembledCertificationItem,
    AssembledCertificationSection,
    AssembledEducationSection,
    AssembledExperienceItem,
    AssembledExperienceSection,
    AssembledProjectItem,
    AssembledProjectSection,
    AssembledSkillSection,
    AssembledSummary,
    BulletRewriteOutput,
    FullGenerationContext,
    GenerationSectionType,
    OmittedAssemblyItem,
    PlannedSection,
    PlannedSectionItem,
    SectionAssemblyInput,
    SectionAssemblyOutput,
    SelectedBulletEvidence,
    SelectedCertificationEvidence,
    SelectedExperienceEvidence,
    SelectedProjectEvidence,
)
from .quality_validator import merge_quality_signals, validate_section_assembly_quality
from .section_budget import BulletBudgetTracker


@dataclass(slots=True)
class _AssemblyIndexes:
    experience_by_id: dict[str, SelectedExperienceEvidence]
    project_by_id: dict[str, SelectedProjectEvidence]
    certification_by_id: dict[str, SelectedCertificationEvidence]
    bullet_by_item_and_id: dict[tuple[str, str], SelectedBulletEvidence]
    rewrite_by_key: dict[tuple[str, str, str], BulletRewriteOutput]


class SectionAssemblyService:
    """Assemble bounded generation artifacts into stable render-ready sections."""

    def assemble(
        self,
        assembly_input: SectionAssemblyInput,
        context: FullGenerationContext,
    ) -> SectionAssemblyOutput:
        """Assemble final structured sections without changing strategy."""

        self._validate_context_alignment(assembly_input, context)
        indexes = _build_indexes(context, assembly_input)
        budget = BulletBudgetTracker(context.page_constraints)
        omitted_items: list[OmittedAssemblyItem] = []
        warnings: list[str] = []

        assembled_summary = self._assemble_summary(assembly_input, context)
        assembled_experience_sections: list[AssembledExperienceSection] = []
        assembled_project_sections: list[AssembledProjectSection] = []
        assembled_skill_section: AssembledSkillSection | None = None
        assembled_certification_section: AssembledCertificationSection | None = None
        assembled_education_section: AssembledEducationSection | None = None

        for section in context.section_plan:
            if not section.visible:
                continue
            if section.section_type == GenerationSectionType.EXPERIENCE:
                assembled_section, section_warnings, section_omissions = self._assemble_experience_section(
                    section,
                    indexes,
                    context,
                    budget,
                )
                warnings.extend(section_warnings)
                omitted_items.extend(section_omissions)
                if assembled_section is not None:
                    assembled_experience_sections.append(assembled_section)
            elif section.section_type == GenerationSectionType.PROJECTS:
                assembled_section, section_warnings, section_omissions = self._assemble_project_section(
                    section,
                    indexes,
                    context,
                    budget,
                )
                warnings.extend(section_warnings)
                omitted_items.extend(section_omissions)
                if assembled_section is not None:
                    assembled_project_sections.append(assembled_section)
            elif section.section_type == GenerationSectionType.SKILLS:
                assembled_skill_section, section_warnings = self._assemble_skill_section(section, assembly_input)
                warnings.extend(section_warnings)
            elif section.section_type == GenerationSectionType.CERTIFICATIONS:
                assembled_certification_section, section_omissions = self._assemble_certification_section(
                    section,
                    indexes,
                )
                omitted_items.extend(section_omissions)

        planner_omissions = self._collect_unplanned_selected_item_omissions(context)
        omitted_items.extend(planner_omissions)

        if assembled_summary is None and any(
            section.section_type == GenerationSectionType.SUMMARY and section.visible
            for section in context.section_plan
        ):
            warnings.append("summary section was planned but no bounded summary output was available")

        result = SectionAssemblyOutput(
            context_id=assembly_input.context_id,
            source_profile_id=assembly_input.source_profile_id,
            assembled_summary=assembled_summary,
            assembled_experience_sections=assembled_experience_sections,
            assembled_project_sections=assembled_project_sections,
            assembled_skill_section=assembled_skill_section,
            assembled_education_section=assembled_education_section,
            assembled_certification_section=assembled_certification_section,
            omitted_items_with_reasons=sorted(
                omitted_items,
                key=lambda item: ((item.section_id or ""), item.source_item_type.value, item.source_item_id),
            ),
            assembly_warnings=_stable_unique(warnings),
            budget_signals=budget.to_signals(),
        )
        return result.model_copy(
            update={
                "quality_signals": merge_quality_signals(
                    assembly_input.quality_signals,
                    validate_section_assembly_quality(result),
                )
            }
        )

    def _validate_context_alignment(
        self,
        assembly_input: SectionAssemblyInput,
        context: FullGenerationContext,
    ) -> None:
        if assembly_input.context_id != context.context_id:
            raise ValueError("section assembly input context_id must match full generation context")
        if assembly_input.source_profile_id != context.source_profile_id:
            raise ValueError("section assembly input source_profile_id must match full generation context")
        input_section_ids = [section.section_id for section in assembly_input.section_plan]
        context_section_ids = [section.section_id for section in context.section_plan]
        if input_section_ids != context_section_ids:
            raise ValueError("section assembly input must use the same section plan ordering as full generation context")

    def _assemble_summary(
        self,
        assembly_input: SectionAssemblyInput,
        context: FullGenerationContext,
    ) -> AssembledSummary | None:
        if assembly_input.summary_output is None:
            return None
        section = next(
            section for section in context.section_plan if section.section_id == assembly_input.summary_output.section_id
        )
        return AssembledSummary(
            section_id=section.section_id,
            title=section.title,
            text=assembly_input.summary_output.summary_text,
        )

    def _assemble_experience_section(
        self,
        section: PlannedSection,
        indexes: _AssemblyIndexes,
        context: FullGenerationContext,
        budget: BulletBudgetTracker,
    ) -> tuple[AssembledExperienceSection | None, list[str], list[OmittedAssemblyItem]]:
        items: list[AssembledExperienceItem] = []
        warnings: list[str] = []
        omissions: list[OmittedAssemblyItem] = []
        per_item_limit = context.page_constraints.max_experience_bullets_per_item

        for planned_item in section.items:
            evidence = indexes.experience_by_id[planned_item.source_item_id]
            bullet_lines, item_warnings, item_omissions = self._assemble_bullets_for_item(
                section=section,
                planned_item=planned_item,
                source_item_type=ItemType.EXPERIENCE,
                per_item_limit=per_item_limit,
                budget=budget,
                indexes=indexes,
            )
            warnings.extend(item_warnings)
            omissions.extend(item_omissions)
            if not bullet_lines:
                budget.note_omission(evidence.source_item_id)
                omissions.append(
                    OmittedAssemblyItem(
                        source_item_id=evidence.source_item_id,
                        source_item_type=ItemType.EXPERIENCE,
                        reason=OmissionReason.SPACE_CONSTRAINT,
                        detail="all planned bullets were omitted by deterministic page budget limits",
                        source_bullet_ids=list(planned_item.selected_bullet_ids),
                        section_id=section.section_id,
                    )
                )
                continue
            items.append(
                AssembledExperienceItem(
                    source_item_id=evidence.source_item_id,
                    title=evidence.title,
                    organization=evidence.organization,
                    bullets=bullet_lines,
                )
            )

        if not items:
            return None, warnings, omissions
        return AssembledExperienceSection(section_id=section.section_id, title=section.title, items=items), warnings, omissions

    def _assemble_project_section(
        self,
        section: PlannedSection,
        indexes: _AssemblyIndexes,
        context: FullGenerationContext,
        budget: BulletBudgetTracker,
    ) -> tuple[AssembledProjectSection | None, list[str], list[OmittedAssemblyItem]]:
        items: list[AssembledProjectItem] = []
        warnings: list[str] = []
        omissions: list[OmittedAssemblyItem] = []
        per_item_limit = context.page_constraints.max_project_bullets_per_item

        for planned_item in section.items:
            evidence = indexes.project_by_id[planned_item.source_item_id]
            bullet_lines, item_warnings, item_omissions = self._assemble_bullets_for_item(
                section=section,
                planned_item=planned_item,
                source_item_type=ItemType.PROJECT,
                per_item_limit=per_item_limit,
                budget=budget,
                indexes=indexes,
            )
            warnings.extend(item_warnings)
            omissions.extend(item_omissions)
            if not bullet_lines:
                budget.note_omission(evidence.source_item_id)
                omissions.append(
                    OmittedAssemblyItem(
                        source_item_id=evidence.source_item_id,
                        source_item_type=ItemType.PROJECT,
                        reason=OmissionReason.SPACE_CONSTRAINT,
                        detail="all planned bullets were omitted by deterministic page budget limits",
                        source_bullet_ids=list(planned_item.selected_bullet_ids),
                        section_id=section.section_id,
                    )
                )
                continue
            items.append(
                AssembledProjectItem(
                    source_item_id=evidence.source_item_id,
                    name=evidence.name,
                    role=evidence.role,
                    bullets=bullet_lines,
                )
            )

        if not items:
            return None, warnings, omissions
        return AssembledProjectSection(section_id=section.section_id, title=section.title, items=items), warnings, omissions

    def _assemble_skill_section(
        self,
        section: PlannedSection,
        assembly_input: SectionAssemblyInput,
    ) -> tuple[AssembledSkillSection | None, list[str]]:
        if assembly_input.skill_presentation_output is None:
            return None, ["skills section was planned but no bounded skill presentation output was available"]
        return (
            AssembledSkillSection(
                section_id=section.section_id,
                title=section.title,
                grouped_skills=assembly_input.skill_presentation_output.grouped_skills,
                rendered_skill_lines=assembly_input.skill_presentation_output.rendered_skill_lines,
            ),
            [],
        )

    def _assemble_certification_section(
        self,
        section: PlannedSection,
        indexes: _AssemblyIndexes,
    ) -> tuple[AssembledCertificationSection | None, list[OmittedAssemblyItem]]:
        items: list[AssembledCertificationItem] = []
        omissions: list[OmittedAssemblyItem] = []
        for planned_item in section.items:
            certification = indexes.certification_by_id.get(planned_item.source_item_id)
            if certification is None:
                omissions.append(
                    OmittedAssemblyItem(
                        source_item_id=planned_item.source_item_id,
                        source_item_type=ItemType.CERTIFICATION,
                        reason=OmissionReason.LOW_SUPPORT,
                        detail="planned certification could not be resolved from bounded context",
                        section_id=section.section_id,
                    )
                )
                continue
            details = None
            if certification.issue_date is not None:
                details = f"Issued {certification.issue_date.raw_value}"
            items.append(
                AssembledCertificationItem(
                    source_item_id=certification.source_item_id,
                    name=certification.name,
                    issuer=certification.issuer,
                    details=details,
                )
            )
        if not items:
            return None, omissions
        return AssembledCertificationSection(section_id=section.section_id, title=section.title, items=items), omissions

    def _assemble_bullets_for_item(
        self,
        *,
        section: PlannedSection,
        planned_item: PlannedSectionItem,
        source_item_type: ItemType,
        per_item_limit: int,
        budget: BulletBudgetTracker,
        indexes: _AssemblyIndexes,
    ) -> tuple[list[AssembledBulletLine], list[str], list[OmittedAssemblyItem]]:
        warnings: list[str] = []
        omissions: list[OmittedAssemblyItem] = []
        bullet_ids = list(planned_item.selected_bullet_ids[:per_item_limit])

        if len(planned_item.selected_bullet_ids) > per_item_limit:
            omitted_ids = planned_item.selected_bullet_ids[per_item_limit:]
            omissions.append(
                OmittedAssemblyItem(
                    source_item_id=planned_item.source_item_id,
                    source_item_type=source_item_type,
                    reason=OmissionReason.SPACE_CONSTRAINT,
                    detail="planner-selected bullets were truncated to the configured per-item cap",
                    source_bullet_ids=list(omitted_ids),
                    section_id=section.section_id,
                )
            )

        lines: list[AssembledBulletLine] = []
        for bullet_id in bullet_ids:
            if not budget.can_take(1):
                budget.note_omission(planned_item.source_item_id)
                omissions.append(
                    OmittedAssemblyItem(
                        source_item_id=planned_item.source_item_id,
                        source_item_type=source_item_type,
                        reason=OmissionReason.SPACE_CONSTRAINT,
                        detail="planned bullet omitted because the total page bullet budget was exhausted",
                        source_bullet_ids=[bullet_id],
                        section_id=section.section_id,
                    )
                )
                continue

            source_bullet = indexes.bullet_by_item_and_id.get((planned_item.source_item_id, bullet_id))
            if source_bullet is None:
                warnings.append(
                    f"planned bullet {bullet_id} for {planned_item.source_item_id} was missing from bounded evidence"
                )
                omissions.append(
                    OmittedAssemblyItem(
                        source_item_id=planned_item.source_item_id,
                        source_item_type=source_item_type,
                        reason=OmissionReason.LOW_SUPPORT,
                        detail="planned bullet could not be resolved from bounded evidence",
                        source_bullet_ids=[bullet_id],
                        section_id=section.section_id,
                    )
                )
                continue

            rewrite = indexes.rewrite_by_key.get((section.section_id, planned_item.source_item_id, bullet_id))
            if rewrite is None:
                warnings.append(
                    f"missing rewritten bullet for {bullet_id}; source text was used during assembly"
                )
                text = _normalize_text(source_bullet.text)
                evidence_ids = list(source_bullet.evidence_unit_ids)
            else:
                text = rewrite.rewritten_text
                evidence_ids = list(rewrite.evidence_ids_used)

            lines.append(
                AssembledBulletLine(
                    source_bullet_id=bullet_id,
                    text=text,
                    evidence_ids_used=evidence_ids,
                )
            )
            budget.consume(1)

        return lines, warnings, omissions

    def _collect_unplanned_selected_item_omissions(
        self,
        context: FullGenerationContext,
    ) -> list[OmittedAssemblyItem]:
        planned_ids = {
            item.source_item_id
            for section in context.section_plan
            for item in section.items
        }
        omissions: list[OmittedAssemblyItem] = []
        for evidence in [
            *context.selected_evidence.experiences,
            *context.selected_evidence.projects,
            *context.selected_evidence.skills,
            *context.selected_evidence.certifications,
        ]:
            if evidence.source_item_id in planned_ids:
                continue
            omissions.append(
                OmittedAssemblyItem(
                    source_item_id=evidence.source_item_id,
                    source_item_type=evidence.item_type,
                    reason=OmissionReason.SPACE_CONSTRAINT,
                    detail="selected evidence was omitted upstream by the section plan and remained omitted during assembly",
                )
            )
        return omissions


def _build_indexes(
    context: FullGenerationContext,
    assembly_input: SectionAssemblyInput,
) -> _AssemblyIndexes:
    return _AssemblyIndexes(
        experience_by_id={item.source_item_id: item for item in context.selected_evidence.experiences},
        project_by_id={item.source_item_id: item for item in context.selected_evidence.projects},
        certification_by_id={item.source_item_id: item for item in context.selected_evidence.certifications},
        bullet_by_item_and_id={
            (item.source_item_id, bullet.bullet_id): bullet
            for item in [*context.selected_evidence.experiences, *context.selected_evidence.projects]
            for bullet in item.bullets
        },
        rewrite_by_key={
            (output.section_id, output.source_item_id, output.source_bullet_id): output
            for output in assembly_input.bullet_outputs
        },
    )


def _normalize_text(text: str) -> str:
    stripped = re.sub(r"\s+", " ", text.strip())
    return stripped.rstrip(".") + "."


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
