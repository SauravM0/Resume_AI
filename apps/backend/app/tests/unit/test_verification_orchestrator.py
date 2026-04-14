from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.schemas.verification import Phase3VerificationInput, VerificationIssue
from backend.app.services.verification.orchestrator import (
    SemanticVerificationPolicy,
    VerificationOrchestrator,
    build_default_verification_orchestrator,
)
from backend.app.services.verification.semantic_validator import (
    SemanticCheckResponse,
    SemanticValidationError,
    SemanticValidationResult,
    SemanticVerdict,
)
from backend.app.services.verification.types import (
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    VerificationDecisionOutcome,
    SemanticVerificationStatus,
    SemanticVerifierUnavailableBehavior,
    VerificationStatus,
)
from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.models import (
    BulletEntry,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    PersonalProfile,
)
from resume_optimizer.phase3_models import (
    BulletRewriteStrategy,
    GeneratedBullet,
    GeneratedExperience,
    GeneratedSummary,
    GenerationMetadata,
    Phase3GenerationPayload,
    Phase3GenerationResult,
    Phase3RoleContext,
    Phase3ValidationMetadata,
    SourceReference,
    SupportLevel,
)


class _FakeSemanticValidator:
    def __init__(self, verdict: SemanticVerdict = SemanticVerdict.PASS) -> None:
        self.verdict = verdict
        self.calls = 0

    def validate_item(self, validation_input):
        self.calls += 1
        if self.verdict == SemanticVerdict.WEAK_SUPPORT:
            response = SemanticCheckResponse(
                verdict=SemanticVerdict.WEAK_SUPPORT,
                confidence=0.61,
                issue_category=IssueCategory.PROVENANCE_WEAK,
                explanation="Summary support is weak and should be reviewed.",
                overclaim_dimensions=["summary_overreach"],
            )
        else:
            response = SemanticCheckResponse(
                verdict=SemanticVerdict.PASS,
                confidence=0.95,
                issue_category=None,
                explanation="Generated statement is faithful.",
                overclaim_dimensions=[],
            )
        return SemanticValidationResult(
            item_id=validation_input.item_id,
            response=response,
            issues=[] if response.verdict == SemanticVerdict.PASS else [
                VerificationIssue(
                    id=f"issue.semantic_faithfulness.{validation_input.item_id}",
                    category=IssueCategory.PROVENANCE_WEAK,
                    severity=IssueSeverity.MEDIUM,
                    message=response.explanation,
                    generated_item_id=validation_input.item_id,
                    source_item_ids=["exp.platform"],
                    source_bullet_ids=["bullet.platform.1"],
                    validator_name="semantic_faithfulness_validator",
                )
            ],
        )


class _FailingSemanticValidator:
    def validate_item(self, _validation_input):
        raise SemanticValidationError("semantic service unavailable")


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile.orchestrator",
        personal_profile=PersonalProfile(id="personal.orchestrator", full_name="Alex Orchestrator"),
        experience=[
            ExperienceEntry(
                id="exp.platform",
                organization="Acme",
                title="Backend Engineer",
                start_date={"raw_value": "2021-01"},
                tools=["Python"],
                bullets=[
                    BulletEntry(
                        id="bullet.platform.1",
                        text="Implemented Python APIs that reduced latency by 25%.",
                        tools=["Python"],
                    )
                ],
            )
        ],
    )


