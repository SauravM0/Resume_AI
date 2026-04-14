from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.orchestration.adapters.verifier_adapter import VerifierAdapter
from backend.app.orchestration.artifacts.artifact_manager import ArtifactManager
from backend.app.orchestration.artifacts.storage_backends import LocalArtifactStorageBackend
from backend.app.orchestration.enums import PipelineStatus, StageName
from backend.app.orchestration.errors import OrchestrationError
from backend.app.orchestration.orchestrator import ResumeGenerationOrchestrator
from backend.app.orchestration.pipeline_models import VerifyGeneratedContentOutput
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.schemas.verification import (
    Phase4RenderingOutput,
    VerificationIssue,
    VerificationItemResult,
    VerificationReport,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    SemanticVerificationStatus,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from backend.tests.orchestration.pipeline_harness import (
    FakePipelineStageRegistry,
    PipelineCase,
    _CapturingRecorderFactory,
    orchestrator_input,
)


def _verification_output(
    *,
    phase3_result,
    decision_outcome: VerificationDecisionOutcome,
    status: VerificationStatus,
    renderable: bool,
    repaired_text: str | None = None,
    degraded: bool = False,
) -> VerifyGeneratedContentOutput:
    verified_result = phase3_result.model_copy(deep=True)
    profile_id = verified_result.metadata.source_profile_id
    if repaired_text is not None and verified_result.selected_experiences:
        verified_result.selected_experiences[0].generated_bullets[0].rewritten_text = repaired_text
    fallback_action = {
        VerificationDecisionOutcome.PASS: FallbackAction.PASS_AS_IS,
        VerificationDecisionOutcome.PASS_WITH_WARNINGS: FallbackAction.MARK_NEEDS_REVIEW,
        VerificationDecisionOutcome.REPAIR_AND_PASS: FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
        VerificationDecisionOutcome.REGENERATE_TARGET: FallbackAction.REGENERATE_SPECIFIC_ITEM,
        VerificationDecisionOutcome.FAIL_CLOSED: FallbackAction.BLOCK_RENDERING,
    }[decision_outcome]
    item_status = (
        VerificationStatus.PASSED
        if decision_outcome == VerificationDecisionOutcome.PASS
        else VerificationStatus.PASSED_WITH_WARNINGS
        if decision_outcome in {
            VerificationDecisionOutcome.PASS_WITH_WARNINGS,
            VerificationDecisionOutcome.REPAIR_AND_PASS,
        }
        else VerificationStatus.FAILED
    )
    issues = []
    if decision_outcome != VerificationDecisionOutcome.PASS:
        issues.append(
            VerificationIssue(
                id=f"issue.{decision_outcome.value}.gen.bullet.1",
                category=(
                    IssueCategory.PROVENANCE_WEAK
                    if decision_outcome == VerificationDecisionOutcome.PASS_WITH_WARNINGS
                    else IssueCategory.UNSUPPORTED_CLAIM
                ),
                severity=(
                    IssueSeverity.MEDIUM
                    if decision_outcome == VerificationDecisionOutcome.PASS_WITH_WARNINGS
                    else IssueSeverity.HIGH
                ),
                message=f"verification outcome {decision_outcome.value}",
                generated_item_id="gen.bullet.1",
                validator_name="test_verification_gate",
            )
        )
    report = VerificationReport(
        verification_run_id=f"verify.{decision_outcome.value}",
        source_profile_id=profile_id,
        status=status,
        item_results=[
            VerificationItemResult(
                item_id="gen.bullet.1",
                item_type="experience_bullet",
                status=item_status,
                evidence_strength=EvidenceStrength.STRONG,
                issues=issues,
                fallback_action=fallback_action,
                decision_outcome=decision_outcome,
            )
        ],
        fallback_actions=[fallback_action],
        decision_outcome=decision_outcome,
        decision_confidence=0.82,
        renderable=renderable,
        retryable=decision_outcome == VerificationDecisionOutcome.REGENERATE_TARGET,
    )
    if degraded:
        report.semantic_verification.enabled = True
        report.semantic_verification.status = SemanticVerificationStatus.DEGRADED
        report.semantic_verification.required_item_ids = ["gen.bullet.1"]
        report.semantic_verification.degraded_item_ids = ["gen.bullet.1"]
        report.semantic_verification.messages = ["semantic verifier unavailable"]
    if repaired_text is not None:
        report.repair_audit.repaired_item_ids = ["gen.bullet.1"]
    return VerifyGeneratedContentOutput(
        verification_run_id=report.verification_run_id,
        verification_report=report,
        rendering_output=Phase4RenderingOutput(
            source_profile_id=profile_id,
            verified_result=verified_result,
            verification_report=report,
            renderable=renderable,
            fallback_action=fallback_action,
        ),
    )


class _FakeVerificationOrchestrator:
    def __init__(self, output_builder) -> None:
        self._output_builder = output_builder

    def run(self, verification_input, **_kwargs):
        stage_output = self._output_builder(verification_input.phase3_result)
        return SimpleNamespace(
            verification_run_id=stage_output.verification_run_id,
            report=stage_output.verification_report,
            rendering_output=stage_output.rendering_output,
        )


class _VerificationGateRegistry(FakePipelineStageRegistry):
    def __init__(
        self,
        case: PipelineCase,
        *,
        verifier_adapter: VerifierAdapter,
    ) -> None:
        super().__init__(case)
        self._verifier_adapter = verifier_adapter
        self.render_inputs = []

    def execute(self, stage_name: StageName, stage_input, context):
        if stage_name == StageName.VERIFY_GENERATED_CONTENT:
            return self._verifier_adapter.execute(stage_input, context)
        if stage_name == StageName.RENDER_DETERMINISTIC_LATEX:
            self.render_inputs.append(stage_input.rendering_output)
        return super().execute(stage_name, stage_input, context)


def _run_with_adapter(tmp_path: Path, verifier_adapter: VerifierAdapter):
    recorder_factory = _CapturingRecorderFactory()
    orchestrator = ResumeGenerationOrchestrator(
        recorder_factory=recorder_factory,
        stage_registry=_VerificationGateRegistry(
            PipelineCase(
                case_id="verification_gate",
                scenario_type="strong_match",
                job_description_text="Senior Backend Engineer with Python APIs.",
            ),
            verifier_adapter=verifier_adapter,
        ),
        artifact_manager=ArtifactManager(LocalArtifactStorageBackend(tmp_path / "artifacts")),
    )
    response = orchestrator.run(
        orchestrator_input(
            run_id="run.verification-gate",
            job_description_text="Senior Backend Engineer with Python APIs.",
        )
    )
    registry = orchestrator.stage_registry
    assert isinstance(registry, _VerificationGateRegistry)
    return response, recorder_factory.recorders[0], registry


def test_phase6_gate_allows_clean_pass_to_continue(tmp_path: Path) -> None:
    adapter = VerifierAdapter(
        orchestrator_factory=lambda: _FakeVerificationOrchestrator(
            lambda phase3_result: _verification_output(
                phase3_result=phase3_result,
                decision_outcome=VerificationDecisionOutcome.PASS,
                status=VerificationStatus.PASSED,
                renderable=True,
            )
        )
    )

    response, recorder, registry = _run_with_adapter(tmp_path, adapter)

    assert response.status is PipelineStatus.SUCCEEDED
    assert len(registry.render_inputs) == 1
    assert any(
        event["message"] == "verification gate decision: pass"
        for event in recorder.stage_events
        if event["stage_name"] == StageName.VERIFY_GENERATED_CONTENT.value
    )


def test_phase6_gate_continues_with_repaired_content(tmp_path: Path) -> None:
    repaired_text = "Built Python APIs for internal workflows."
    adapter = VerifierAdapter(
        orchestrator_factory=lambda: _FakeVerificationOrchestrator(
            lambda phase3_result: _verification_output(
                phase3_result=phase3_result,
                decision_outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                renderable=True,
                repaired_text=repaired_text,
            )
        )
    )

    response, recorder, registry = _run_with_adapter(tmp_path, adapter)

    assert response.status is PipelineStatus.SUCCEEDED_WITH_WARNINGS
    assert registry.render_inputs[0].verified_result.selected_experiences[0].generated_bullets[0].rewritten_text == repaired_text
    assert any(
        event["message"] == "verification repairs applied to generated content"
        for event in recorder.stage_events
        if event["stage_name"] == StageName.VERIFY_GENERATED_CONTENT.value
    )


def test_phase6_gate_stops_before_render_on_fail_closed(tmp_path: Path) -> None:
    adapter = VerifierAdapter(
        orchestrator_factory=lambda: _FakeVerificationOrchestrator(
            lambda phase3_result: _verification_output(
                phase3_result=phase3_result,
                decision_outcome=VerificationDecisionOutcome.FAIL_CLOSED,
                status=VerificationStatus.FAILED,
                renderable=False,
            )
        )
    )

    recorder_factory = _CapturingRecorderFactory()
    registry = _VerificationGateRegistry(
        PipelineCase(
            case_id="verification_gate_fail_closed",
            scenario_type="strong_match",
            job_description_text="Senior Backend Engineer with Python APIs.",
        ),
        verifier_adapter=adapter,
    )
    orchestrator = ResumeGenerationOrchestrator(
        recorder_factory=recorder_factory,
        stage_registry=registry,
        artifact_manager=ArtifactManager(LocalArtifactStorageBackend(tmp_path / "artifacts")),
    )

    with pytest.raises(OrchestrationError):
        orchestrator.run(
            orchestrator_input(
                run_id="run.verification-gate-fail",
                job_description_text="Senior Backend Engineer with Python APIs.",
            )
        )
    assert registry.render_inputs == []


def test_phase6_gate_records_degraded_semantic_mode(tmp_path: Path) -> None:
    adapter = VerifierAdapter(
        orchestrator_factory=lambda: _FakeVerificationOrchestrator(
            lambda phase3_result: _verification_output(
                phase3_result=phase3_result,
                decision_outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                renderable=True,
                degraded=True,
            )
        )
    )

    response, recorder, _registry = _run_with_adapter(tmp_path, adapter)

    assert response.status is PipelineStatus.SUCCEEDED_WITH_WARNINGS
    assert any(
        event["message"] == "verification completed in degraded semantic mode"
        for event in recorder.stage_events
        if event["stage_name"] == StageName.VERIFY_GENERATED_CONTENT.value
    )


def test_phase6_gate_supports_targeted_regeneration_handler(tmp_path: Path) -> None:
    def recovery_handler(stage_input, stage_output, context):
        return _verification_output(
            phase3_result=stage_input.phase3_result,
            decision_outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
            status=VerificationStatus.PASSED_WITH_WARNINGS,
            renderable=True,
            repaired_text="Recovered Python API bullet.",
        )

    adapter = VerifierAdapter(
        orchestrator_factory=lambda: _FakeVerificationOrchestrator(
            lambda phase3_result: _verification_output(
                phase3_result=phase3_result,
                decision_outcome=VerificationDecisionOutcome.REGENERATE_TARGET,
                status=VerificationStatus.FAILED,
                renderable=False,
            )
        ),
        targeted_recovery_handler=recovery_handler,
    )

    response, recorder, registry = _run_with_adapter(tmp_path, adapter)

    assert response.status is PipelineStatus.SUCCEEDED_WITH_WARNINGS
    assert registry.render_inputs[0].verified_result.selected_experiences[0].generated_bullets[0].rewritten_text == "Recovered Python API bullet."
    assert any(
        event["message"] == "Targeted regeneration path executed for verification gate."
        for event in recorder.stage_events
        if event["stage_name"] == StageName.VERIFY_GENERATED_CONTENT.value
    )
