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

from backend.app.orchestration.enums import OrchestrationFailureType, StageName, StageStatus
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.policies.policy_types import (
    FallbackStrategy,
    PolicyAction,
    PolicyRequest,
    RetryStrategy,
)
from backend.app.orchestration.policies.retry_policy import DEFAULT_POLICY_ENGINE
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.orchestration.stage_executor import StageExecutor


def _recorder() -> PipelineRunRecorder:
    recorder = PipelineRunRecorder()
    recorder.create_run(
        run_id="run.retry-policy-test",
        requested_template="ats_standard",
        requested_mode="resume_pdf",
        job_description_hash="sha256:test",
        source_profile_id="profile.retry-policy-test",
    )
    return recorder


def test_policy_engine_retries_malformed_generation_once() -> None:
    decision = DEFAULT_POLICY_ENGINE.decide(
        PolicyRequest(
            stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
            failure_type=OrchestrationFailureType.GENERATION_SCHEMA,
            current_attempt=1,
        )
    )

    assert decision.action == PolicyAction.RETRY
    assert decision.retry is True
    assert decision.retry_strategy == RetryStrategy.STRICTER_INSTRUCTION_PATH
    assert decision.max_attempts == 2


def test_policy_engine_fails_generation_schema_after_retry_budget() -> None:
    decision = DEFAULT_POLICY_ENGINE.decide(
        PolicyRequest(
            stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
            failure_type=OrchestrationFailureType.GENERATION_SCHEMA,
            current_attempt=2,
        )
    )

    assert decision.action == PolicyAction.FAIL
    assert decision.fail is True


def test_policy_engine_allows_verification_fallback_decision_without_auto_apply() -> None:
    decision = DEFAULT_POLICY_ENGINE.decide(
        PolicyRequest(
            stage_name=StageName.VERIFY_GENERATED_CONTENT,
            failure_type=OrchestrationFailureType.VERIFICATION_BLOCKED,
            current_attempt=1,
        )
    )

    assert decision.action == PolicyAction.FALLBACK
    assert decision.fallback is True
    assert decision.fallback_strategy == FallbackStrategy.SOURCE_BULLET_OR_SAFER_REWRITE
    assert decision.safe_to_apply_automatically is False


def test_stage_executor_persists_retry_attempt_and_does_not_rerun_full_pipeline() -> None:
    recorder = _recorder()
    executor = StageExecutor(recorder)
    calls = {"count": 0}

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise StageExecutionError(
                "verifier service transient failure",
                failure_type=OrchestrationFailureType.VERIFICATION_RETRYABLE,
                stage_name=StageName.VERIFY_GENERATED_CONTENT,
                retryable=True,
            )
        return "verified"

    result = executor.execute(StageName.VERIFY_GENERATED_CONTENT, operation)

    assert result == "verified"
    assert calls["count"] == 2
    assert recorder.retry_attempts == [
        {
            "stage_name": StageName.VERIFY_GENERATED_CONTENT.value,
            "attempt_number": 2,
            "reason": "verifier service transient failure",
            "retry_strategy": RetryStrategy.IMMEDIATE.value,
            "result_status": StageStatus.RETRYING.value,
        }
    ]


def test_stage_executor_persists_fallback_decision_without_fake_success() -> None:
    recorder = _recorder()
    executor = StageExecutor(recorder)

    def operation() -> str:
        raise StageExecutionError(
            "empty rank result",
            failure_type=OrchestrationFailureType.RANKING_SELECTION,
            stage_name=StageName.RANK_SELECT_EVIDENCE,
        )

    with pytest.raises(StageExecutionError):
        executor.execute(StageName.RANK_SELECT_EVIDENCE, operation)

    assert recorder.fallback_decisions
    fallback = recorder.fallback_decisions[0]
    assert fallback["stage_name"] == StageName.RANK_SELECT_EVIDENCE.value
    assert fallback["fallback_strategy"] == FallbackStrategy.DETERMINISTIC_BEST_MATCH_SUBSET.value
    assert fallback["applied"] is False
    assert recorder.stage_events[-1]["status"] == StageStatus.SKIPPED.value
