from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.schemas.verification import (
    VerificationIssue,
    VerificationItemResult,
    VerificationRepairRecord,
    VerificationReport,
)
from backend.app.services.verification.audit_artifact import (
    VERIFICATION_AUDIT_ARTIFACT_SCHEMA_VERSION,
    build_verification_audit_artifact,
    render_verification_audit_summary,
    serialize_verification_audit_artifact,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    RepairExecutionStatus,
    VerificationDecisionOutcome,
    VerificationStatus,
)


def _report() -> VerificationReport:
    issue = VerificationIssue(
        id="issue.metric.summary",
        category=IssueCategory.UNSUPPORTED_METRIC,
        severity=IssueSeverity.HIGH,
        message="unsupported metric",
        generated_item_id="summary",
        source_item_ids=["exp.1"],
        source_bullet_ids=["bullet.1"],
        validator_name="numeric_claim_validator",
    )
    item = VerificationItemResult(
        item_id="summary",
        item_type="summary",
        status=VerificationStatus.PASSED_WITH_WARNINGS,
        evidence_strength=EvidenceStrength.WEAK,
        issues=[issue],
        fallback_action=FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
        decision_outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
        decision_confidence=0.63,
    )
    report = VerificationReport(
        verification_run_id="verify.audit",
        source_profile_id="profile.audit",
        status=VerificationStatus.PASSED_WITH_WARNINGS,
        item_results=[item],
        fallback_actions=[FallbackAction.USE_SAFE_SUMMARY_FALLBACK],
        deterministic_validator_names=["numeric_claim_validator", "summary_years_experience_validator"],
        semantic_validator_names=["semantic_faithfulness_validator"],
        decision_outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
        decision_confidence=0.63,
        renderable=True,
    )
    report.semantic_verification.required_item_ids = ["summary"]
    report.semantic_verification.completed_item_ids = ["summary"]
    report.repair_audit.attempted_item_ids = ["summary"]
    report.repair_audit.repaired_item_ids = ["summary"]
    report.repair_audit.records = [
        VerificationRepairRecord(
            item_id="summary",
            item_type="summary",
            fallback_action=FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
            status=RepairExecutionStatus.APPLIED,
            strategy="rebuild_summary_from_controlled_inputs",
            repaired_text="Backend engineer with Python APIs.",
            source_item_ids=["exp.1"],
            source_bullet_ids=["bullet.1"],
        )
    ]
    return report


def test_build_verification_audit_artifact_captures_expected_summary() -> None:
    artifact = build_verification_audit_artifact(
        run_id="pipeline.audit",
        verification_timestamp=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
        report=_report(),
    )

    assert artifact.schema_version == VERIFICATION_AUDIT_ARTIFACT_SCHEMA_VERSION
    assert artifact.run_id == "pipeline.audit"
    assert artifact.verifier_coverage.semantic_coverage == 1.0
    assert artifact.final_decision is VerificationDecisionOutcome.REPAIR_AND_PASS
    assert artifact.counts_by_severity == {"high": 1}
    assert artifact.counts_by_issue_type == {"unsupported_metric": 1}
    assert artifact.repaired_item_count == 1
    assert artifact.affected_items[0].repaired is True
    assert "decision=repair_and_pass" in artifact.internal_summary


def test_verification_audit_serialization_is_stable() -> None:
    artifact = build_verification_audit_artifact(
        run_id="pipeline.audit",
        verification_timestamp=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
        report=_report(),
    )

    payload_one, canonical_one, digest_one = serialize_verification_audit_artifact(artifact)
    payload_two, canonical_two, digest_two = serialize_verification_audit_artifact(artifact)

    assert payload_one == payload_two
    assert canonical_one == canonical_two
    assert digest_one == digest_two
    assert len(digest_one) == 64


def test_render_verification_audit_summary_is_concise_and_machine_oriented() -> None:
    summary = render_verification_audit_summary(report=_report())

    assert summary.startswith("status=passed_with_warnings;")
    assert "decision=repair_and_pass" in summary
    assert "semantic_degraded=False" in summary
