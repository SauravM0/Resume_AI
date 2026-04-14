from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.orchestration.enums import FailureCategory, OrchestrationFailureType, StageName
from backend.app.orchestration.errors import OrchestrationError, StageExecutionError
from backend.app.orchestration.failure_handling import get_failure_definition
from backend.app.orchestration.policies.error_classifier import classify_stage_error
from backend.app.orchestration.policies.policy_types import FallbackStrategy, PolicyAction, PolicyRequest, RetryStrategy
from backend.app.orchestration.policies.retry_policy import DEFAULT_POLICY_ENGINE


def test_failure_catalog_maps_malformed_generation_to_safe_retry_policy() -> None:
    definition = get_failure_definition(OrchestrationFailureType.GENERATION_SCHEMA)

    assert definition.category == FailureCategory.MALFORMED_MODEL_OUTPUT_ERROR
    assert definition.retryable is True
    assert definition.max_retry_count == 1
    assert definition.retry_strategy == RetryStrategy.STRICTER_INSTRUCTION_PATH.value
    assert definition.allowed_fallback == FallbackStrategy.NONE.value
    assert "invalid format" in definition.user_safe_message.lower()


def test_failure_catalog_maps_verification_block_to_non_retryable_fallback() -> None:
    definition = get_failure_definition(OrchestrationFailureType.VERIFICATION_BLOCKED)

    assert definition.category == FailureCategory.VERIFICATION_ERROR
    assert definition.retryable is False
    assert definition.allowed_fallback == FallbackStrategy.SOURCE_BULLET_OR_SAFER_REWRITE.value


def test_policy_engine_keeps_verification_hard_fail_non_retryable() -> None:
    decision = DEFAULT_POLICY_ENGINE.decide(
        PolicyRequest(
            stage_name=StageName.VERIFY_GENERATED_CONTENT,
            failure_type=OrchestrationFailureType.VERIFICATION_BLOCKED,
            current_attempt=1,
        )
    )

    assert decision.action == PolicyAction.FALLBACK
    assert decision.failure_category == FailureCategory.VERIFICATION_ERROR
    assert decision.retry is False
    assert decision.fallback is True


def test_policy_engine_allows_targeted_compile_repair_after_retry_budget() -> None:
    decision = DEFAULT_POLICY_ENGINE.decide(
        PolicyRequest(
            stage_name=StageName.COMPILE_PDF,
            failure_type=OrchestrationFailureType.PDF_COMPILE,
            current_attempt=2,
        )
    )

    assert decision.action == PolicyAction.FALLBACK
    assert decision.failure_category == FailureCategory.LATEX_COMPILE_ERROR
    assert decision.fallback_strategy == FallbackStrategy.LATEX_RENDER_CORRECTION


def test_configuration_like_errors_fail_fast_with_safe_api_message() -> None:
    exc = StageExecutionError(
        "normalization exploded with internal details: /home/secret/path",
        failure_type=OrchestrationFailureType.SOURCE_PROFILE_NORMALIZATION,
        stage_name=StageName.NORMALIZE_SOURCE_DATA,
    )

    detail = exc.to_safe_api_detail()

    assert exc.failure_category == FailureCategory.CONFIGURATION_ERROR
    assert exc.retryable is False
    assert detail["message"] == "The source profile configuration is invalid."
    assert "/home/secret/path" not in str(detail)


def test_error_classifier_infers_timeout_for_uncategorized_timeout() -> None:
    classified = classify_stage_error(
        StageName.COMPILE_PDF,
        TimeoutError("compiler timed out"),
        current_attempt=1,
    )

    assert classified.failure_type == OrchestrationFailureType.TIMEOUT


def test_operator_diagnostic_preserves_root_cause_reference() -> None:
    root_cause = RuntimeError("provider said token sk-secret-123")
    exc = OrchestrationError(
        "upstream provider failed",
        failure_type=OrchestrationFailureType.GENERATION_PROVIDER,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        root_cause=root_cause,
    )

    assert exc.diagnostic_cause is root_cause
    assert exc.user_safe_message == "Structured resume generation is temporarily unavailable."
