"""Stage error classification for retry/fallback policy evaluation."""

from __future__ import annotations

from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.policies.policy_types import PolicyRequest


def classify_stage_error(
    stage_name: StageName,
    exc: BaseException,
    *,
    current_attempt: int,
) -> PolicyRequest:
    """Classify an exception into the formal policy key shape."""

    if isinstance(exc, StageExecutionError):
        failure_type = exc.failure_type
        message = str(exc)
    else:
        failure_type = _infer_failure_type(stage_name, exc)
        message = str(exc) or exc.__class__.__name__
    return PolicyRequest(
        stage_name=stage_name,
        failure_type=failure_type,
        current_attempt=current_attempt,
        exception_type=exc.__class__.__name__,
        message=message,
    )


def _infer_failure_type(
    stage_name: StageName,
    exc: BaseException,
) -> OrchestrationFailureType:
    """Infer a safe failure type for uncategorized exceptions."""

    if isinstance(exc, TimeoutError):
        return OrchestrationFailureType.TIMEOUT
    if isinstance(exc, OSError) and stage_name in {
        StageName.LOAD_SOURCE_PROFILE,
        StageName.COMPILE_PDF,
        StageName.PERSIST_ARTIFACTS,
    }:
        return OrchestrationFailureType.ARTIFACT_PERSISTENCE
    return OrchestrationFailureType.INTERNAL