def _phase3_result(*, generated_bullet_text: str, include_summary: bool = False) -> Phase3GenerationResult:
    summary = (
        GeneratedSummary(
            text="Backend engineer with Python API experience.",
            source_item_ids=["exp.platform"],
            source_bullet_ids=["bullet.platform.1"],
            provenance=[
                SourceReference(
                    source_item_id="exp.platform",
                    source_item_type=ItemType.EXPERIENCE,
                    source_bullet_id="bullet.platform.1",
                    support_level=SupportLevel.SYNTHESIZED,
                )
            ],
            support_level=SupportLevel.SYNTHESIZED,
        )
        if include_summary
        else None
    )
    return Phase3GenerationResult(
        summary=summary,
        selected_experiences=[
            GeneratedExperience(
                source_item_id="exp.platform",
                organization="Acme",
                title="Backend Engineer",
                start_date={"raw_value": "2021-01"},
                generated_bullets=[
                    GeneratedBullet(
                        id="gen.bullet.1",
                        source_item_id="exp.platform",
                        source_item_type=ItemType.EXPERIENCE,
                        source_bullet_ids=["bullet.platform.1"],
                        rewritten_text=generated_bullet_text,
                        rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
                        provenance=[
                            SourceReference(
                                source_item_id="exp.platform",
                                source_item_type=ItemType.EXPERIENCE,
                                source_bullet_id="bullet.platform.1",
                                support_level=SupportLevel.DIRECT,
                            )
                        ],
                        support_level=SupportLevel.DIRECT,
                    )
                ],
                support_level=SupportLevel.DIRECT,
            )
        ],
        metadata=GenerationMetadata(source_profile_id="profile.orchestrator"),
    )


def _verification_input(*, generated_bullet_text: str, include_summary: bool = False) -> Phase3VerificationInput:
    profile = _profile()
    return Phase3VerificationInput(
        source_profile_id=profile.id,
        job_analysis=NormalizedJobAnalysis(
            role_type="individual_contributor",
            seniority_level="senior",
            technical_skills=["Python"],
        ),
        source_profile=profile,
        generation_payload=Phase3GenerationPayload(
            role_context=Phase3RoleContext(target_role_title="Backend Engineer"),
            validation_metadata=Phase3ValidationMetadata(profile_id=profile.id),
        ),
        phase3_result=_phase3_result(
            generated_bullet_text=generated_bullet_text,
            include_summary=include_summary,
        ),
    )


def test_clean_run_passes_as_is_and_runs_semantic_for_required_bullet() -> None:
    semantic = _FakeSemanticValidator()
    result = VerificationOrchestrator(semantic_validator=semantic).run(
        _verification_input(
            generated_bullet_text="Implemented Python APIs that reduced latency by 25%."
        ),
        verification_run_id="verify.clean",
    )

    assert result.report.status is VerificationStatus.PASSED
    assert result.report.renderable is True
    assert result.report.decision_outcome is VerificationDecisionOutcome.PASS
    assert result.report.item_results[0].fallback_action is FallbackAction.PASS_AS_IS
    assert semantic.calls == 1
    assert result.report.semantic_verification.completed_item_ids == ["gen.bullet.1"]


def test_unsupported_numeric_bullet_fails_item_but_run_can_pass_with_source_fallback() -> None:
    semantic = _FakeSemanticValidator()
    result = VerificationOrchestrator(semantic_validator=semantic).run(
        _verification_input(
            generated_bullet_text="Implemented Python APIs that reduced latency by 40%."
        ),
        verification_run_id="verify.numeric",
    )

    item = result.report.item_results[0]
    assert item.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert item.fallback_action is FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET
    assert item.decision_outcome is VerificationDecisionOutcome.REPAIR_AND_PASS
    assert item.issues[0].category is IssueCategory.UNSUPPORTED_METRIC
    assert result.report.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert result.report.decision_outcome is VerificationDecisionOutcome.REPAIR_AND_PASS
    assert result.report.repair_audit.repaired_item_ids == ["gen.bullet.1"]
    assert result.report.repair_audit.records[0].strategy == "fallback_to_source_bullet"
    assert (
        result.rendering_output.verified_result.selected_experiences[0].generated_bullets[0].rewritten_text
        == "Implemented Python APIs that reduced latency by 25%."
    )
    assert result.rendering_output.renderable is True
    assert semantic.calls == 1


