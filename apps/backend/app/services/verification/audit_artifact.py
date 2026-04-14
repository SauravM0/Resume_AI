"""Stable Phase 6 verification audit artifact builder and serializer."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
import json

from pydantic import Field

from backend.app.schemas.verification import VerificationReport
from backend.app.services.verification.types import (
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.models import NonEmptyStr, ScoreValue, StableId, StrictModel

VERIFICATION_AUDIT_ARTIFACT_SCHEMA_VERSION = "phase6.verification.audit.v1"


class VerificationCoverageSummary(StrictModel):
    """Summary of which verification layers executed and how completely."""

    deterministic_validator_names: list[NonEmptyStr] = Field(default_factory=list)
    semantic_validator_names: list[NonEmptyStr] = Field(default_factory=list)
    semantic_required_count: int = 0
    semantic_completed_count: int = 0
    semantic_degraded_count: int = 0
    semantic_coverage: ScoreValue = 1.0


class VerificationItemAuditSummary(StrictModel):
    """Compact per-item decision summary for internal review."""

    item_id: StableId
    item_type: NonEmptyStr
    status: VerificationStatus
    decision_outcome: VerificationDecisionOutcome
    issue_categories: list[NonEmptyStr] = Field(default_factory=list)
    affected_source_item_ids: list[StableId] = Field(default_factory=list)
    affected_source_bullet_ids: list[StableId] = Field(default_factory=list)
    repaired: bool = False
    blocked: bool = False
    passed: bool = False
    requires_regeneration: bool = False


class VerificationAuditArtifact(StrictModel):
    """Machine-readable audit artifact for one Phase 6 verification run."""

    schema_version: NonEmptyStr = VERIFICATION_AUDIT_ARTIFACT_SCHEMA_VERSION
    run_id: StableId
    verification_run_id: StableId
    verification_timestamp: datetime
    verification_status: VerificationStatus
    final_decision: VerificationDecisionOutcome
    final_confidence: ScoreValue
    renderable: bool
    degraded_mode: bool = False
    verifier_coverage: VerificationCoverageSummary
    passed_checks: list[NonEmptyStr] = Field(default_factory=list)
    issue_count: int = 0
    issues: list[dict[str, object]] = Field(default_factory=list)
    counts_by_severity: dict[NonEmptyStr, int] = Field(default_factory=dict)
    counts_by_issue_type: dict[NonEmptyStr, int] = Field(default_factory=dict)
    affected_items: list[VerificationItemAuditSummary] = Field(default_factory=list)
    fallback_repairs: list[dict[str, object]] = Field(default_factory=list)
    blocked_item_count: int = 0
    repaired_item_count: int = 0
    passed_item_count: int = 0
    requires_regeneration_item_count: int = 0
    internal_summary: NonEmptyStr


def build_verification_audit_artifact(
    *,
    run_id: str,
    verification_timestamp: datetime,
    report: VerificationReport,
) -> VerificationAuditArtifact:
    """Build a concise, structured audit artifact from the verification report."""

    issue_summaries: list[dict[str, object]] = []
    severity_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    passed_checks = sorted(
        {
            *report.deterministic_validator_names,
            *report.semantic_validator_names,
        }
        - {issue.validator_name for item in report.item_results for issue in item.issues}
    )
    affected_items: list[VerificationItemAuditSummary] = []
    for item in report.item_results:
        item_categories = [issue.category.value for issue in item.issues]
        source_item_ids = sorted({source_id for issue in item.issues for source_id in issue.source_item_ids})
        source_bullet_ids = sorted({bullet_id for issue in item.issues for bullet_id in issue.source_bullet_ids})
        affected_items.append(
            VerificationItemAuditSummary(
                item_id=item.item_id,
                item_type=item.item_type,
                status=item.status,
                decision_outcome=item.decision_outcome,
                issue_categories=item_categories,
                affected_source_item_ids=source_item_ids,
                affected_source_bullet_ids=source_bullet_ids,
                repaired=item.item_id in report.repair_audit.repaired_item_ids,
                blocked=item.status == VerificationStatus.BLOCKED,
                passed=item.status in {VerificationStatus.PASSED, VerificationStatus.PASSED_WITH_WARNINGS},
                requires_regeneration=item.item_id in report.repair_audit.requires_regeneration_item_ids
                or item.decision_outcome == VerificationDecisionOutcome.REGENERATE_TARGET,
            )
        )
        for issue in item.issues:
            severity_counts[issue.severity.value] += 1
            type_counts[issue.category.value] += 1
            issue_summaries.append(
                {
                    "item_id": item.item_id,
                    "item_type": item.item_type,
                    "category": issue.category.value,
                    "severity": issue.severity.value,
                    "validator_name": issue.validator_name,
                    "source_item_ids": list(issue.source_item_ids),
                    "source_bullet_ids": list(issue.source_bullet_ids),
                }
            )

    required = len(report.semantic_verification.required_item_ids)
    completed = len(report.semantic_verification.completed_item_ids)
    semantic_coverage = round(completed / required, 4) if required else 1.0
    fallback_repairs = [
        {
            "item_id": record.item_id,
            "item_type": record.item_type,
            "fallback_action": record.fallback_action.value,
            "status": record.status.value,
            "strategy": record.strategy,
            "removed_fragments": list(record.removed_fragments),
            "requires_regeneration": record.requires_regeneration,
            "source_item_ids": list(record.source_item_ids),
            "source_bullet_ids": list(record.source_bullet_ids),
        }
        for record in report.repair_audit.records
    ]
    return VerificationAuditArtifact(
        run_id=run_id,
        verification_run_id=report.verification_run_id,
        verification_timestamp=verification_timestamp,
        verification_status=report.status,
        final_decision=report.decision_outcome,
        final_confidence=report.decision_confidence,
        renderable=report.renderable,
        degraded_mode=bool(report.semantic_verification.degraded_item_ids),
        verifier_coverage=VerificationCoverageSummary(
            deterministic_validator_names=report.deterministic_validator_names,
            semantic_validator_names=report.semantic_validator_names,
            semantic_required_count=required,
            semantic_completed_count=completed,
            semantic_degraded_count=len(report.semantic_verification.degraded_item_ids),
            semantic_coverage=semantic_coverage,
        ),
        passed_checks=passed_checks,
        issue_count=sum(len(item.issues) for item in report.item_results),
        issues=issue_summaries,
        counts_by_severity={key: severity_counts[key] for key in sorted(severity_counts)},
        counts_by_issue_type={key: type_counts[key] for key in sorted(type_counts)},
        affected_items=affected_items,
        fallback_repairs=fallback_repairs,
        blocked_item_count=sum(1 for item in affected_items if item.blocked),
        repaired_item_count=len(report.repair_audit.repaired_item_ids),
        passed_item_count=sum(1 for item in affected_items if item.passed),
        requires_regeneration_item_count=len(report.repair_audit.requires_regeneration_item_ids),
        internal_summary=render_verification_audit_summary(
            report=report,
            severity_counts=severity_counts,
            type_counts=type_counts,
        ),
    )


def render_verification_audit_summary(
    *,
    report: VerificationReport,
    severity_counts: Counter[str] | None = None,
    type_counts: Counter[str] | None = None,
) -> str:
    """Render a concise internal summary line from the verification artifact."""

    severity_counts = severity_counts or Counter(
        issue.severity.value for item in report.item_results for issue in item.issues
    )
    type_counts = type_counts or Counter(
        issue.category.value for item in report.item_results for issue in item.issues
    )
    top_issue = next(iter(sorted(type_counts))) if type_counts else "none"
    return (
        f"status={report.status.value}; decision={report.decision_outcome.value}; "
        f"confidence={report.decision_confidence:.4f}; issues={sum(type_counts.values())}; "
        f"top_issue={top_issue}; repaired={len(report.repair_audit.repaired_item_ids)}; "
        f"blocked={sum(1 for item in report.item_results if item.status == VerificationStatus.BLOCKED)}; "
        f"semantic_degraded={bool(report.semantic_verification.degraded_item_ids)}"
    )


def serialize_verification_audit_artifact(
    artifact: VerificationAuditArtifact,
) -> tuple[dict[str, object], str, str]:
    """Return stable JSON payload, canonical string, and sha256 hash."""

    payload = artifact.model_dump(mode="json", exclude_none=True)
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return payload, canonical_json, sha256(canonical_json.encode("utf-8")).hexdigest()
