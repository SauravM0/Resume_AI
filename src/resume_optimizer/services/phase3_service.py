"""Phase 3 orchestration service using the bounded Phase 5 generation path."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

from backend.app.metrics.storage import record_stage_metric
from ..config import DEFAULT_SETTINGS, Settings
from ..generation import (
    BulletRewriteService,
    SectionAssemblyService,
    SummaryGenerationService,
    build_bullet_rewrite_inputs,
    build_full_generation_context,
    build_section_assembly_input,
    build_skill_presentation_input,
    build_summary_generation_input,
    merge_quality_signals,
    present_skills,
    validate_generation_quality,
)
from ..generation.contracts import (
    GenerationQualitySignals,
    QualitySignal,
    QualitySignalSeverity,
)
from ..generation.phase3_compat import build_phase3_compat_result
from ..phase1_models import Phase1JobAnalysis
from ..phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from ..phase3_assembler import assemble_phase3_generation_payload
from ..phase3_models import (
    GenerationPreferences,
    Phase3GenerationPayload,
    Phase3GenerationRequest,
    Phase3GenerationResult,
    Phase3GenerationResultRecord,
    Phase3JobAnalysisInput,
    Phase3RankingInput,
    Phase3SelectionInput,
    Phase3SourceProfileInput,
)
from ..phase3_output_validation import Phase3ValidationReport
from ..phase3_section_planner import Phase3SectionPlan, PlanningMode, plan_phase3_sections

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Phase3ServiceResult:
    """Backend-facing Phase 3 artifact bundle for later phases to consume."""

    request: Phase3GenerationRequest
    generation_payload: Phase3GenerationPayload
    section_plan: Phase3SectionPlan
    phase3_result: Phase3GenerationResult
    validation_report: Phase3ValidationReport
    result_record: Phase3GenerationResultRecord
    bounded_generation_context: dict[str, object] = field(default_factory=dict)
    bounded_generation_artifacts: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Phase3Service:
    """Orchestrate Phase 3 assembly, planning, generation, and safe logging."""

    settings: Settings = field(default_factory=lambda: DEFAULT_SETTINGS)
    summary_service: SummaryGenerationService = field(default_factory=SummaryGenerationService)
    bullet_rewrite_service: BulletRewriteService = field(default_factory=BulletRewriteService)
    section_assembly_service: SectionAssemblyService = field(default_factory=SectionAssemblyService)

    def run(
        self,
        job_analysis: Phase3JobAnalysisInput,
        *,
        phase1_final_analysis: Phase1JobAnalysis | None = None,
        phase2_selection: Phase3SelectionInput,
        phase2_ranking: Phase3RankingInput,
        source_profile: Phase3SourceProfileInput,
        generation_preferences: GenerationPreferences | None = None,
    ) -> Phase3ServiceResult:
        """Run the full Phase 3 backend pipeline from upstream artifacts."""

        request = Phase3GenerationRequest(
            job_analysis=job_analysis,
            phase2_selection=phase2_selection,
            source_profile=source_profile,
            generation_preferences=generation_preferences,
        )
        if self.settings.phase3_safe_logging_enabled:
            self._log_run_start(request)

        # The assembler is where the richer resume-selection decision becomes the
        # compact Phase 3 generator contract. Downstream phases still receive the
        # same top-level payload shape, but with broader and more explainable items.
        generation_payload = assemble_phase3_generation_payload(
            job_analysis,
            phase2_selection,
            source_profile,
            phase2_ranking,
            generation_preferences=generation_preferences,
        )
        section_planning_started_at = datetime.now(timezone.utc)
        try:
            section_plan = plan_phase3_sections(
                generation_payload,
                mode=_resolve_planning_mode(generation_preferences),
            )
        except Exception:
            record_stage_metric(
                stage_name="section_planning",
                started_at=section_planning_started_at,
                ended_at=datetime.now(timezone.utc),
                success=False,
                failure_type="section_planning_error",
                output_metadata={"mode": _resolve_planning_mode(generation_preferences).value},
            )
            raise
        record_stage_metric(
            stage_name="section_planning",
            started_at=section_planning_started_at,
            ended_at=datetime.now(timezone.utc),
            success=True,
            output_metadata={
                "mode": section_plan.mode.value,
                "planned_experience_count": len(section_plan.experiences),
                "planned_project_count": len(section_plan.projects),
                "planned_skill_count": len(section_plan.skills),
                "planned_omission_count": len(section_plan.omitted_items),
            },
        )
        full_generation_context = build_full_generation_context(
            context_id=f"genctx.{source_profile.id}",
            source_profile_id=source_profile.id,
            job_analysis=job_analysis,
            generation_payload=generation_payload,
            section_plan=section_plan,
            functional_role_family=_resolve_functional_role_family(phase1_final_analysis),
            organizational_role_mode=_resolve_organizational_role_mode(phase1_final_analysis),
            story_focus_mode=_resolve_story_focus_mode(section_plan),
        )
        summary_input = build_summary_generation_input(full_generation_context)
        summary_output = None
        summary_quality_signals = GenerationQualitySignals()
        try:
            summary_output = self.summary_service.generate(summary_input)
        except Exception as exc:
            logger.warning(
                "phase3 summary generation degraded to omission",
                extra={
                    "profile_id": source_profile.id,
                    "context_id": full_generation_context.context_id,
                    "error": str(exc),
                },
            )
            summary_quality_signals = GenerationQualitySignals(
                warnings=[
                    QualitySignal(
                        signal_id=f"quality.phase5.summary_omitted.{full_generation_context.context_id}",
                        severity=QualitySignalSeverity.WARNING,
                        message="Summary generation failed; proceeding without a summary section.",
                        section_id=summary_input.section_id,
                        suggested_fallback_action="omit_summary_and_continue",
                    )
                ]
            )
        bullet_inputs = build_bullet_rewrite_inputs(full_generation_context)
        bullet_outputs = [
            bullet_output
            for bullet_input in bullet_inputs
            for bullet_output in self.bullet_rewrite_service.rewrite(bullet_input)
        ]
        skill_output = None
        if any(section.section_type.value == "skills" and section.visible for section in full_generation_context.section_plan):
            try:
                skill_output = present_skills(build_skill_presentation_input(full_generation_context))
            except ValueError:
                skill_output = None
        pre_assembly_quality = merge_quality_signals(
            summary_output.quality_signals if summary_output is not None else summary_quality_signals,
            *[output.rewrite_quality_signals for output in bullet_outputs],
            *( [skill_output.quality_signals] if skill_output is not None else [] ),
        )
        assembly_input = build_section_assembly_input(
            full_generation_context,
            summary_output=summary_output,
            bullet_outputs=bullet_outputs,
            skill_presentation_output=skill_output,
            quality_signals=pre_assembly_quality,
        )
        assembly_output = self.section_assembly_service.assemble(assembly_input, full_generation_context)
        generation_quality_signals = merge_quality_signals(
            pre_assembly_quality,
            assembly_output.quality_signals,
            validate_generation_quality(
                summary_output=summary_output,
                bullet_outputs_by_section=_group_bullets_by_section(bullet_outputs),
                skill_output=skill_output,
                assembly_output=assembly_output,
            ),
        )
        phase3_result, validation_report = build_phase3_compat_result(
            context=full_generation_context,
            summary_output=summary_output,
            bullet_outputs=bullet_outputs,
            skill_output=skill_output,
            assembly_output=assembly_output,
            generation_quality_signals=generation_quality_signals,
            phase2_status=phase2_selection.diagnostics.status,
            preferences_applied=_preferences_applied(generation_preferences),
        )
        result_record = Phase3GenerationResultRecord(
            profile_id=source_profile.id,
            request=request,
            result=phase3_result,
        )

        # TODO(phase6): feed section-plan and validation-report artifacts into the
        # verification stage without coupling verification rules into generation.
        if self.settings.phase3_safe_logging_enabled:
            self._log_run_summary(
                request=request,
                section_plan=section_plan,
                result=phase3_result,
                validation_report=validation_report,
                summary_output=summary_output,
                bullet_outputs=bullet_outputs,
                skill_output=skill_output,
                assembly_output=assembly_output,
                generation_quality_signals=generation_quality_signals,
            )

        # TODO(phase5): hand this service result directly to the rendering layer
        # once the structured rendering contract is finalized.
        return Phase3ServiceResult(
            request=request,
            generation_payload=generation_payload,
            section_plan=section_plan,
            phase3_result=phase3_result,
            validation_report=validation_report,
            result_record=result_record,
            bounded_generation_context=full_generation_context.model_dump(mode="json", exclude_none=True),
            bounded_generation_artifacts={
                "summary_output": (
                    summary_output.model_dump(mode="json", exclude_none=True)
                    if summary_output is not None
                    else None
                ),
                "bullet_outputs": [output.model_dump(mode="json", exclude_none=True) for output in bullet_outputs],
                "skill_presentation_output": (
                    skill_output.model_dump(mode="json", exclude_none=True)
                    if skill_output is not None
                    else None
                ),
                "section_assembly_output": assembly_output.model_dump(mode="json", exclude_none=True),
                "generation_quality_signals": generation_quality_signals.model_dump(mode="json", exclude_none=True),
            },
        )

    def _log_run_start(self, request: Phase3GenerationRequest) -> None:
        """Emit safe structured logs for Phase 3 start without leaking resume content."""

        logger.info(
            "phase3 run started",
            extra={
                "profile_id": request.source_profile.id,
                "selected_experience_count": len(request.phase2_selection.selected_experiences),
                "selected_project_count": len(request.phase2_selection.selected_projects),
                "selected_skill_count": len(request.phase2_selection.selected_skills),
                "phase2_status": request.phase2_selection.diagnostics.status.value,
                "target_page_count": (
                    request.generation_preferences.target_page_count
                    if request.generation_preferences is not None
                    else None
                ),
            },
        )

    def _log_run_summary(
        self,
        *,
        request: Phase3GenerationRequest,
        section_plan: Phase3SectionPlan,
        result: Phase3GenerationResult,
        validation_report: Phase3ValidationReport,
        summary_output,
        bullet_outputs,
        skill_output,
        assembly_output,
        generation_quality_signals,
    ) -> None:
        """Emit safe structured logs for Phase 3 completion and fallback status."""

        logger.info(
            "phase3 run completed",
            extra={
                "profile_id": request.source_profile.id,
                "phase2_status": request.phase2_selection.diagnostics.status.value,
                "planning_mode": section_plan.mode.value,
                "project_emphasis": section_plan.project_emphasis.value,
                "planned_experience_count": len(section_plan.experiences),
                "planned_project_count": len(section_plan.projects),
                "planned_skill_count": len(section_plan.skills),
                "planned_omission_count": len(section_plan.omitted_items),
                "validation_status": (
                    "severe_failure" if validation_report.severe_failure else "ok"
                ),
                "fallback_applied": bool(validation_report.applied_fallbacks),
                "fallback_count": len(validation_report.applied_fallbacks),
                "validation_issue_count": len(validation_report.issues),
                "summary_generated": summary_output is not None,
                "bullet_rewrite_count": len(bullet_outputs),
                "skills_rendered": skill_output is not None,
                "assembled_experience_count": sum(len(section.items) for section in assembly_output.assembled_experience_sections),
                "assembled_project_count": sum(len(section.items) for section in assembly_output.assembled_project_sections),
                "assembly_warning_count": len(assembly_output.assembly_warnings),
                "quality_issue_count": len(generation_quality_signals.hard_failures) + len(generation_quality_signals.warnings),
                "quality_passed": generation_quality_signals.passed,
                "selected_experience_count": result.metadata.selected_experience_count,
                "selected_project_count": result.metadata.selected_project_count,
                "highlighted_skill_count": result.metadata.highlighted_skill_count,
                "warning_count": result.metadata.warning_count,
                "omitted_item_count": result.metadata.omitted_item_count,
            },
        )


def _resolve_planning_mode(
    generation_preferences: GenerationPreferences | None,
) -> PlanningMode:
    """Map explicit length guidance onto a deterministic section-planning mode."""

    if generation_preferences is None:
        return PlanningMode.STANDARD
    if generation_preferences.target_page_count == 1:
        return PlanningMode.COMPACT
    return PlanningMode.STANDARD


DEFAULT_PHASE3_SERVICE = Phase3Service()


def _resolve_functional_role_family(
    phase1_final_analysis: Phase1JobAnalysis | None,
) -> FunctionalRoleFamily:
    if phase1_final_analysis is None:
        return FunctionalRoleFamily.OTHER
    return phase1_final_analysis.functional_role_family


def _resolve_organizational_role_mode(
    phase1_final_analysis: Phase1JobAnalysis | None,
) -> OrganizationalRoleMode:
    if phase1_final_analysis is None:
        return OrganizationalRoleMode.UNKNOWN
    return phase1_final_analysis.organizational_role_mode


def _resolve_story_focus_mode(section_plan: Phase3SectionPlan):
    from ..generation.contracts import StoryFocusMode

    if section_plan.projects and not section_plan.experiences:
        return StoryFocusMode.PROJECT_FORWARD
    if section_plan.skills and not section_plan.experiences and not section_plan.projects:
        return StoryFocusMode.SKILLS_FORWARD
    if section_plan.experiences:
        return StoryFocusMode.EXPERIENCE_FORWARD
    return StoryFocusMode.BALANCED


def _group_bullets_by_section(bullet_outputs):
    grouped: dict[str, list] = {}
    for output in bullet_outputs:
        grouped.setdefault(output.section_id, []).append(output)
    return grouped


def _preferences_applied(generation_preferences: GenerationPreferences | None) -> list[str]:
    if generation_preferences is None:
        return []
    applied: list[str] = []
    for field_name, value in generation_preferences.model_dump(exclude_none=True).items():
        if isinstance(value, bool):
            if value:
                applied.append(field_name)
        else:
            applied.append(field_name)
    return applied
