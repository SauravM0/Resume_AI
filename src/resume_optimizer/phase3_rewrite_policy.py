"""Rewrite guardrails for Phase 3 bullet drafting.

This layer is intentionally lightweight. It does not attempt full semantic verification,
but it catches common inflation patterns early so later phases can verify or reject them
with richer context.
"""

from __future__ import annotations

import re
from collections import Counter
from enum import StrEnum

from pydantic import Field

from .models import NonEmptyStr, ScoreValue, StableId, StrictModel
from .phase3_models import Phase3SelectedBulletPayload

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+#/%-]*")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_KNOWN_TOOL_TERMS = {
    "aws",
    "azure",
    "docker",
    "gcp",
    "github",
    "github actions",
    "graphql",
    "java",
    "javascript",
    "kafka",
    "kubernetes",
    "mysql",
    "node",
    "node.js",
    "postgres",
    "postgresql",
    "python",
    "react",
    "redis",
    "snowflake",
    "terraform",
    "typescript",
}
_STRONG_ACTION_VERBS = {
    "accelerated",
    "automated",
    "built",
    "delivered",
    "designed",
    "drove",
    "improved",
    "introduced",
    "launched",
    "optimized",
    "reduced",
    "refactored",
    "rewrote",
    "scaled",
    "streamlined",
}
_LEADERSHIP_INFLATION_TERMS = {
    "architected",
    "directed",
    "drove",
    "led",
    "managed",
    "mentored",
    "owned",
    "spearheaded",
}
_LEADERSHIP_SUPPORT_TERMS = _LEADERSHIP_INFLATION_TERMS | {
    "coached",
    "coordinated",
    "guided",
    "introduced",
    "mentoring",
    "ownership",
}
_BUSINESS_IMPACT_TERMS = {
    "arr",
    "conversion",
    "customer",
    "customers",
    "pipeline",
    "revenue",
    "retention",
    "sales",
    "signup",
    "trial",
}
_AI_CLICHE_PHRASES = (
    "results-driven",
    "proven track record",
    "strategic thinker",
    "cutting-edge",
    "dynamic professional",
)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "the",
    "to",
    "with",
}

ALLOWED_REWRITE_TRANSFORMATIONS: tuple[str, ...] = (
    "compress wording while preserving meaning",
    "strengthen clarity without changing the factual claim",
    "reorder phrasing for better readability",
    "mirror job terminology only when supported by the source bullet",
)

FORBIDDEN_REWRITE_TRANSFORMATIONS: tuple[str, ...] = (
    "add numbers or metrics not present in the source bullet",
    "add tools or technologies not present in the source bullet",
    "upgrade contribution level or seniority without source support",
    "add leadership or ownership claims without source support",
    "invent domain or business impact not present in the source bullet",
)


class RewriteViolationType(StrEnum):
    """Stable violation taxonomy for later verification and analytics."""

    INSERTED_METRIC = "inserted_metric"
    INSERTED_TOOL = "inserted_tool"
    CONTRIBUTION_INFLATION = "contribution_inflation"
    LEADERSHIP_INFLATION = "leadership_inflation"
    INVENTED_BUSINESS_IMPACT = "invented_business_impact"
    AI_CLICHE = "ai_cliche"
    KEYWORD_STUFFING = "keyword_stuffing"
    WEAK_ACTION_VERB = "weak_action_verb"
    OVERLONG = "overlong"


class RewriteViolationSeverity(StrEnum):
    """Relative severity of rewrite violations."""

    WARNING = "warning"
    ERROR = "error"


class RewriteLengthPolicy(StrictModel):
    """Configurable length and repetition targets for rewritten bullets."""

    target_max_words: int = Field(default=28, ge=8, le=60)
    hard_max_words: int = Field(default=36, ge=10, le=80)
    max_repeated_term_count: int = Field(default=2, ge=1, le=5)


class RewriteViolation(StrictModel):
    """Structured signal describing one detected rewrite-policy issue."""

    violation_type: RewriteViolationType
    severity: RewriteViolationSeverity
    message: NonEmptyStr
    matched_terms: list[NonEmptyStr] = Field(default_factory=list)


class BulletRewriteAssessment(StrictModel):
    """Compact rewrite assessment for generation safeguards and later verification."""

    source_bullet_ids: list[StableId] = Field(min_length=1)
    rewritten_text: NonEmptyStr
    word_count: int = Field(ge=1)
    quality_score: ScoreValue
    hard_fail: bool = False
    violations: list[RewriteViolation] = Field(default_factory=list)
    trim_guidance: list[NonEmptyStr] = Field(default_factory=list)


