from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.schemas.verification import SemanticVerificationAudit, VerificationIssue
from backend.app.services.verification.decision_engine import VerificationDecisionEngine
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    VerificationDecisionOutcome,
    VerificationStatus,
)


def _issue(
    *,
    category: IssueCategory,
    severity: IssueSeverity,
    item_id: str = "item.1",
) -> VerificationIssue:
    return VerificationIssue(
        id=f"issue.{category.value}.{item_id}",
        category=category,
        severity=severity,
        message=f"{category.value} detected",
        generated_item_id=item_id,
        validator_name="test_validator",
    )


def test_decide_item_returns_pass_when_clean() -> None:
    engine = VerificationDecisionEngine()

    decision = engine.decide_item(
        item_id="summary",
        item_type="summary",
        issues=[],
        evidence_strength=EvidenceStrength.STRONG,
    )

    assert decision.status is VerificationStatus.PASSED
    assert decision.outcome is VerificationDecisionOutcome.PASS
    assert decision.fallback_action is FallbackAction.PASS_AS_IS


def test_medium_bullet_issue_repairs_with_source_fallback() -> None:
    engine = VerificationDecisionEngine()

    decision = engine.decide_item(
        item_id="gen.bullet.1",
        item_type="experience_bullet",
        issues=[_issue(category=IssueCategory.UNSUPPORTED_KEYWORD, severity=IssueSeverity.MEDIUM, item_id="gen.bullet.1")],
        evidence_strength=EvidenceStrength.STRONG,
    )

    assert decision.outcome is VerificationDecisionOutcome.REPAIR_AND_PASS
    assert decision.fallback_action is FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET


def test_high_summary_issue_prefers_safe_summary_fallback() -> None:
    engine = VerificationDecisionEngine()

    decision = engine.decide_item(
        item_id="summary",
        item_type="summary",
        issues=[_issue(category=IssueCategory.UNSUPPORTED_SCOPE, severity=IssueSeverity.HIGH, item_id="summary")],
        evidence_strength=EvidenceStrength.MODERATE,
    )

    assert decision.status is VerificationStatus.FAILED
    assert decision.outcome is VerificationDecisionOutcome.REPAIR_AND_PASS
    assert decision.fallback_action is FallbackAction.USE_SAFE_SUMMARY_FALLBACK


def test_critical_semantic_degradation_fails_closed_without_safe_fallback() -> None:
    engine = VerificationDecisionEngine()

    decision = engine.decide_item(
        item_id="summary",
        item_type="summary",
        issues=[
            _issue(
                category=IssueCategory.SEMANTIC_VERIFICATION_UNAVAILABLE,
                severity=IssueSeverity.CRITICAL,
                item_id="summary",
            )
        ],
        evidence_strength=EvidenceStrength.NONE,
    )

    assert decision.status is VerificationStatus.BLOCKED
    assert decision.outcome is VerificationDecisionOutcome.FAIL_CLOSED
    assert decision.fallback_action is FallbackAction.BLOCK_RENDERING


def test_multiple_medium_issues_in_same_section_escalate_run_to_regeneration() -> None:
    engine = VerificationDecisionEngine()
    item_one = engine.decide_item(
        item_id="gen.bullet.1",
        item_type="experience_bullet",
        issues=[_issue(category=IssueCategory.UNSUPPORTED_KEYWORD, severity=IssueSeverity.MEDIUM, item_id="gen.bullet.1")],
        evidence_strength=EvidenceStrength.STRONG,
    )
    item_two = engine.decide_item(
        item_id="gen.bullet.2",
        item_type="experience_bullet",
        issues=[_issue(category=IssueCategory.PROVENANCE_WEAK, severity=IssueSeverity.MEDIUM, item_id="gen.bullet.2")],
        evidence_strength=EvidenceStrength.MODERATE,
    )

    run = engine.decide_run(
        item_decisions=[item_one, item_two],
        semantic_audit=SemanticVerificationAudit(enabled=True, required_item_ids=["gen.bullet.1", "gen.bullet.2"], completed_item_ids=["gen.bullet.1", "gen.bullet.2"]),
    )

    assert run.status is VerificationStatus.FAILED
    assert run.outcome is VerificationDecisionOutcome.REGENERATE_TARGET
    assert run.renderable is False
    assert "multiple_medium_issues_in_experience" in run.audit.reasons


def test_degraded_semantic_coverage_lowers_confidence_and_stays_auditable() -> None:
    engine = VerificationDecisionEngine()
    item = engine.decide_item(
        item_id="gen.bullet.1",
        item_type="experience_bullet",
        issues=[
            _issue(
                category=IssueCategory.SEMANTIC_VERIFICATION_UNAVAILABLE,
                severity=IssueSeverity.MEDIUM,
                item_id="gen.bullet.1",
            )
        ],
        evidence_strength=EvidenceStrength.STRONG,
    )

    run = engine.decide_run(
        item_decisions=[item],
        semantic_audit=SemanticVerificationAudit(
            enabled=True,
            required_item_ids=["gen.bullet.1"],
            attempted_item_ids=["gen.bullet.1"],
            degraded_item_ids=["gen.bullet.1"],
            messages=["semantic verifier unavailable"],
        ),
    )

    assert run.outcome is VerificationDecisionOutcome.PASS_WITH_WARNINGS
    assert run.audit.degraded_semantic is True
    assert run.audit.semantic_coverage == 0.0
    assert run.confidence < item.confidence
