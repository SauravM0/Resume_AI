"""Explicit safe fallback catalog and audit helpers for orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.orchestration.enums import ArtifactKind, StageName
from backend.app.privacy import sanitize_diagnostic_text, sanitize_value
from resume_optimizer.phase3_output_validation import (
    Phase3FallbackAction,
    Phase3FallbackActionType,
)

WEAK_PARSE_CONFIDENCE_THRESHOLD = 0.65


class FallbackClass:
    """Stable names for explicit, bounded fallback behaviors."""

    USE_ORIGINAL_SOURCE_BULLET = "use_original_source_bullet"
    REDUCE_SUMMARY_TO_SAFE_SHORT_FORM = "reduce_summary_to_safe_short_form"
    DROP_LOW_PRIORITY_SECTION = "drop_low_priority_section"
    SKIP_OPTIONAL_ARTIFACT_GENERATION = "skip_optional_artifact_generation"
    USE_DETERMINISTIC_PARSE_SIGNALS = "use_deterministic_parse_signals"
    USE_CONSERVATIVE_HEADLINE = "use_conservative_headline"
    USE_SUPPORTED_SKILL_HIGHLIGHTS = "use_supported_skill_highlights"
    REBUILD_GENERATION_METADATA = "rebuild_generation_metadata"


@dataclass(frozen=True, slots=True)
class FallbackRule:
    """One explicit fallback definition with its safety boundaries."""

    fallback_class: str
    stage_name: StageName
    allowed_when: str
    quality_tradeoff: str
    affects_final_confidence: bool


FALLBACK_RULES: dict[str, FallbackRule] = {
    FallbackClass.USE_ORIGINAL_SOURCE_BULLET: FallbackRule(
        fallback_class=FallbackClass.USE_ORIGINAL_SOURCE_BULLET,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        allowed_when="A rewritten bullet fails validation or verification but the source bullet is supported.",
        quality_tradeoff="Uses less polished source phrasing instead of an unsupported rewrite.",
        affects_final_confidence=True,
    ),
    FallbackClass.REDUCE_SUMMARY_TO_SAFE_SHORT_FORM: FallbackRule(
        fallback_class=FallbackClass.REDUCE_SUMMARY_TO_SAFE_SHORT_FORM,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        allowed_when="A generated summary is invalid, inflated, or weakly supported.",
        quality_tradeoff="Uses a shorter, more conservative summary with reduced coverage.",
        affects_final_confidence=True,
    ),
    FallbackClass.DROP_LOW_PRIORITY_SECTION: FallbackRule(
        fallback_class=FallbackClass.DROP_LOW_PRIORITY_SECTION,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        allowed_when="Optional content must be omitted due to page budget or render pressure.",
        quality_tradeoff="Reduces resume completeness to preserve render safety and core relevance.",
        affects_final_confidence=True,
    ),
    FallbackClass.SKIP_OPTIONAL_ARTIFACT_GENERATION: FallbackRule(
        fallback_class=FallbackClass.SKIP_OPTIONAL_ARTIFACT_GENERATION,
        stage_name=StageName.COMPILE_PDF,
        allowed_when="Core PDF persistence succeeded but optional compile artifacts could not be persisted.",
        quality_tradeoff="Compile diagnostics or LaTeX source may be unavailable even though the PDF succeeded.",
        affects_final_confidence=False,
    ),
    FallbackClass.USE_DETERMINISTIC_PARSE_SIGNALS: FallbackRule(
        fallback_class=FallbackClass.USE_DETERMINISTIC_PARSE_SIGNALS,
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
        allowed_when="Parser confidence is weak and deterministic extraction remains available.",
        quality_tradeoff="Relies more heavily on conservative deterministic parse signals with reduced nuance.",
        affects_final_confidence=True,
    ),
    FallbackClass.USE_CONSERVATIVE_HEADLINE: FallbackRule(
        fallback_class=FallbackClass.USE_CONSERVATIVE_HEADLINE,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        allowed_when="A generated headline is unsupported or inflated.",
        quality_tradeoff="Uses a simpler supported headline with less specificity.",
        affects_final_confidence=True,
    ),
    FallbackClass.USE_SUPPORTED_SKILL_HIGHLIGHTS: FallbackRule(
        fallback_class=FallbackClass.USE_SUPPORTED_SKILL_HIGHLIGHTS,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        allowed_when="Generated skill highlights are invalid or missing but supported matched skills exist.",
        quality_tradeoff="Uses a narrower supported skill set instead of a broader highlight set.",
        affects_final_confidence=True,
    ),
    FallbackClass.REBUILD_GENERATION_METADATA: FallbackRule(
        fallback_class=FallbackClass.REBUILD_GENERATION_METADATA,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        allowed_when="Phase 3 metadata is invalid and can be rebuilt deterministically from validated output.",
        quality_tradeoff="Preserves output while replacing unreliable metadata bookkeeping.",
        affects_final_confidence=False,
    ),
}


def get_fallback_rule(fallback_class: str) -> FallbackRule:
    """Return the configured rule for one fallback class."""

    return FALLBACK_RULES[fallback_class]


def phase3_fallback_class(action: Phase3FallbackAction) -> str | None:
    """Map a validated Phase 3 fallback action to the orchestration catalog."""

    mapping = {
        Phase3FallbackActionType.HEADLINE_FALLBACK: FallbackClass.USE_CONSERVATIVE_HEADLINE,
        Phase3FallbackActionType.SUMMARY_FALLBACK: FallbackClass.REDUCE_SUMMARY_TO_SAFE_SHORT_FORM,
        Phase3FallbackActionType.BULLET_SOURCE_FALLBACK: FallbackClass.USE_ORIGINAL_SOURCE_BULLET,
        Phase3FallbackActionType.EXPERIENCE_SOURCE_FALLBACK: FallbackClass.USE_ORIGINAL_SOURCE_BULLET,
        Phase3FallbackActionType.PROJECT_SOURCE_FALLBACK: FallbackClass.USE_ORIGINAL_SOURCE_BULLET,
        Phase3FallbackActionType.SKILL_FALLBACK: FallbackClass.USE_SUPPORTED_SKILL_HIGHLIGHTS,
        Phase3FallbackActionType.DROP_OPTIONAL_SECTION: FallbackClass.DROP_LOW_PRIORITY_SECTION,
        Phase3FallbackActionType.METADATA_REBUILT: FallbackClass.REBUILD_GENERATION_METADATA,
    }
    return mapping.get(action.action_type)


def should_use_deterministic_parse_fallback(
    *,
    parser_confidence: float | None,
    has_deterministic_extraction: bool,
) -> bool:
    """Return whether parse output should be marked as using deterministic fallback signals."""

    if not has_deterministic_extraction:
        return False
    if parser_confidence is None:
        return False
    return parser_confidence < WEAK_PARSE_CONFIDENCE_THRESHOLD


def build_fallback_audit_payload(
    *,
    fallback_class: str,
    reason: str,
    final_output_downgraded: bool,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable machine payload for fallback audit events."""

    rule = get_fallback_rule(fallback_class)
    return {
        "fallback_class": fallback_class,
        "allowed_when": rule.allowed_when,
        "quality_tradeoff": rule.quality_tradeoff,
        "affects_final_confidence": rule.affects_final_confidence,
        "final_output_downgraded": final_output_downgraded,
        "reason": sanitize_diagnostic_text(reason),
        **sanitize_value(extra_metadata or {}),
    }


def optional_artifact_fallback_metadata(
    artifact_kind: ArtifactKind,
    *,
    artifact_name: str,
    error_message: str,
) -> dict[str, Any]:
    """Return sanitized metadata for optional compile-artifact fallback audits."""

    return {
        "artifact_kind": artifact_kind.value,
        "artifact_name": artifact_name,
        "artifact_error": sanitize_diagnostic_text(error_message),
    }