def evaluate_bullet_rewrite(
    source_bullets: list[Phase3SelectedBulletPayload],
    rewritten_text: str,
    *,
    length_policy: RewriteLengthPolicy | None = None,
) -> BulletRewriteAssessment:
    """Evaluate one rewritten bullet against lightweight anti-inflation rules.

    The heuristics are intentionally conservative. They flag obvious unsupported changes
    without trying to fully prove semantic equivalence.
    """

    if not source_bullets:
        raise ValueError("source_bullets must contain at least one bullet")

    resolved_policy = length_policy or RewriteLengthPolicy()
    source_text = " ".join(bullet.text for bullet in source_bullets)
    source_tools = {
        normalized_tool
        for bullet in source_bullets
        for normalized_tool in _normalize_tool_variants(bullet.tools)
    }
    source_tokens = set(_tokenize(source_text))
    rewritten_tokens = _tokenize(rewritten_text)
    rewritten_token_counts = Counter(
        token for token in rewritten_tokens if len(token) > 2 and token not in _STOPWORDS
    )

    violations: list[RewriteViolation] = []
    violations.extend(_detect_inserted_metrics(source_text, rewritten_text))
    violations.extend(_detect_inserted_tools(source_text, rewritten_text, source_tools))
    violations.extend(_detect_contribution_inflation(source_tokens, rewritten_tokens))
    violations.extend(_detect_business_impact_inflation(source_tokens, rewritten_tokens))
    violations.extend(_detect_ai_cliches(rewritten_text))
    violations.extend(_detect_style_issues(rewritten_tokens, rewritten_token_counts, resolved_policy))

    word_count = len(rewritten_tokens)
    quality_score = _score_bullet_quality(violations, word_count, resolved_policy)
    trim_guidance = _build_trim_guidance(violations)

    return BulletRewriteAssessment(
        source_bullet_ids=[bullet.id for bullet in source_bullets],
        rewritten_text=rewritten_text.strip(),
        word_count=word_count,
        quality_score=quality_score,
        hard_fail=any(
            violation.severity == RewriteViolationSeverity.ERROR for violation in violations
        ),
        violations=violations,
        trim_guidance=trim_guidance,
    )


def passes_rewrite_policy(assessment: BulletRewriteAssessment) -> bool:
    """Return whether the assessment passes hard safety constraints."""

    return not assessment.hard_fail


def build_rewrite_policy_prompt_lines() -> list[str]:
    """Expose compact policy text so prompts can mirror the same guardrails."""

    return [
        "Allowed rewrite transformations:",
        *[f"- {item}." for item in ALLOWED_REWRITE_TRANSFORMATIONS],
        "Forbidden rewrite transformations:",
        *[f"- {item}." for item in FORBIDDEN_REWRITE_TRANSFORMATIONS],
        "- Keep bullets concise, human-sounding, ATS-aware, and free of keyword stuffing.",
        "- Prefer a strong action verb opening and keep to one line or a short two-line bullet.",
    ]


def _detect_inserted_metrics(source_text: str, rewritten_text: str) -> list[RewriteViolation]:
    source_numbers = set(_NUMBER_PATTERN.findall(source_text))
    rewritten_numbers = set(_NUMBER_PATTERN.findall(rewritten_text))
    inserted = sorted(rewritten_numbers - source_numbers)
    if not inserted:
        return []
    return [
        RewriteViolation(
            violation_type=RewriteViolationType.INSERTED_METRIC,
            severity=RewriteViolationSeverity.ERROR,
            message="Rewritten bullet introduced unsupported numeric detail.",
            matched_terms=inserted,
        )
    ]


def _detect_inserted_tools(
    source_text: str,
    rewritten_text: str,
    source_tools: set[str],
) -> list[RewriteViolation]:
    source_text_normalized = source_text.casefold()
    rewritten_text_normalized = rewritten_text.casefold()
    inserted_tools = sorted(
        tool
        for tool in _KNOWN_TOOL_TERMS
        if tool in rewritten_text_normalized
        and tool not in source_text_normalized
        and tool not in source_tools
    )
    if not inserted_tools:
        return []
    return [
        RewriteViolation(
            violation_type=RewriteViolationType.INSERTED_TOOL,
            severity=RewriteViolationSeverity.ERROR,
            message="Rewritten bullet introduced tools not supported by the source bullet.",
            matched_terms=inserted_tools,
        )
    ]


