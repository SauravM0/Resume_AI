"""Internal run-confidence scoring and gating for Phase 6 orchestration."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from backend.app.models.render_models import RenderOutputStatus
from backend.app.orchestration.enums import StageName
from backend.app.orchestration.pipeline_models import (
    CompilePdfOutput,
    GenerateStructuredContentOutput,
    ParseJobDescriptionOutput,
    RankSelectEvidenceOutput,
    RenderDeterministicLatexOutput,
    VerifyGeneratedContentOutput,
)
from backend.app.services.verification.types import (
    SemanticVerificationStatus,
    VerificationDecisionOutcome,
)
from resume_optimizer.models import StrictModel
from resume_optimizer.phase2_models import Phase2Status


class InternalConfidenceLevel(StrEnum):
    """Internal trust classification for one pipeline run."""

    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    DEGRADED = "degraded"
    UNSAFE = "unsafe"


class ConfidenceDimensionScore(StrictModel):
    """One confidence dimension with score and safe reasoning."""

    score: float
    level: InternalConfidenceLevel
    reasons: list[str] = []


class RunConfidenceAssessment(StrictModel):
    """Internal confidence assessment for one pipeline run."""

    final_confidence_level: InternalConfidenceLevel
    gating_reasons: list[str] = []
    jd_parse_confidence: ConfidenceDimensionScore
    evidence_selection_confidence: ConfidenceDimensionScore
    generation_confidence: ConfidenceDimensionScore
    verification_confidence: ConfidenceDimensionScore
    fallback_impact: ConfidenceDimensionScore
    render_confidence: ConfidenceDimensionScore
    retry_count: int = 0
    fallback_count: int = 0


def assess_run_confidence(
    *,
    parsed: ParseJobDescriptionOutput | None = None,
    ranked: RankSelectEvidenceOutput | None = None,
    generated: GenerateStructuredContentOutput | None = None,
    verified: VerifyGeneratedContentOutput | None = None,
    rendered: RenderDeterministicLatexOutput | None = None,
    compiled: CompilePdfOutput | None = None,
    retry_attempts: list[dict[str, Any]] | None = None,
    fallback_audits: list[dict[str, Any]] | None = None,
    terminal_failure_stage: str | None = None,
) -> RunConfidenceAssessment:
    """Score one run using conservative internal confidence rules."""

    retries = list(retry_attempts or [])
    fallbacks = list(fallback_audits or [])
    jd_parse = _jd_parse_confidence(parsed, fallbacks)
    evidence = _evidence_selection_confidence(ranked)
    generation = _generation_confidence(generated)
    verification = _verification_confidence(verified)
    fallback_impact = _fallback_impact_confidence(fallbacks)
    render = _render_confidence(rendered, compiled)

    gating_reasons: list[str] = []
    retry_count = len(retries)
    fallback_count = len(fallbacks)

    if terminal_failure_stage in {
        StageName.VERIFY_GENERATED_CONTENT.value,
        StageName.RENDER_DETERMINISTIC_LATEX.value,
        StageName.COMPILE_PDF.value,
    }:
        gating_reasons.append(f"terminal_failure:{terminal_failure_stage}")
    if verified is not None:
        report = verified.verification_report
        if report.decision_outcome == VerificationDecisionOutcome.FAIL_CLOSED:
            gating_reasons.append("verification_fail_closed")
        if not report.renderable:
            gating_reasons.append("verification_not_renderable")
    if compiled is not None and not compiled.compile_result.compile_success:
        gating_reasons.append("render_or_compile_failed")
    if rendered is not None and rendered.render_output is not None:
        if rendered.render_output.status == RenderOutputStatus.FAILED:
            gating_reasons.append("render_failed")
        elif rendered.render_output.status == RenderOutputStatus.PARTIAL:
            gating_reasons.append("render_partial")
    if fallback_count >= 3:
        gating_reasons.append("excessive_fallback_usage")
    if retry_count >= 2:
        gating_reasons.append("repeated_retries")
    if jd_parse.score < 0.55 and evidence.score < 0.6:
        gating_reasons.append("weak_parse_and_selection")

    weighted_score = (
        (jd_parse.score * 0.18)
        + (evidence.score * 0.2)
        + (generation.score * 0.2)
        + (verification.score * 0.22)
        + (fallback_impact.score * 0.1)
        + (render.score * 0.1)
    )

    if any(
        reason in gating_reasons
        for reason in {
            "verification_fail_closed",
            "verification_not_renderable",
            "render_or_compile_failed",
            "render_failed",
        }
    ):
        final_level = InternalConfidenceLevel.UNSAFE
    elif any(
        reason in gating_reasons
        for reason in {
            "excessive_fallback_usage",
            "repeated_retries",
            "weak_parse_and_selection",
            "render_partial",
        }
    ) or weighted_score < 0.72:
        final_level = InternalConfidenceLevel.DEGRADED
    elif weighted_score < 0.88:
        final_level = InternalConfidenceLevel.ACCEPTABLE
    else:
        final_level = InternalConfidenceLevel.STRONG

    return RunConfidenceAssessment(
        final_confidence_level=final_level,
        gating_reasons=gating_reasons,
        jd_parse_confidence=jd_parse,
        evidence_selection_confidence=evidence,
        generation_confidence=generation,
        verification_confidence=verification,
        fallback_impact=fallback_impact,
        render_confidence=render,
        retry_count=retry_count,
        fallback_count=fallback_count,
    )


def _jd_parse_confidence(
    parsed: ParseJobDescriptionOutput | None,
    fallbacks: list[dict[str, Any]],
) -> ConfidenceDimensionScore:
    if parsed is None or parsed.final_analysis is None:
        return _dimension(0.5, "parse confidence unavailable")
    score = float(parsed.final_analysis.parser_confidence)
    reasons: list[str] = []
    if any(item.get("fallback_class") == "use_deterministic_parse_signals" for item in fallbacks):
        score = min(score, 0.55)
        reasons.append("deterministic_parse_fallback_applied")
    return _dimension(score, *reasons)


def _evidence_selection_confidence(
    ranked: RankSelectEvidenceOutput | None,
) -> ConfidenceDimensionScore:
    if ranked is None:
        return _dimension(0.5, "selection confidence unavailable")
    diagnostics = ranked.selection_result.diagnostics
    total_selected = (
        diagnostics.selected_experience_count
        + diagnostics.selected_project_count
        + diagnostics.selected_skill_count
    )
    reasons: list[str] = []
    score = {
        Phase2Status.SUCCESS: 0.9,
        Phase2Status.PARTIAL: 0.68,
        Phase2Status.FAILED: 0.2,
    }[diagnostics.status]
    if diagnostics.candidate_evidence_count < 3:
        score -= 0.2
        reasons.append("low_candidate_evidence")
    if diagnostics.weak_coverage_areas:
        score -= min(0.24, 0.08 * len(diagnostics.weak_coverage_areas))
        reasons.append("weak_coverage_areas_present")
    if total_selected < 2:
        score -= 0.15
        reasons.append("thin_selection_output")
    if diagnostics.warnings:
        score -= min(0.12, 0.04 * len(diagnostics.warnings))
        reasons.append("selection_warnings_present")
    return _dimension(score, *reasons)


def _generation_confidence(
    generated: GenerateStructuredContentOutput | None,
) -> ConfidenceDimensionScore:
    if generated is None:
        return _dimension(0.5, "generation confidence unavailable")
    report = generated.validation_report
    reasons: list[str] = []
    score = 0.92
    if report.severe_failure:
        score = min(score, 0.3)
        reasons.append("generation_severe_failure")
    if report.issues:
        score -= min(0.25, 0.05 * len(report.issues))
        reasons.append("generation_validation_issues")
    if report.applied_fallbacks:
        score -= min(0.25, 0.08 * len(report.applied_fallbacks))
        reasons.append("generation_fallbacks_applied")
    return _dimension(score, *reasons)


def _verification_confidence(
    verified: VerifyGeneratedContentOutput | None,
) -> ConfidenceDimensionScore:
    if verified is None:
        return _dimension(0.5, "verification confidence unavailable")
    report = verified.verification_report
    reasons: list[str] = []
    outcome_score = {
        VerificationDecisionOutcome.PASS: 0.98,
        VerificationDecisionOutcome.PASS_WITH_WARNINGS: 0.78,
        VerificationDecisionOutcome.REPAIR_AND_PASS: 0.68,
        VerificationDecisionOutcome.REGENERATE_TARGET: 0.25,
        VerificationDecisionOutcome.FAIL_CLOSED: 0.0,
    }[report.decision_outcome]
    score = min(outcome_score, float(report.decision_confidence))
    if report.semantic_verification.status == SemanticVerificationStatus.DEGRADED:
        score -= 0.15
        reasons.append("semantic_verification_degraded")
    if report.repair_audit.repaired_item_ids:
        score -= 0.08
        reasons.append("verification_repairs_applied")
    if not report.renderable:
        score = min(score, 0.2)
        reasons.append("verification_not_renderable")
    return _dimension(score, *reasons)


def _fallback_impact_confidence(
    fallbacks: list[dict[str, Any]],
) -> ConfidenceDimensionScore:
    if not fallbacks:
        return _dimension(1.0)
    downgraded_count = sum(1 for item in fallbacks if item.get("final_output_downgraded"))
    score = 1.0 - (0.18 * len(fallbacks)) - (0.1 * downgraded_count)
    reasons = ["fallbacks_used"]
    if downgraded_count:
        reasons.append("fallbacks_downgraded_output")
    return _dimension(score, *reasons)


def _render_confidence(
    rendered: RenderDeterministicLatexOutput | None,
    compiled: CompilePdfOutput | None,
) -> ConfidenceDimensionScore:
    reasons: list[str] = []
    if compiled is not None:
        result = compiled.compile_result
        if not result.compile_success:
            return _dimension(0.0, "compile_failed")
        score = 0.92
        if result.warnings_detected:
            score -= min(0.15, 0.03 * len(result.warnings_detected))
            reasons.append("compile_warnings_present")
        if result.errors_detected:
            score -= min(0.25, 0.08 * len(result.errors_detected))
            reasons.append("compile_errors_detected")
        return _dimension(score, *reasons)
    if rendered is None or rendered.render_output is None:
        return _dimension(0.85)
    output = rendered.render_output
    if output.status == RenderOutputStatus.FAILED:
        return _dimension(0.0, "render_failed")
    if output.status == RenderOutputStatus.PARTIAL:
        return _dimension(0.45, "render_partial")
    score = 0.9
    if output.warnings:
        score -= min(0.12, 0.04 * len(output.warnings))
        reasons.append("render_warnings_present")
    if output.diagnostics.layout_overflow:
        score -= 0.1
        reasons.append("layout_overflow_detected")
    return _dimension(score, *reasons)


def _dimension(score: float, *reasons: str) -> ConfidenceDimensionScore:
    bounded = max(0.0, min(1.0, round(score, 4)))
    if bounded >= 0.88:
        level = InternalConfidenceLevel.STRONG
    elif bounded >= 0.7:
        level = InternalConfidenceLevel.ACCEPTABLE
    elif bounded >= 0.35:
        level = InternalConfidenceLevel.DEGRADED
    else:
        level = InternalConfidenceLevel.UNSAFE
    return ConfidenceDimensionScore(score=bounded, level=level, reasons=[reason for reason in reasons if reason])
