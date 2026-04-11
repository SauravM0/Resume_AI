"""Retry policy matrix and policy engine for Phase 6 orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.orchestration.failure_handling import get_failure_definition
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.policies.fallback_policy import get_fallback_rule
from backend.app.orchestration.policies.policy_types import (
    FallbackStrategy,
    PolicyAction,
    PolicyDecision,
    PolicyRequest,
    RetryStrategy,
)
from resume_optimizer.config import DEFAULT_SETTINGS


@dataclass(frozen=True, slots=True)
class RetryPolicyRule:
    """Retry decision rule keyed by stage, failure type, and attempt window."""

    stage_name: StageName
    failure_type: OrchestrationFailureType
    max_attempts: int
    retry_strategy: RetryStrategy
    backoff_seconds: float
    escalation_note: str

    def can_retry(self, request: PolicyRequest) -> bool:
        """Return whether another attempt is allowed for this policy key."""

        return (
            self.stage_name == request.stage_name
            and self.failure_type == request.failure_type
            and request.current_attempt < self.max_attempts
        )


def _default_retry_policy_rules() -> tuple[RetryPolicyRule, ...]:
    settings = DEFAULT_SETTINGS.retry_policy
    return (
        RetryPolicyRule(
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
        failure_type=OrchestrationFailureType.JOB_DESCRIPTION_PARSE,
        max_attempts=settings.parse_retry_max_attempts,
        retry_strategy=RetryStrategy.STRICTER_INSTRUCTION_PATH,
        backoff_seconds=settings.fixed_backoff_seconds,
        escalation_note=(
            "Retry job parsing once. Use a stricter instruction path only if the "
            "parser adapter exposes that hook; otherwise rerun the same parser once."
        ),
    ),
        RetryPolicyRule(
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
        failure_type=OrchestrationFailureType.TIMEOUT,
        max_attempts=settings.parse_retry_max_attempts,
        retry_strategy=RetryStrategy.FIXED_BACKOFF,
        backoff_seconds=settings.fixed_backoff_seconds,
        escalation_note="Retry one transient parser timeout with fixed backoff.",
    ),
        RetryPolicyRule(
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        failure_type=OrchestrationFailureType.GENERATION_PROVIDER,
        max_attempts=settings.generation_retry_max_attempts,
        retry_strategy=RetryStrategy.FIXED_BACKOFF,
        backoff_seconds=settings.fixed_backoff_seconds,
        escalation_note="Retry one transient generation provider failure.",
    ),
        RetryPolicyRule(
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        failure_type=OrchestrationFailureType.GENERATION_SCHEMA,
        max_attempts=settings.generation_retry_max_attempts,
        retry_strategy=RetryStrategy.STRICTER_INSTRUCTION_PATH,
        backoff_seconds=settings.fixed_backoff_seconds,
        escalation_note=(
            "Retry malformed generation output once. Use stricter schema instruction "
            "path only if the generator adapter exposes it."
        ),
    ),
        RetryPolicyRule(
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        failure_type=OrchestrationFailureType.TIMEOUT,
        max_attempts=settings.generation_retry_max_attempts,
        retry_strategy=RetryStrategy.FIXED_BACKOFF,
        backoff_seconds=settings.fixed_backoff_seconds,
        escalation_note="Retry one transient generation timeout with fixed backoff.",
    ),
        RetryPolicyRule(
        stage_name=StageName.VERIFY_GENERATED_CONTENT,
        failure_type=OrchestrationFailureType.VERIFICATION_RETRYABLE,
        max_attempts=settings.verification_retry_max_attempts,
        retry_strategy=RetryStrategy.IMMEDIATE,
        backoff_seconds=0.0,
        escalation_note="Retry verifier execution errors once; do not retry verifier rejections.",
    ),
        RetryPolicyRule(
        stage_name=StageName.COMPILE_PDF,
        failure_type=OrchestrationFailureType.PDF_COMPILE,
        max_attempts=settings.pdf_compile_retry_max_attempts,
        retry_strategy=RetryStrategy.LOCAL_RENDER_CORRECTION,
        backoff_seconds=0.0,
        escalation_note=(
            "Retry PDF compilation once locally. Do not regenerate upstream content."
        ),
    ),
        RetryPolicyRule(
        stage_name=StageName.COMPILE_PDF,
        failure_type=OrchestrationFailureType.TIMEOUT,
        max_attempts=settings.pdf_compile_retry_max_attempts,
        retry_strategy=RetryStrategy.FIXED_BACKOFF,
        backoff_seconds=settings.fixed_backoff_seconds,
        escalation_note="Retry one transient PDF compiler timeout with fixed backoff.",
    ),
        RetryPolicyRule(
        stage_name=StageName.PERSIST_ARTIFACTS,
        failure_type=OrchestrationFailureType.ARTIFACT_PERSISTENCE,
        max_attempts=1,
        retry_strategy=RetryStrategy.NONE,
        backoff_seconds=0.0,
        escalation_note=(
            "Fail fast when artifact persistence cannot be trusted; do not report success."
        ),
    ),
    )


RETRY_POLICY_RULES: tuple[RetryPolicyRule, ...] = _default_retry_policy_rules()


class RetryFallbackPolicyEngine:
    """Evaluate formal retry, fallback, or fail decisions for stage errors."""

    def decide(self, request: PolicyRequest) -> PolicyDecision:
        """Return the policy decision for one failed stage attempt."""

        retry_rule = self._matching_retry_rule(request)
        definition = get_failure_definition(request.failure_type)
        if retry_rule is not None and retry_rule.can_retry(request):
            return PolicyDecision(
                action=PolicyAction.RETRY,
                stage_name=request.stage_name,
                failure_type=request.failure_type,
                failure_category=definition.category,
                current_attempt=request.current_attempt,
                retry=True,
                max_attempts=retry_rule.max_attempts,
                retry_strategy=retry_rule.retry_strategy,
                backoff_seconds=retry_rule.backoff_seconds,
                escalation_note=retry_rule.escalation_note,
            )

        fallback_rule = get_fallback_rule(
            stage_name=request.stage_name,
            failure_type=request.failure_type,
            current_attempt=request.current_attempt,
        )
        if fallback_rule is not None:
            return PolicyDecision(
                action=PolicyAction.FALLBACK,
                stage_name=request.stage_name,
                failure_type=request.failure_type,
                failure_category=definition.category,
                current_attempt=request.current_attempt,
                fallback=True,
                fallback_strategy=fallback_rule.strategy,
                max_attempts=retry_rule.max_attempts if retry_rule is not None else 1,
                safe_to_apply_automatically=fallback_rule.safe_to_apply_automatically,
                escalation_note=fallback_rule.escalation_note,
            )

        return PolicyDecision(
            action=PolicyAction.FAIL,
            stage_name=request.stage_name,
            failure_type=request.failure_type,
            failure_category=definition.category,
            current_attempt=request.current_attempt,
            fail=True,
            fallback_strategy=FallbackStrategy.NONE,
            max_attempts=retry_rule.max_attempts if retry_rule is not None else 1,
            escalation_note=(
                "No retry or fallback policy matched this stage failure; fail safely."
            ),
        )

    def max_attempts_for_stage(self, stage_name: StageName) -> int:
        """Return a bounded loop limit for a stage across all known policies."""

        attempts = [
            rule.max_attempts
            for rule in RETRY_POLICY_RULES
            if rule.stage_name == stage_name
        ]
        return max(attempts, default=1)

    def _matching_retry_rule(self, request: PolicyRequest) -> RetryPolicyRule | None:
        for rule in RETRY_POLICY_RULES:
            if rule.stage_name == request.stage_name and rule.failure_type == request.failure_type:
                return rule
        return None


DEFAULT_POLICY_ENGINE = RetryFallbackPolicyEngine()
