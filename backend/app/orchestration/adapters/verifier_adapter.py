"""Adapter for the Phase 6 generated-content verification gate."""

from __future__ import annotations

from collections.abc import Callable
import logging

from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.enums import OrchestrationFailureType, StageName, StageStatus
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.pipeline_models import VerifyGeneratedContentInput, VerifyGeneratedContentOutput
from backend.app.orchestration.types import PipelineArtifactRef
from backend.app.schemas.verification import Phase3VerificationInput
from backend.app.services.verification.orchestrator import (
    VerificationOrchestrator,
    build_default_verification_orchestrator,
)
from backend.app.services.verification.types import VerificationDecisionOutcome, VerificationStatus

logger = logging.getLogger(__name__)

TargetedRecoveryHandler = Callable[
    [VerifyGeneratedContentInput, VerifyGeneratedContentOutput, StageExecutionContext],
    VerifyGeneratedContentOutput,
]


class VerifierAdapter:
    """Wrap the Phase 6 verification orchestrator."""

    stage_name = StageName.VERIFY_GENERATED_CONTENT

    def __init__(
        self,
        *,
        orchestrator_factory: Callable[[], VerificationOrchestrator] = build_default_verification_orchestrator,
        targeted_recovery_handler: TargetedRecoveryHandler | None = None,
    ) -> None:
        self._orchestrator_factory = orchestrator_factory
        self._targeted_recovery_handler = targeted_recovery_handler

    def execute(
        self,
        stage_input: VerifyGeneratedContentInput,
        context: StageExecutionContext,
    ) -> VerifyGeneratedContentOutput:
        """Run Phase 6 verification and enforce render gate status."""

        try:
            verification_result = self._orchestrator_factory().run(
                Phase3VerificationInput(
                    source_profile_id=stage_input.source_profile_id,
                    job_analysis=stage_input.job_analysis,
                    source_profile=stage_input.source_profile,
                    generation_payload=stage_input.generation_payload,
                    phase3_result=stage_input.phase3_result,
                    phase3_validation_report=stage_input.phase3_validation_report,
                ),
                generation_id=stage_input.phase3_result.metadata.source_profile_id,
                pipeline_run_id=context.run_id,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"verification failed: {exc}",
                failure_type=OrchestrationFailureType.VERIFICATION_RETRYABLE,
                stage_name=self.stage_name,
                retryable=True,
            ) from exc

        stage_output = VerifyGeneratedContentOutput(
            verification_run_id=verification_result.verification_run_id,
            verification_report=verification_result.report,
            rendering_output=verification_result.rendering_output,
        )
        self._record_verification_events(stage_output, context)

        decision = verification_result.report.decision_outcome
        if decision == VerificationDecisionOutcome.REGENERATE_TARGET:
            if self._targeted_recovery_handler is not None:
                recovered = self._targeted_recovery_handler(stage_input, stage_output, context)
                self._record_gate_decision_event(
                    context,
                    message="Targeted regeneration path executed for verification gate.",
                    outcome=recovered.verification_report.decision_outcome,
                    status=StageStatus.FALLBACK_APPLIED,
                    extra={"targeted_recovery": True},
                )
                return recovered
            raise StageExecutionError(
                "verification requested targeted regeneration before rendering",
                failure_type=OrchestrationFailureType.VERIFICATION_RETRYABLE,
                stage_name=self.stage_name,
                retryable=True,
                fallback_eligible=True,
            )
        if decision == VerificationDecisionOutcome.FAIL_CLOSED or verification_result.report.status in {
            VerificationStatus.FAILED,
            VerificationStatus.BLOCKED,
        }:
            raise StageExecutionError(
                f"verification rejected generated content: {decision.value}",
                failure_type=OrchestrationFailureType.VERIFICATION_BLOCKED,
                stage_name=self.stage_name,
                http_status_code=409,
            )
        return stage_output

    def extract_artifacts(
        self,
        stage_output: VerifyGeneratedContentOutput,
        context: StageExecutionContext,
    ) -> list[PipelineArtifactRef]:
        return []

    def _record_verification_events(
        self,
        stage_output: VerifyGeneratedContentOutput,
        context: StageExecutionContext,
    ) -> None:
        """Emit explicit verification-stage lifecycle events for gate inspection."""

        report = stage_output.verification_report
        audit = report.semantic_verification
        repair_audit = report.repair_audit
        if context.recorder is None:
            return

        if audit.degraded_item_ids:
            context.recorder.record_stage_event(
                stage_name=self.stage_name,
                status=StageStatus.SUCCEEDED,
                attempt_number=1,
                message="verification completed in degraded semantic mode",
                machine_payload_json={
                    "verification_run_id": stage_output.verification_run_id,
                    "decision_outcome": report.decision_outcome.value,
                    "degraded_item_ids": list(audit.degraded_item_ids),
                },
            )
        if repair_audit.repaired_item_ids:
            context.recorder.record_stage_event(
                stage_name=self.stage_name,
                status=StageStatus.FALLBACK_APPLIED,
                attempt_number=1,
                message="verification repairs applied to generated content",
                machine_payload_json={
                    "verification_run_id": stage_output.verification_run_id,
                    "repaired_item_ids": list(repair_audit.repaired_item_ids),
                    "repair_count": len(repair_audit.repaired_item_ids),
                },
            )
        self._record_gate_decision_event(
            context,
            message=f"verification gate decision: {report.decision_outcome.value}",
            outcome=report.decision_outcome,
            status=(
                StageStatus.BLOCKED
                if report.decision_outcome == VerificationDecisionOutcome.FAIL_CLOSED
                else StageStatus.SUCCEEDED
            ),
            extra={
                "verification_run_id": stage_output.verification_run_id,
                "decision_confidence": report.decision_confidence,
                "renderable": report.renderable,
            },
        )
        logger.info(
            "verification gate evaluated",
            extra={
                "run_id": context.run_id,
                "verification_run_id": stage_output.verification_run_id,
                "decision_outcome": report.decision_outcome.value,
                "decision_confidence": report.decision_confidence,
                "repaired_item_count": len(repair_audit.repaired_item_ids),
                "degraded_mode": bool(audit.degraded_item_ids),
            },
        )

    def _record_gate_decision_event(
        self,
        context: StageExecutionContext,
        *,
        message: str,
        outcome: VerificationDecisionOutcome,
        status: StageStatus,
        extra: dict[str, object] | None = None,
    ) -> None:
        """Append a concise gate-decision event to the run recorder."""

        if context.recorder is None:
            return
        context.recorder.record_stage_event(
            stage_name=self.stage_name,
            status=status,
            attempt_number=1,
            message=message,
            machine_payload_json={
                "decision_outcome": outcome.value,
                **(extra or {}),
            },
        )