def _detect_contribution_inflation(
    source_tokens: set[str],
    rewritten_tokens: list[str],
) -> list[RewriteViolation]:
    rewritten_set = set(rewritten_tokens)
    inflation_terms = sorted(
        term for term in _LEADERSHIP_INFLATION_TERMS if term in rewritten_set and term not in source_tokens
    )
    if not inflation_terms:
        return []

    severity = (
        RewriteViolationSeverity.ERROR
        if any(term in {"led", "managed", "owned", "spearheaded", "architected"} for term in inflation_terms)
        else RewriteViolationSeverity.WARNING
    )
    return [
        RewriteViolation(
            violation_type=RewriteViolationType.LEADERSHIP_INFLATION,
            severity=severity,
            message="Rewritten bullet appears to upgrade contribution level beyond the source wording.",
            matched_terms=inflation_terms,
        )
    ]


def _detect_business_impact_inflation(
    source_tokens: set[str],
    rewritten_tokens: list[str],
) -> list[RewriteViolation]:
    inserted_terms = sorted(
        term for term in _BUSINESS_IMPACT_TERMS if term in rewritten_tokens and term not in source_tokens
    )
    if not inserted_terms:
        return []
    return [
        RewriteViolation(
            violation_type=RewriteViolationType.INVENTED_BUSINESS_IMPACT,
            severity=RewriteViolationSeverity.ERROR,
            message="Rewritten bullet introduced unsupported business-impact terminology.",
            matched_terms=inserted_terms,
        )
    ]


def _detect_ai_cliches(rewritten_text: str) -> list[RewriteViolation]:
    rewritten_text_normalized = rewritten_text.casefold()
    matched_phrases = sorted(
        phrase for phrase in _AI_CLICHE_PHRASES if phrase in rewritten_text_normalized
    )
    if not matched_phrases:
        return []
    return [
        RewriteViolation(
            violation_type=RewriteViolationType.AI_CLICHE,
            severity=RewriteViolationSeverity.WARNING,
            message="Rewritten bullet uses generic or AI-sounding phrasing.",
            matched_terms=matched_phrases,
        )
    ]


def _detect_style_issues(
    rewritten_tokens: list[str],
    rewritten_token_counts: Counter[str],
    length_policy: RewriteLengthPolicy,
) -> list[RewriteViolation]:
    violations: list[RewriteViolation] = []
    word_count = len(rewritten_tokens)

    if word_count > length_policy.hard_max_words:
        violations.append(
            RewriteViolation(
                violation_type=RewriteViolationType.OVERLONG,
                severity=RewriteViolationSeverity.ERROR,
                message="Rewritten bullet is materially over the configured hard length limit.",
            )
        )
    elif word_count > length_policy.target_max_words:
        violations.append(
            RewriteViolation(
                violation_type=RewriteViolationType.OVERLONG,
                severity=RewriteViolationSeverity.WARNING,
                message="Rewritten bullet is longer than the target concise length.",
            )
        )

    first_token = rewritten_tokens[0] if rewritten_tokens else ""
    if first_token and first_token not in _STRONG_ACTION_VERBS:
        violations.append(
            RewriteViolation(
                violation_type=RewriteViolationType.WEAK_ACTION_VERB,
                severity=RewriteViolationSeverity.WARNING,
                message="Rewritten bullet does not start with a strong action verb.",
                matched_terms=[first_token],
            )
        )

    repeated_terms = sorted(
        token
        for token, count in rewritten_token_counts.items()
        if count > length_policy.max_repeated_term_count
    )
    if repeated_terms:
        violations.append(
            RewriteViolation(
                violation_type=RewriteViolationType.KEYWORD_STUFFING,
                severity=RewriteViolationSeverity.WARNING,
                message="Rewritten bullet repeats the same terms too often.",
                matched_terms=repeated_terms,
            )
        )

    return violations


def _score_bullet_quality(
    violations: list[RewriteViolation],
    word_count: int,
    length_policy: RewriteLengthPolicy,
) -> float:
    score = 1.0
    for violation in violations:
        score -= 0.25 if violation.severity == RewriteViolationSeverity.ERROR else 0.1
    if word_count <= length_policy.target_max_words:
        score += 0.05
    return max(0.0, min(1.0, round(score, 4)))


def _build_trim_guidance(violations: list[RewriteViolation]) -> list[str]:
    guidance: list[str] = []
    violation_types = {violation.violation_type for violation in violations}
    if RewriteViolationType.OVERLONG in violation_types:
        guidance.append("Trim trailing qualifiers and keep only the strongest factual claim.")
        guidance.append("Prefer one action, one scope, and one supported outcome per bullet.")
    if RewriteViolationType.KEYWORD_STUFFING in violation_types:
        guidance.append("Remove repeated keywords and keep only the most relevant supported terms.")
    return guidance


def _normalize_tool_variants(tools: list[str]) -> set[str]:
    normalized: set[str] = set()
    for tool in tools:
        normalized.add(tool.casefold())
        normalized.add(tool.casefold().replace(".js", ""))
    return normalized


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())
