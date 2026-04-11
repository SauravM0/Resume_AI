"""Deterministic regression harness for Phase 5 bounded generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path

from pydantic import Field

from backend.app.tests.fixtures.phase5_eval_cases import (
    DEFAULT_PHASE5_EVAL_TODAY,
    Phase5EvalFixtureCase,
    load_phase5_eval_cases,
)

from .generation import (
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
from .generation.contracts import FullGenerationContext, QualityDimension, QualitySignal
from .generation.role_style_policy import resolve_role_style_policy
from .phase1_role_modeling import FunctionalRoleFamily
from .phase3_assembler import assemble_phase3_generation_payload
from .phase3_models import GenerationPreferences
from .phase3_section_planner import PlanningMode, plan_phase3_sections
from .services.phase2_service import Phase2Service
from .models import NonEmptyStr, StrictModel

DEFAULT_PHASE5_EVAL_FIXTURE_ROOT = Path("backend/app/tests/fixtures/phase5_eval")
DEFAULT_PHASE5_EVAL_BASELINE_PATH = DEFAULT_PHASE5_EVAL_FIXTURE_ROOT / "baseline_snapshot.json"


class Phase5EvalCheckResult(StrictModel):
    name: NonEmptyStr
    passed: bool
    detail: NonEmptyStr


class Phase5EvalCaseResult(StrictModel):
    case_id: NonEmptyStr
    description: NonEmptyStr
    passed: bool
    checks: list[Phase5EvalCheckResult] = Field(default_factory=list)
    quality_issue_dimensions: list[QualityDimension] = Field(default_factory=list)
    actual_snapshot: dict[str, object] = Field(default_factory=dict)
    unmet_expectations: list[NonEmptyStr] = Field(default_factory=list)


class Phase5EvalSummary(StrictModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    case_results: list[Phase5EvalCaseResult] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ResolvedPlan:
    context: FullGenerationContext
    summary_response_text: str
    bullet_response_texts: list[str]


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._outputs[min(len(self.calls) - 1, len(self._outputs) - 1)])


class _FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = _FakeResponses(outputs)


def run_phase5_eval(
    *,
    today: date = DEFAULT_PHASE5_EVAL_TODAY,
    case_ids: list[str] | None = None,
) -> Phase5EvalSummary:
    selected_ids = set(case_ids) if case_ids is not None else None
    results = [
        run_phase5_eval_case(case, today=today)
        for case in load_phase5_eval_cases()
        if selected_ids is None or case.case_id in selected_ids
    ]
    passed_cases = sum(1 for result in results if result.passed)
    return Phase5EvalSummary(
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        case_results=results,
    )


def run_phase5_eval_case(
    case: Phase5EvalFixtureCase,
    *,
    today: date = DEFAULT_PHASE5_EVAL_TODAY,
) -> Phase5EvalCaseResult:
    plan = _resolve_plan(case, today=today)
    summary_service = SummaryGenerationService(
        client=_FakeClient([plan.summary_response_text]),
        model="phase5-eval",
        prompt_template="phase5 eval summary prompt",
    )
    bullet_service = BulletRewriteService(
        client=_FakeClient(plan.bullet_response_texts),
        model="phase5-eval",
        prompt_template="phase5 eval bullet prompt",
    )
    summary_input = build_summary_generation_input(plan.context)
    summary_output = summary_service.generate(summary_input)
    bullet_inputs = build_bullet_rewrite_inputs(plan.context)
    bullet_outputs = [
        bullet_output
        for bullet_input in bullet_inputs
        for bullet_output in bullet_service.rewrite(bullet_input)
    ]
    skill_output = None
    try:
        skill_output = present_skills(build_skill_presentation_input(plan.context))
    except ValueError:
        skill_output = None

    pre_assembly_quality = merge_quality_signals(
        summary_output.quality_signals,
        *[output.rewrite_quality_signals for output in bullet_outputs],
        *([skill_output.quality_signals] if skill_output is not None else []),
    )
    assembly_output = SectionAssemblyService().assemble(
        build_section_assembly_input(
            plan.context,
            summary_output=summary_output,
            bullet_outputs=bullet_outputs,
            skill_presentation_output=skill_output,
            quality_signals=pre_assembly_quality,
        ),
        plan.context,
    )
    final_quality = merge_quality_signals(
        pre_assembly_quality,
        assembly_output.quality_signals,
        validate_generation_quality(
            summary_output=summary_output,
            bullet_outputs_by_section=_group_bullets_by_section(bullet_outputs),
            skill_output=skill_output,
            assembly_output=assembly_output,
        ),
    )
    checks = _evaluate_case(
        case,
        context=plan.context,
        summary_output=summary_output,
        bullet_outputs=bullet_outputs,
        skill_output=skill_output,
        assembly_output=assembly_output,
        final_quality=final_quality,
    )
    unmet = [check.detail for check in checks if not check.passed]
    return Phase5EvalCaseResult(
        case_id=case.case_id,
        description=case.description,
        passed=not unmet,
        checks=checks,
        quality_issue_dimensions=sorted(
            {
                signal.quality_dimension
                for signal in [*final_quality.hard_failures, *final_quality.warnings]
                if signal.quality_dimension is not None
            },
            key=lambda item: item.value,
        ),
        actual_snapshot={
            "parsed_job_output": plan.context.parsed_job_output.model_dump(mode="json", exclude_none=True),
            "selected_evidence": plan.context.selected_evidence.model_dump(mode="json", exclude_none=True),
            "section_plan": [section.model_dump(mode="json", exclude_none=True) for section in plan.context.section_plan],
            "expected_generation_shape": case.expected_generation_shape.model_dump(mode="json", exclude_none=True),
            "expected_quality_rules": case.expected_quality_rules.model_dump(mode="json", exclude_none=True),
            "red_flags": case.red_flags.model_dump(mode="json", exclude_none=True),
            "summary_output": summary_output.model_dump(mode="json", exclude_none=True),
            "bullet_outputs": [output.model_dump(mode="json", exclude_none=True) for output in bullet_outputs],
            "skill_output": skill_output.model_dump(mode="json", exclude_none=True) if skill_output is not None else None,
            "assembly_output": assembly_output.model_dump(mode="json", exclude_none=True),
            "final_quality": final_quality.model_dump(mode="json", exclude_none=True),
        },
        unmet_expectations=unmet,
    )


def render_phase5_eval_summary(summary: Phase5EvalSummary) -> str:
    lines = [
        "Phase 5 Evaluation Summary",
        f"Cases: {summary.total_cases} | Passed: {summary.passed_cases} | Failed: {summary.failed_cases}",
        "",
    ]
    for result in summary.case_results:
        status = "PASS" if result.passed else "FAIL"
        dimensions = ", ".join(dimension.value for dimension in result.quality_issue_dimensions) or "none"
        lines.append(f"[{status}] {result.case_id} | quality dimensions: {dimensions}")
        for check in result.checks:
            prefix = "ok" if check.passed else "x"
            lines.append(f"  - {prefix}: {check.name} | {check.detail}")
        lines.append("")
    return "\n".join(lines).rstrip()


def phase5_eval_summary_json(summary: Phase5EvalSummary) -> str:
    return json.dumps(summary.model_dump(mode="json"), indent=2)


def load_phase5_eval_baseline(path: Path = DEFAULT_PHASE5_EVAL_BASELINE_PATH) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_plan(case: Phase5EvalFixtureCase, *, today: date) -> _ResolvedPlan:
    profile = case.build_profile()
    phase2_result = Phase2Service().run(case.job_analysis, source_profile=profile, today=today)
    preferences = GenerationPreferences(target_page_count=case.target_page_count)
    payload = assemble_phase3_generation_payload(
        case.job_analysis,
        phase2_result.phase2_result,
        profile,
        phase2_result.ranking_response,
        generation_preferences=preferences,
    )
    section_plan = plan_phase3_sections(
        payload,
        mode=PlanningMode.COMPACT if case.target_page_count == 1 else PlanningMode.STANDARD,
    )
    context = build_full_generation_context(
        context_id=f"phase5.eval.{case.case_id}",
        source_profile_id=profile.id,
        job_analysis=case.job_analysis,
        generation_payload=payload,
        section_plan=section_plan,
        functional_role_family=case.role_family,
        organizational_role_mode=case.organizational_role_mode,
    )
    bullet_inputs = build_bullet_rewrite_inputs(context)
    summary_input = build_summary_generation_input(context)
    summary_response_text = json.dumps(
        {
            "summary_text": case.summary_text,
            "evidence_ids_used": (
                [summary_input.experiences[0].evidence_unit_ids[0]]
                if summary_input.experiences
                else (
                    [summary_input.projects[0].evidence_unit_ids[0]]
                    if summary_input.projects
                    else [summary_input.skills[0].evidence_unit_ids[0]]
                )
            ),
            "themes_used": list(summary_input.story_strategy.summary_themes[:2]),
        }
    )
    bullet_response_texts: list[str] = []
    for bullet_input in bullet_inputs:
        for source_bullet in bullet_input.source_bullets[: bullet_input.requested_bullet_count]:
            bullet_response_texts.append(
                json.dumps(
                    {
                        "rewritten_text": case.bullet_text_overrides.get(source_bullet.bullet_id, source_bullet.text),
                        "evidence_ids_used": [bullet_input.evidence_unit_ids[0]],
                        "rewrite_strategy": "light_rewrite",
                    }
                )
            )
    return _ResolvedPlan(
        context=context,
        summary_response_text=summary_response_text,
        bullet_response_texts=bullet_response_texts,
    )


def _evaluate_case(
    case: Phase5EvalFixtureCase,
    *,
    context: FullGenerationContext,
    summary_output,
    bullet_outputs,
    skill_output,
    assembly_output,
    final_quality,
) -> list[Phase5EvalCheckResult]:
    checks: list[Phase5EvalCheckResult] = []
    summary_words = len(summary_output.summary_text.split())
    summary_fallback = any("bounded fallback" in warning.casefold() for warning in summary_output.warnings)
    bullet_fallbacks = sum(
        1
        for output in bullet_outputs
        if any("normalized source text" in warning.casefold() for warning in output.warnings)
    )
    checks.append(
        Phase5EvalCheckResult(
            name="summary_quality",
            passed=(
                (not case.expected_generation_shape.require_summary or assembly_output.assembled_summary is not None)
                and summary_words <= case.expected_quality_rules.max_summary_words
                and (case.expected_quality_rules.allow_summary_fallback or not summary_fallback)
            ),
            detail=(
                f"summary words={summary_words}, fallback={summary_fallback}, "
                f"assembled={assembly_output.assembled_summary is not None}"
            ),
        )
    )
    checks.append(
        Phase5EvalCheckResult(
            name="bullet_faithfulness_indicators",
            passed=case.expected_quality_rules.allow_bullet_fallbacks or bullet_fallbacks == 0,
            detail=f"bullet fallbacks={bullet_fallbacks}, rewritten bullets={len(bullet_outputs)}",
        )
    )
    checks.append(
        Phase5EvalCheckResult(
            name="role_family_style_adherence",
            passed=_style_terms_present(
                case,
                summary_text=summary_output.summary_text,
                bullet_texts=[output.rewritten_text for output in bullet_outputs],
            ),
            detail=(
                "required style terms="
                + ", ".join(case.expected_quality_rules.required_style_terms_any or ["<none>"])
            ),
        )
    )
    checks.append(
        Phase5EvalCheckResult(
            name="section_balance",
            passed=_shape_is_valid(case, assembly_output),
            detail=(
                f"experience_items={sum(len(section.items) for section in assembly_output.assembled_experience_sections)}, "
                f"project_items={sum(len(section.items) for section in assembly_output.assembled_project_sections)}, "
                f"skill_section={assembly_output.assembled_skill_section is not None}"
            ),
        )
    )
    checks.append(
        Phase5EvalCheckResult(
            name="omission_traceability",
            passed=_omission_traceability_is_valid(case, context, assembly_output),
            detail=(
                f"omissions={len(assembly_output.omitted_items_with_reasons)}, "
                f"tracked_budget_ids={len(assembly_output.budget_signals.omitted_item_ids)}"
            ),
        )
    )
    skill_lines = len(skill_output.rendered_skill_lines) if skill_output is not None else 0
    checks.append(
        Phase5EvalCheckResult(
            name="skills_compactness",
            passed=skill_lines <= case.expected_quality_rules.max_skill_lines,
            detail=f"skill lines={skill_lines}",
        )
    )
    checks.append(
        Phase5EvalCheckResult(
            name="generation_quality_issues",
            passed=_quality_is_valid(case, final_quality),
            detail=(
                f"hard_failures={len(final_quality.hard_failures)}, "
                f"warnings={len(final_quality.warnings)}, "
                f"dimensions={','.join(sorted({signal.quality_dimension.value for signal in [*final_quality.hard_failures, *final_quality.warnings] if signal.quality_dimension is not None})) or 'none'}"
            ),
        )
    )
    checks.append(
        Phase5EvalCheckResult(
            name="red_flags",
            passed=_red_flags_absent(case, summary_output.summary_text, bullet_outputs, final_quality),
            detail="red-flag scan completed",
        )
    )
    return checks


def _shape_is_valid(case: Phase5EvalFixtureCase, assembly_output) -> bool:
    experience_items = sum(len(section.items) for section in assembly_output.assembled_experience_sections)
    project_items = sum(len(section.items) for section in assembly_output.assembled_project_sections)
    skill_groups = (
        len(assembly_output.assembled_skill_section.grouped_skills)
        if assembly_output.assembled_skill_section is not None
        else 0
    )
    return (
        (not case.expected_generation_shape.require_summary or assembly_output.assembled_summary is not None)
        and experience_items >= case.expected_generation_shape.min_experience_items
        and project_items >= case.expected_generation_shape.min_project_items
        and skill_groups >= case.expected_generation_shape.min_skill_groups
        and (
            not case.expected_generation_shape.require_skill_section
            or assembly_output.assembled_skill_section is not None
        )
        and (
            not case.expected_generation_shape.require_certification_section
            or assembly_output.assembled_certification_section is not None
        )
        and (
            not case.expected_generation_shape.require_omitted_items
            or bool(assembly_output.omitted_items_with_reasons)
        )
    )


def _omission_traceability_is_valid(case: Phase5EvalFixtureCase, context: FullGenerationContext, assembly_output) -> bool:
    planned_item_ids = {
        item.source_item_id
        for section in context.section_plan
        for item in section.items
        if section.section_type.value in {"experience", "projects", "certifications"}
    }
    assembled_item_ids = {
        item.source_item_id
        for section in assembly_output.assembled_experience_sections
        for item in section.items
    }
    assembled_item_ids.update(
        item.source_item_id
        for section in assembly_output.assembled_project_sections
        for item in section.items
    )
    if assembly_output.assembled_certification_section is not None:
        assembled_item_ids.update(item.source_item_id for item in assembly_output.assembled_certification_section.items)
    omitted_ids = {item.source_item_id for item in assembly_output.omitted_items_with_reasons}
    missing_ids = planned_item_ids - assembled_item_ids
    if case.expected_quality_rules.require_omission_traceability:
        return missing_ids.issubset(omitted_ids)
    return True


def _style_terms_present(
    case: Phase5EvalFixtureCase,
    *,
    summary_text: str,
    bullet_texts: list[str],
) -> bool:
    required_terms = [term.casefold() for term in case.expected_quality_rules.required_style_terms_any]
    if not required_terms:
        return True
    haystack = " ".join([summary_text, *bullet_texts]).casefold()
    if any(term in haystack for term in required_terms):
        return True
    policy = resolve_role_style_policy(
        role_family=case.role_family,
        organizational_role_mode=case.organizational_role_mode,
    )
    return any(term.casefold() in haystack for term in policy.preferred_vocabulary_clusters)


def _quality_is_valid(case: Phase5EvalFixtureCase, final_quality) -> bool:
    if not case.expected_quality_rules.allow_hard_failures and final_quality.hard_failures:
        return False
    actual_warning_dimensions = {
        signal.quality_dimension
        for signal in final_quality.warnings
        if signal.quality_dimension is not None
    }
    return set(case.expected_quality_rules.required_warning_dimensions).issubset(actual_warning_dimensions)


def _red_flags_absent(case: Phase5EvalFixtureCase, summary_text: str, bullet_outputs, final_quality) -> bool:
    text = " ".join([summary_text, *[output.rewritten_text for output in bullet_outputs]]).casefold()
    if any(phrase.casefold() in text for phrase in case.red_flags.banned_phrases):
        return False
    return not any(_signal_mentions_red_flag(signal, case.red_flags.banned_phrases) for signal in [*final_quality.hard_failures, *final_quality.warnings])


def _signal_mentions_red_flag(signal: QualitySignal, banned_phrases: list[str]) -> bool:
    message = signal.message.casefold()
    return any(phrase.casefold() in message for phrase in banned_phrases)


def _group_bullets_by_section(bullet_outputs) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for output in bullet_outputs:
        grouped.setdefault(output.section_id, []).append(output)
    return grouped