def test_unsafe_summary_is_rebuilt_to_safe_fallback() -> None:
    semantic = _FakeSemanticValidator()
    verification_input = _verification_input(
        generated_bullet_text="Implemented Python APIs that reduced latency by 25%.",
        include_summary=True,
    )
    verification_input.phase3_result.summary = verification_input.phase3_result.summary.model_copy(
        update={"text": "Principal full-stack engineer with 15 years of distributed systems leadership."}
    )

    result = VerificationOrchestrator(semantic_validator=semantic).run(
        verification_input,
        verification_run_id="verify.summary.repair",
    )

    summary = next(item for item in result.report.item_results if item.item_type == "summary")
    assert summary.fallback_action is FallbackAction.USE_SAFE_SUMMARY_FALLBACK
    assert result.report.repair_audit.repaired_item_ids == ["summary"]
    assert result.report.repair_audit.records[0].strategy == "rebuild_summary_from_controlled_inputs"
    assert result.rendering_output.verified_result.summary is not None
    assert result.rendering_output.verified_result.summary.text != "Principal full-stack engineer with 15 years of distributed systems leadership."


def test_weak_summary_semantic_result_marks_run_for_review() -> None:
    semantic = _FakeSemanticValidator(SemanticVerdict.WEAK_SUPPORT)
    result = VerificationOrchestrator(semantic_validator=semantic).run(
        _verification_input(
            generated_bullet_text="Implemented Python APIs that reduced latency by 25%.",
            include_summary=True,
        ),
        verification_run_id="verify.summary",
    )

    summary = next(item for item in result.report.item_results if item.item_type == "summary")
    assert summary.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert summary.fallback_action is FallbackAction.MARK_NEEDS_REVIEW
    assert summary.decision_outcome is VerificationDecisionOutcome.PASS_WITH_WARNINGS
    assert result.report.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert result.rendering_output.fallback_action is FallbackAction.MARK_NEEDS_REVIEW
    assert semantic.calls == 2
    assert result.report.semantic_verification.status is SemanticVerificationStatus.COMPLETED


def test_default_builder_injects_semantic_validator_for_bullets_and_summary(monkeypatch) -> None:
    semantic = _FakeSemanticValidator()
    monkeypatch.setattr(
        "backend.app.services.verification.orchestrator.build_default_semantic_validator",
        lambda: semantic,
    )
    monkeypatch.setattr(
        "backend.app.services.verification.orchestrator.build_default_semantic_verification_policy",
        lambda: SemanticVerificationPolicy(
            enabled=True,
            strict_mode=True,
            fallback_behavior=SemanticVerifierUnavailableBehavior.BLOCK,
        ),
    )

    orchestrator = build_default_verification_orchestrator()
    result = orchestrator.run(
        _verification_input(
            generated_bullet_text="Implemented Python APIs that reduced latency by 25%.",
            include_summary=True,
        ),
        verification_run_id="verify.default-builder",
    )

    assert result.report.status is VerificationStatus.PASSED
    assert semantic.calls == 2
    assert result.report.semantic_verification.status is SemanticVerificationStatus.COMPLETED
    assert set(result.report.semantic_verification.completed_item_ids) == {"gen.bullet.1", "summary"}


def test_semantic_unavailability_can_degrade_explicitly_when_configured() -> None:
    result = VerificationOrchestrator(
        semantic_validator=_FailingSemanticValidator(),
        semantic_policy=SemanticVerificationPolicy(
            enabled=True,
            strict_mode=False,
            fallback_behavior=SemanticVerifierUnavailableBehavior.MARK_NEEDS_REVIEW,
        ),
    ).run(
        _verification_input(
            generated_bullet_text="Implemented Python APIs that reduced latency by 25%."
        ),
        verification_run_id="verify.degraded",
    )

    item = result.report.item_results[0]
    assert item.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert item.fallback_action is FallbackAction.MARK_NEEDS_REVIEW
    assert item.issues[-1].category is IssueCategory.SEMANTIC_VERIFICATION_UNAVAILABLE
    assert result.report.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert result.report.semantic_verification.status is SemanticVerificationStatus.DEGRADED
    assert result.report.semantic_verification.degraded_item_ids == ["gen.bullet.1"]
    assert result.report.repair_audit.records == []
    assert "semantic service unavailable" in result.report.semantic_verification.messages[0]
