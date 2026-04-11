"""Typed policy decisions for Phase 6 retry and fallback handling."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from backend.app.orchestration.enums import FailureCategory, OrchestrationFailureType, StageName
from resume_optimizer.models import NonEmptyStr, StrictModel


class PolicyAction(StrEnum):
    """Terminal action chosen by the policy engine for a failed stage attempt."""

    RETRY = "retry"
    FALLBACK = "fallback"
    FAIL = "fail"


class FallbackStrategy(StrEnum):
    """Named fallback strategies that require explicit implementation hooks."""

    NONE = "none"
    DETERMINISTIC_BEST_MATCH_SUBSET = "deterministic_best_match_subset"
    SOURCE_BULLET_OR_SAFER_REWRITE = "source_bullet_or_safer_rewrite"
    LATEX_RENDER_CORRECTION = "latex_render_correction"


class RetryStrategy(StrEnum):
    """Named retry strategies for persistence and debugging."""

    NONE = "none"
    IMMEDIATE = "immediate"
    FIXED_BACKOFF = "fixed_backoff"
    STRICTER_INSTRUCTION_PATH = "stricter_instruction_path"
    LOCAL_RENDER_CORRECTION = "local_render_correction"


class PolicyRequest(StrictModel):
    """Input for evaluating one failed stage attempt."""

    stage_name: StageName
    failure_type: OrchestrationFailureType
    current_attempt: int = Field(ge=1)
    exception_type: NonEmptyStr | None = None
    message: NonEmptyStr | None = None


class PolicyDecision(StrictModel):
    """Serializable result of retry/fallback policy evaluation."""

    action: PolicyAction
    stage_name: StageName
    failure_type: OrchestrationFailureType
    failure_category: FailureCategory
    current_attempt: int = Field(ge=1)
    retry: bool = False
    fallback: bool = False
    fail: bool = False
    retry_strategy: RetryStrategy = RetryStrategy.NONE
    fallback_strategy: FallbackStrategy = FallbackStrategy.NONE
    max_attempts: int = Field(default=1, ge=1, le=10)
    backoff_seconds: float = Field(default=0.0, ge=0.0)
    escalation_note: NonEmptyStr
    safe_to_apply_automatically: bool = False

    def to_event_payload(self) -> dict[str, object]:
        """Return a JSON-safe payload for stage events and retry records."""

        return {
            "policy_action": self.action.value,
            "failure_type": self.failure_type.value,
            "failure_category": self.failure_category.value,
            "current_attempt": self.current_attempt,
            "retry": self.retry,
            "fallback": self.fallback,
            "fail": self.fail,
            "retry_strategy": self.retry_strategy.value,
            "fallback_strategy": self.fallback_strategy.value,
            "max_attempts": self.max_attempts,
            "backoff_seconds": self.backoff_seconds,
            "safe_to_apply_automatically": self.safe_to_apply_automatically,
            "escalation_note": self.escalation_note,
        }
