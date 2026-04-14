"""Structured errors for Phase 6 orchestration services."""

from __future__ import annotations

from backend.app.orchestration.enums import FailureCategory, OrchestrationFailureType, StageName
from backend.app.orchestration.failure_handling import get_failure_definition
from backend.app.privacy import sanitize_diagnostic_text, sanitize_exception_message


class OrchestrationError(RuntimeError):
    """Base error with API and stage classification metadata."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: OrchestrationFailureType = OrchestrationFailureType.INTERNAL,
        stage_name: StageName | None = None,
        retryable: bool | None = None,
        fallback_eligible: bool | None = None,
        http_status_code: int | None = None,
        run_id: str | None = None,
        user_safe_message: str | None = None,
        operator_diagnostic_message: str | None = None,
        root_cause: BaseException | None = None,
    ) -> None:
        super().__init__(sanitize_exception_message(message))
        definition = get_failure_definition(failure_type)
        self.failure_type = failure_type
        self.failure_category: FailureCategory = definition.category
        self.stage_name = stage_name
        self.retryable = definition.retryable if retryable is None else retryable
        self.fallback_eligible = (
            definition.allowed_fallback != "none"
            if fallback_eligible is None
            else fallback_eligible
        )
        self.http_status_code = definition.default_http_status if http_status_code is None else http_status_code
        self.run_id = run_id
        self.user_safe_message = user_safe_message or definition.user_safe_message
        self.operator_diagnostic_message = sanitize_diagnostic_text(
            operator_diagnostic_message or definition.operator_message,
            default=definition.operator_message,
        )
        self.root_cause = root_cause

    @property
    def diagnostic_cause(self) -> BaseException | None:
        """Return the deepest known root cause when available."""

        return self.root_cause or self.__cause__

    def to_safe_api_detail(self) -> dict[str, object]:
        """Return a public-safe API error payload."""

        return {
            "message": self.user_safe_message,
            "failure_type": self.failure_type.value,
            "failure_category": self.failure_category.value,
            "stage_name": self.stage_name.value if self.stage_name is not None else None,
            "retryable": self.retryable,
            "fallback_eligible": self.fallback_eligible,
            "run_id": self.run_id,
        }


class StageExecutionError(OrchestrationError):
    """Raised when a stage fails after contract-aware classification."""
