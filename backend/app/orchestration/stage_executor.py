"""Contract-aware stage executor for Phase 6 orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
import time
from typing import TypeVar

from backend.app.metrics.storage import record_stage_metric, summarize_stage_output
from backend.app.observability import log_event
from backend.app.orchestration.enums import StageName, StageStatus
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.policies.error_classifier import classify_stage_error
from backend.app.orchestration.policies.policy_types import PolicyAction
from backend.app.orchestration.policies.retry_policy import (
    DEFAULT_POLICY_ENGINE,
    RetryFallbackPolicyEngine,
)
from backend.app.orchestration.runner import PipelineRunRecorder

T = TypeVar("T")
logger = logging.getLogger(__name__)


class StageExecutor:
    """Execute one stage with event recording, retry policy, and error typing."""

    def __init__(
        self,
        recorder: PipelineRunRecorder,
        policy_engine: RetryFallbackPolicyEngine = DEFAULT_POLICY_ENGINE,
    ) -> None:
        self.recorder = recorder
        self.policy_engine = policy_engine

    def execute(
        self,
        stage_name: StageName,
        operation: Callable[[], T],
        *,
        fallback_operation: Callable[[StageExecutionError], T] | None = None,
    ) -> T:
        """Run an operation under its declared stage contract."""

        attempts = self.policy_engine.max_attempts_for_stage(stage_name)
        last_error: StageExecutionError | None = None
        stage_started_at = datetime.now(timezone.utc)
        retry_count = 0
        fallback_used = False
        for attempt in range(1, attempts + 1):
            started_at = datetime.now(timezone.utc)
            log_event(
                logger,
                service="resume_optimizer.stage_executor",
                event_name="stage_started",
                outcome="started",
                run_id=self.recorder.run_id,
                stage_name=stage_name.value,
                metadata={"attempt_number": attempt},
            )
            self.recorder.record_stage_event(
                stage_name=stage_name,
                status=StageStatus.RUNNING,
                attempt_number=attempt,
                message=f"{stage_name.value} started.",
                started_at=started_at,
            )
            try:
                result = operation()
            except StageExecutionError as exc:
                ended_at = datetime.now(timezone.utc)
                last_error = exc
                duration_ms = _duration_ms(started_at, ended_at)
                policy_request = classify_stage_error(stage_name, exc, current_attempt=attempt)
                decision = self.policy_engine.decide(policy_request)
                failed_status = _status_for_policy_decision(decision.action)
                log_event(
                    logger,
                    level=logging.ERROR,
                    service="resume_optimizer.stage_executor",
                    event_name="stage_failed",
                    outcome="failure",
                    run_id=self.recorder.run_id,
                    stage_name=stage_name.value,
                    duration_ms=duration_ms,
                    error_code=exc.failure_type.value,
                    metadata={
                        "attempt_number": attempt,
                        "retryable": decision.retry,
                        "fallback_eligible": decision.fallback,
                        "status": failed_status.value,
                        "failure_category": exc.failure_category.value,
                    },
                )
                self.recorder.record_stage_event(
                    stage_name=stage_name,
                    status=failed_status,
                    attempt_number=attempt,
                    message=str(exc),
                    machine_payload_json={
                        "failure_type": exc.failure_type.value,
                        "failure_category": exc.failure_category.value,
                        "retryable": decision.retry,
                        "fallback_eligible": decision.fallback,
                        "policy": decision.to_event_payload(),
                    },
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                )
                if decision.action == PolicyAction.RETRY:
                    retry_count += 1
                    self.recorder.record_retry(
                        stage_name=stage_name,
                        attempt_number=attempt + 1,
                        reason=str(exc),
                        retry_strategy=decision.retry_strategy.value,
                        result_status=StageStatus.RETRYING,
                    )
                    if decision.backoff_seconds:
                        time.sleep(decision.backoff_seconds)
                    continue
                if decision.action == PolicyAction.FALLBACK:
                    fallback_used = True
                    self.recorder.record_fallback_decision(
                        stage_name=stage_name,
                        attempt_number=attempt,
                        reason=str(exc),
                        fallback_strategy=decision.fallback_strategy.value,
                        applied=fallback_operation is not None and decision.safe_to_apply_automatically,
                        escalation_note=decision.escalation_note,
                        machine_payload_json=decision.to_event_payload(),
                    )
                    if fallback_operation is not None and decision.safe_to_apply_automatically:
                        fallback_result = fallback_operation(exc)
                        fallback_ended_at = datetime.now(timezone.utc)
                        record_stage_metric(
                            stage_name=stage_name.value,
                            started_at=stage_started_at,
                            ended_at=fallback_ended_at,
                            success=True,
                            retry_count=retry_count,
                            fallback_used=True,
                            run_id=self.recorder.run_id,
                            output_metadata=summarize_stage_output(fallback_result) | {
                                "attempt_number": attempt,
                                "status": StageStatus.FALLBACK_APPLIED.value,
                            },
                        )
                        return fallback_result
                record_stage_metric(
                    stage_name=stage_name.value,
                    started_at=stage_started_at,
                    ended_at=ended_at,
                    success=False,
                    failure_type=exc.failure_type.value,
                    retry_count=retry_count,
                    fallback_used=fallback_used,
                    run_id=self.recorder.run_id,
                    output_metadata={
                        "attempt_number": attempt,
                        "status": failed_status.value,
                    },
                )
                raise
            except Exception as exc:
                ended_at = datetime.now(timezone.utc)
                classified = classify_stage_error(stage_name, exc, current_attempt=attempt)
                wrapped = StageExecutionError(
                    str(exc),
                    failure_type=classified.failure_type,
                    stage_name=stage_name,
                    http_status_code=None,
                    root_cause=exc,
                )
                last_error = wrapped
                policy_request = classify_stage_error(stage_name, wrapped, current_attempt=attempt)
                decision = self.policy_engine.decide(policy_request)
                failed_status = _status_for_policy_decision(decision.action)
                duration_ms = _duration_ms(started_at, ended_at)
                log_event(
                    logger,
                    level=logging.ERROR,
                    service="resume_optimizer.stage_executor",
                    event_name="stage_failed",
                    outcome="failure",
                    run_id=self.recorder.run_id,
                    stage_name=stage_name.value,
                    duration_ms=duration_ms,
                    error_code=wrapped.failure_type.value,
                    metadata={
                        "attempt_number": attempt,
                        "status": failed_status.value,
                        "failure_category": wrapped.failure_category.value,
                    },
                )
                self.recorder.record_stage_event(
                    stage_name=stage_name,
                    status=failed_status,
                    attempt_number=attempt,
                    message=str(exc),
                    machine_payload_json={
                        "failure_type": wrapped.failure_type.value,
                        "failure_category": wrapped.failure_category.value,
                        "policy": decision.to_event_payload(),
                    },
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                )
                if decision.action == PolicyAction.RETRY:
                    retry_count += 1
                    self.recorder.record_retry(
                        stage_name=stage_name,
                        attempt_number=attempt + 1,
                        reason=str(exc),
                        retry_strategy=decision.retry_strategy.value,
                        result_status=StageStatus.RETRYING,
                    )
                    if decision.backoff_seconds:
                        time.sleep(decision.backoff_seconds)
                    continue
                record_stage_metric(
                    stage_name=stage_name.value,
                    started_at=stage_started_at,
                    ended_at=ended_at,
                    success=False,
                    failure_type=wrapped.failure_type.value,
                    retry_count=retry_count,
                    fallback_used=fallback_used,
                    run_id=self.recorder.run_id,
                    output_metadata={
                        "attempt_number": attempt,
                        "status": failed_status.value,
                    },
                )
                raise wrapped from exc
            else:
                ended_at = datetime.now(timezone.utc)
                duration_ms = _duration_ms(started_at, ended_at)
                log_event(
                    logger,
                    service="resume_optimizer.stage_executor",
                    event_name="stage_completed",
                    outcome="success",
                    run_id=self.recorder.run_id,
                    stage_name=stage_name.value,
                    duration_ms=duration_ms,
                    metadata={"attempt_number": attempt},
                )
                self.recorder.record_stage_event(
                    stage_name=stage_name,
                    status=StageStatus.SUCCEEDED,
                    attempt_number=attempt,
                    message=f"{stage_name.value} succeeded.",
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                )
                record_stage_metric(
                    stage_name=stage_name.value,
                    started_at=stage_started_at,
                    ended_at=ended_at,
                    success=True,
                    retry_count=retry_count,
                    fallback_used=fallback_used,
                    run_id=self.recorder.run_id,
                    output_metadata=summarize_stage_output(result) | {"attempt_number": attempt},
                )
                return result
        assert last_error is not None
        raise last_error


def _status_for_policy_decision(action: PolicyAction) -> StageStatus:
    if action == PolicyAction.RETRY:
        return StageStatus.RETRYING
    if action == PolicyAction.FALLBACK:
        return StageStatus.BLOCKED
    return StageStatus.FAILED


def _duration_ms(started_at: datetime, ended_at: datetime) -> int:
    return int((ended_at - started_at).total_seconds() * 1000)
