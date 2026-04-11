from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.models.render_models import RenderOutputStatus
from backend.app.orchestration.confidence import InternalConfidenceLevel, assess_run_confidence
from backend.app.orchestration.enums import StageName
from backend.app.services.verification.types import SemanticVerificationStatus, VerificationDecisionOutcome
from resume_optimizer.phase2_models import Phase2Status


def _parsed(parser_confidence: float):
    return SimpleNamespace(final_analysis=SimpleNamespace(parser_confidence=parser_confidence))


def _ranked(
    *,
    status: Phase2Status = Phase2Status.SUCCESS,
    candidate_evidence_count: int = 6,
    weak_coverage_areas: list[str] | None = None,
    selected_experience_count: int = 2,
    selected_project_count: int = 1,
    selected_skill_count: int = 3,
    warnings: list[str] | None = None,
):
    diagnostics = SimpleNamespace(
        status=status,
        candidate_evidence_count=candidate_evidence_count,
        weak_coverage_areas=weak_coverage_areas or [],
        selected_experience_count=selected_experience_count,
        selected_project_count=selected_project_count,
        selected_skill_count=selected_skill_count,
        warnings=warnings or [],
    )
    return SimpleNamespace(selection_result=SimpleNamespace(diagnostics=diagnostics))


def _generated(*, severe_failure: bool = False, issue_count: int = 0, fallback_count: int = 0):
    return SimpleNamespace(
        validation_report=SimpleNamespace(
            severe_failure=severe_failure,
            issues=[object()] * issue_count,
            applied_fallbacks=[object()] * fallback_count,
        )
    )


def _verified(
    *,
    outcome: VerificationDecisionOutcome,
    confidence: float,
    renderable: bool,
    semantic_status: SemanticVerificationStatus = SemanticVerificationStatus.COMPLETED,
    repaired_item_count: int = 0,
):
    return SimpleNamespace(
        verification_report=SimpleNamespace(
            decision_outcome=outcome,
            decision_confidence=confidence,
            renderable=renderable,
            semantic_verification=SimpleNamespace(status=semantic_status),
            repair_audit=SimpleNamespace(repaired_item_ids=["item"] * repaired_item_count),
        )
    )


def _rendered(*, status: RenderOutputStatus = RenderOutputStatus.SUCCEEDED, warning_count: int = 0):
    return SimpleNamespace(
        render_output=SimpleNamespace(
            status=status,
            warnings=["warn"] * warning_count,
            diagnostics=SimpleNamespace(layout_overflow=False),
        )
    )


def _compiled(*, compile_success: bool = True, warning_count: int = 0, error_count: int = 0):
    return SimpleNamespace(
        compile_result=SimpleNamespace(
            compile_success=compile_success,
            warnings_detected=["warn"] * warning_count,
            errors_detected=["err"] * error_count,
        )
    )


def test_strong_successful_run_remains_strong() -> None:
    assessment = assess_run_confidence(
        parsed=_parsed(0.91),
        ranked=_ranked(),
        generated=_generated(),
        verified=_verified(
            outcome=VerificationDecisionOutcome.PASS,
            confidence=0.96,
            renderable=True,
        ),
        rendered=_rendered(),
        compiled=_compiled(),
        retry_attempts=[],
        fallback_audits=[],
    )

    assert assessment.final_confidence_level is InternalConfidenceLevel.STRONG
    assert not assessment.gating_reasons


def test_verification_hard_fail_is_unsafe() -> None:
    assessment = assess_run_confidence(
        parsed=_parsed(0.82),
        ranked=_ranked(),
        generated=_generated(),
        verified=_verified(
            outcome=VerificationDecisionOutcome.FAIL_CLOSED,
            confidence=0.12,
            renderable=False,
        ),
        rendered=_rendered(status=RenderOutputStatus.FAILED),
        retry_attempts=[],
        fallback_audits=[],
        terminal_failure_stage=StageName.VERIFY_GENERATED_CONTENT.value,
    )

    assert assessment.final_confidence_level is InternalConfidenceLevel.UNSAFE
    assert "verification_fail_closed" in assessment.gating_reasons


def test_weak_parse_and_weak_selection_become_degraded() -> None:
    assessment = assess_run_confidence(
        parsed=_parsed(0.42),
        ranked=_ranked(
            candidate_evidence_count=1,
            weak_coverage_areas=["backend depth", "leadership"],
            selected_experience_count=0,
            selected_project_count=1,
            selected_skill_count=0,
        ),
        generated=_generated(issue_count=2),
        verified=_verified(
            outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
            confidence=0.74,
            renderable=True,
        ),
        rendered=_rendered(),
        compiled=_compiled(),
        retry_attempts=[],
        fallback_audits=[],
    )

    assert assessment.final_confidence_level is InternalConfidenceLevel.DEGRADED
    assert "weak_parse_and_selection" in assessment.gating_reasons


def test_retries_and_fallbacks_degrade_otherwise_successful_run() -> None:
    assessment = assess_run_confidence(
        parsed=_parsed(0.86),
        ranked=_ranked(),
        generated=_generated(fallback_count=2),
        verified=_verified(
            outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
            confidence=0.7,
            renderable=True,
            semantic_status=SemanticVerificationStatus.DEGRADED,
            repaired_item_count=1,
        ),
        rendered=_rendered(status=RenderOutputStatus.PARTIAL),
        compiled=_compiled(warning_count=2),
        retry_attempts=[{"stage_name": "parse"}, {"stage_name": "verify"}],
        fallback_audits=[
            {"fallback_class": "use_deterministic_parse_signals", "final_output_downgraded": True},
            {"fallback_class": "reduce_summary_to_safe_short_form", "final_output_downgraded": True},
            {"fallback_class": "drop_low_priority_section", "final_output_downgraded": True},
        ],
    )

    assert assessment.final_confidence_level is InternalConfidenceLevel.DEGRADED
    assert "repeated_retries" in assessment.gating_reasons
    assert "excessive_fallback_usage" in assessment.gating_reasons
