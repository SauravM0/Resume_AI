"""Shared conservative rewrite-policy enforcement for Phase 5 generation."""

from __future__ import annotations

from enum import StrEnum
import re

from pydantic import Field

from ..models import NonEmptyStr, StableId, StrictModel
from ..phase1_role_modeling import OrganizationalRoleMode
from .contracts import (
    PolicyReasonCode,
    PolicySignalSeverity,
    QualitySignal,
    QualitySignalSeverity,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+#/%-]*")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_YEARS_PATTERN = re.compile(r"\b\d+\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
_KNOWN_TOOL_TERMS = {
    "airflow",
    "aws",
    "azure",
    "bigquery",
    "datadog",
    "docker",
    "gcp",
    "github",
    "github actions",
    "gitlab",
    "graphql",
    "java",
    "javascript",
    "kafka",
    "kubernetes",
    "mysql",
    "next.js",
    "node",
    "node.js",
    "pandas",
    "postgres",
    "postgresql",
    "python",
    "react",
    "redis",
    "snowflake",
    "spark",
    "sql",
    "terraform",
    "typescript",
}
_OWNERSHIP_RISK_PAIRS = {
    "supported": {"owned", "led", "managed", "architected"},
    "contributed": {"led", "owned", "managed", "architected"},
    "helped": {"led", "owned", "managed", "architected"},
    "assisted": {"led", "owned", "managed", "architected"},
}
_LEADERSHIP_TERMS = {
    "architected",
    "directed",
    "headed",
    "led",
    "managed",
    "manager",
    "mentored",
    "owned",
}
_SCOPE_RISK_TERMS = {
    "company-wide",
    "cross-functional",
    "end-to-end",
    "global",
    "organization-wide",
    "org-wide",
    "platform-wide",
}
_SPECIALIZATION_TERMS = {
    "authority",
    "deep expertise",
    "domain expert",
    "expert",
    "expertise",
    "mastery",
    "specialist",
    "specialized",
    "subject matter expert",
}
_DOMAIN_HINT_TERMS = {
    "adtech",
    "analytics",
    "banking",
    "consumer",
    "ecommerce",
    "fintech",
    "healthcare",
    "insurance",
    "payments",
    "platform",
    "retail",
    "saas",
    "security",
}
_IC_MODES = {
    OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
    OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
    OrganizationalRoleMode.RESEARCHER,
}


class RewritePolicyTarget(StrEnum):
    """Generation surface that produced the candidate text."""

    SUMMARY = "summary"
    BULLET = "bullet"


class RewritePolicyContext(StrictModel):
    """Deterministic support context for policy evaluation."""

    target: RewritePolicyTarget
    section_id: StableId
    source_item_id: StableId | None = None
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    source_text: NonEmptyStr
    candidate_text: NonEmptyStr
    allowed_tools: list[NonEmptyStr] = Field(default_factory=list)
    supported_domain_phrases: list[NonEmptyStr] = Field(default_factory=list)
    leadership_supported: bool = False
    organizational_role_mode: OrganizationalRoleMode


class RewritePolicyViolation(StrictModel):
    """One machine-readable Phase 5 rewrite-policy violation."""

    signal_id: StableId
    reason_code: PolicyReasonCode
    policy_severity: PolicySignalSeverity
    message: NonEmptyStr
    matched_terms: list[NonEmptyStr] = Field(default_factory=list)
    section_id: StableId
    source_item_id: StableId | None = None
    source_bullet_ids: list[StableId] = Field(default_factory=list)

    def to_quality_signal(self) -> QualitySignal:
        severity = (
            QualitySignalSeverity.WARNING
            if self.policy_severity == PolicySignalSeverity.SOFT_WARNING
            else QualitySignalSeverity.ERROR
        )
        return QualitySignal(
            signal_id=self.signal_id,
            severity=severity,
            message=self.message,
            reason_code=self.reason_code,
            policy_severity=self.policy_severity,
            section_id=self.section_id,
            source_item_id=self.source_item_id,
            source_bullet_ids=self.source_bullet_ids,
        )


class RewritePolicyEvaluation(StrictModel):
    """Policy evaluation result for one candidate text."""

    violations: list[RewritePolicyViolation] = Field(default_factory=list)

    @property
    def blocking_violations(self) -> list[RewritePolicyViolation]:
        return [
            violation
            for violation in self.violations
            if violation.policy_severity
            in {
                PolicySignalSeverity.HARD_BLOCK,
                PolicySignalSeverity.FALLBACK_TO_SOURCE,
                PolicySignalSeverity.REQUIRES_REGENERATION,
            }
        ]

    @property
    def warning_violations(self) -> list[RewritePolicyViolation]:
        return [
            violation
            for violation in self.violations
            if violation.policy_severity == PolicySignalSeverity.SOFT_WARNING
        ]

    def to_quality_signals(self) -> tuple[list[QualitySignal], list[QualitySignal]]:
        return (
            [violation.to_quality_signal() for violation in self.blocking_violations],
            [violation.to_quality_signal() for violation in self.warning_violations],
        )


def evaluate_rewrite_policy(context: RewritePolicyContext) -> RewritePolicyEvaluation:
    """Evaluate one generated summary or bullet against conservative rewrite rules."""

    source_text = context.source_text
    candidate_text = context.candidate_text
    source_tokens = set(_tokenize(source_text))
    candidate_tokens = set(_tokenize(candidate_text))
    domain_tokens = {token for phrase in context.supported_domain_phrases for token in _tokenize(phrase)}
    violations: list[RewritePolicyViolation] = []

    violations.extend(
        _unsupported_number_violations(
            context,
            source_text=source_text,
            candidate_text=candidate_text,
        )
    )
    violations.extend(
        _unsupported_tool_violations(
            context,
            source_text=source_text,
            candidate_text=candidate_text,
        )
    )
    violations.extend(
        _ownership_inflation_violations(
            context,
            source_tokens=source_tokens,
            candidate_tokens=candidate_tokens,
        )
    )
    violations.extend(
        _leadership_inflation_violations(
            context,
            source_tokens=source_tokens,
            candidate_tokens=candidate_tokens,
        )
    )
    violations.extend(
        _scope_inflation_violations(
            context,
            source_text=source_text,
            candidate_text=candidate_text,
        )
    )
    violations.extend(
        _domain_inflation_violations(
            context,
            source_tokens=source_tokens,
            candidate_tokens=candidate_tokens,
            domain_tokens=domain_tokens,
        )
    )
    violations.extend(
        _specialization_violations(
            context,
            source_text=source_text,
            candidate_text=candidate_text,
        )
    )
    violations.extend(
        _years_experience_violations(
            context,
            source_text=source_text,
            candidate_text=candidate_text,
        )
    )
    return RewritePolicyEvaluation(violations=violations)


def _unsupported_number_violations(
    context: RewritePolicyContext,
    *,
    source_text: str,
    candidate_text: str,
) -> list[RewritePolicyViolation]:
    source_numbers = set(_NUMBER_PATTERN.findall(source_text))
    candidate_numbers = set(_NUMBER_PATTERN.findall(candidate_text))
    inserted = sorted(candidate_numbers - source_numbers)
    if not inserted:
        return []
    return [
        _violation(
            context,
            reason_code=PolicyReasonCode.UNSUPPORTED_NUMBER,
            policy_severity=PolicySignalSeverity.HARD_BLOCK,
            message="generated text introduced unsupported numeric detail",
            matched_terms=inserted,
        )
    ]


def _unsupported_tool_violations(
    context: RewritePolicyContext,
    *,
    source_text: str,
    candidate_text: str,
) -> list[RewritePolicyViolation]:
    source_text_lower = source_text.casefold()
    candidate_text_lower = candidate_text.casefold()
    allowed_tools = {tool.casefold() for tool in context.allowed_tools}
    inserted = sorted(
        tool
        for tool in _KNOWN_TOOL_TERMS
        if tool in candidate_text_lower and tool not in source_text_lower and tool not in allowed_tools
    )
    if not inserted:
        return []
    return [
        _violation(
            context,
            reason_code=PolicyReasonCode.UNSUPPORTED_TOOL,
            policy_severity=PolicySignalSeverity.HARD_BLOCK,
            message="generated text introduced unsupported tools or platforms",
            matched_terms=inserted,
        )
    ]


def _ownership_inflation_violations(
    context: RewritePolicyContext,
    *,
    source_tokens: set[str],
    candidate_tokens: set[str],
) -> list[RewritePolicyViolation]:
    violations: list[RewritePolicyViolation] = []
    severity = _inflation_policy_severity(context.target)
    for source_term, blocked_terms in _OWNERSHIP_RISK_PAIRS.items():
        if source_term not in source_tokens:
            continue
        inserted = sorted(term for term in blocked_terms if term in candidate_tokens and term not in source_tokens)
        if not inserted:
            continue
        violations.append(
            _violation(
                context,
                reason_code=PolicyReasonCode.OWNERSHIP_INFLATION,
                policy_severity=severity,
                message=f"generated text upgraded ownership from '{source_term}' to stronger ownership language",
                matched_terms=inserted,
            )
        )
    return violations


def _leadership_inflation_violations(
    context: RewritePolicyContext,
    *,
    source_tokens: set[str],
    candidate_tokens: set[str],
) -> list[RewritePolicyViolation]:
    if context.leadership_supported:
        return []
    inserted = sorted(term for term in _LEADERSHIP_TERMS if term in candidate_tokens and term not in source_tokens)
    if not inserted and context.organizational_role_mode not in _IC_MODES:
        return []
    if not inserted:
        return []
    return [
        _violation(
            context,
            reason_code=PolicyReasonCode.LEADERSHIP_INFLATION,
            policy_severity=_inflation_policy_severity(context.target),
            message="generated text introduced unsupported leadership language",
            matched_terms=inserted,
        )
    ]


def _scope_inflation_violations(
    context: RewritePolicyContext,
    *,
    source_text: str,
    candidate_text: str,
) -> list[RewritePolicyViolation]:
    source_text_lower = source_text.casefold()
    candidate_text_lower = candidate_text.casefold()
    inserted = sorted(
        term for term in _SCOPE_RISK_TERMS if term in candidate_text_lower and term not in source_text_lower
    )
    if "architecture" in _tokenize(candidate_text) and "architecture" not in _tokenize(source_text):
        inserted.append("architecture")
    inserted = sorted(set(inserted))
    if not inserted:
        return []
    return [
        _violation(
            context,
            reason_code=PolicyReasonCode.SCOPE_INFLATION,
            policy_severity=_inflation_policy_severity(context.target),
            message="generated text introduced unsupported scope or system-level ownership claims",
            matched_terms=inserted,
        )
    ]


def _domain_inflation_violations(
    context: RewritePolicyContext,
    *,
    source_tokens: set[str],
    candidate_tokens: set[str],
    domain_tokens: set[str],
) -> list[RewritePolicyViolation]:
    monitored_domain_terms = domain_tokens | _DOMAIN_HINT_TERMS
    inserted = sorted(
        token
        for token in monitored_domain_terms
        if token in candidate_tokens and token not in source_tokens and token not in domain_tokens
    )
    if not inserted:
        return []
    return [
        _violation(
            context,
            reason_code=PolicyReasonCode.DOMAIN_INFLATION,
            policy_severity=_inflation_policy_severity(context.target),
            message="generated text introduced unsupported domain specialization",
            matched_terms=inserted,
        )
    ]


def _specialization_violations(
    context: RewritePolicyContext,
    *,
    source_text: str,
    candidate_text: str,
) -> list[RewritePolicyViolation]:
    source_text_lower = source_text.casefold()
    candidate_text_lower = candidate_text.casefold()
    inserted = sorted(
        term for term in _SPECIALIZATION_TERMS if term in candidate_text_lower and term not in source_text_lower
    )
    if not inserted:
        return []
    return [
        _violation(
            context,
            reason_code=PolicyReasonCode.FAKE_SPECIALIZATION,
            policy_severity=_inflation_policy_severity(context.target),
            message="generated text introduced unsupported specialization or expertise claims",
            matched_terms=inserted,
        )
    ]


def _years_experience_violations(
    context: RewritePolicyContext,
    *,
    source_text: str,
    candidate_text: str,
) -> list[RewritePolicyViolation]:
    source_years = set(_YEARS_PATTERN.findall(source_text))
    candidate_years = set(_YEARS_PATTERN.findall(candidate_text))
    inserted = sorted(candidate_years - source_years)
    if "decade" in candidate_text.casefold() and "decade" not in source_text.casefold():
        inserted.append("decade")
    inserted = sorted(set(inserted))
    if not inserted:
        return []
    return [
        _violation(
            context,
            reason_code=PolicyReasonCode.UNSUPPORTED_YEARS_EXPERIENCE,
            policy_severity=PolicySignalSeverity.HARD_BLOCK,
            message="generated text introduced unsupported years-of-experience phrasing",
            matched_terms=inserted,
        )
    ]


def _inflation_policy_severity(target: RewritePolicyTarget) -> PolicySignalSeverity:
    if target == RewritePolicyTarget.BULLET:
        return PolicySignalSeverity.FALLBACK_TO_SOURCE
    return PolicySignalSeverity.REQUIRES_REGENERATION


def _violation(
    context: RewritePolicyContext,
    *,
    reason_code: PolicyReasonCode,
    policy_severity: PolicySignalSeverity,
    message: str,
    matched_terms: list[str],
) -> RewritePolicyViolation:
    suffix = context.source_bullet_ids[0] if context.source_bullet_ids else context.section_id
    return RewritePolicyViolation(
        signal_id=f"policy.{context.target.value}.{reason_code.value}.{suffix}",
        reason_code=reason_code,
        policy_severity=policy_severity,
        message=message,
        matched_terms=matched_terms,
        section_id=context.section_id,
        source_item_id=context.source_item_id,
        source_bullet_ids=context.source_bullet_ids,
    )


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())
