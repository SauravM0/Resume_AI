"""Repository for durable Phase 6 verification persistence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.provenance_link import ProvenanceLinkModel
from backend.app.db.models.verification_issue import VerificationIssueModel
from backend.app.db.models.verification_item import VerificationItemModel
from backend.app.db.models.verification_run import VerificationRunModel
from backend.app.schemas.verification import (
    ProvenanceLink,
    VerificationDecisionAudit,
    VerificationRepairAudit,
    SemanticVerificationAudit,
    VerificationIssue,
    VerificationItemResult,
    VerificationReport,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    ProvenanceRelationType,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.models import ItemType, ScoreValue


@dataclass(frozen=True, slots=True)
class VerificationIssueCreate:
    """Input payload for persisting an item-level verification issue."""

    category: IssueCategory
    severity: IssueSeverity
    message: str
    source_span_json: dict[str, Any] | None = None
    generated_span_json: dict[str, Any] | None = None
    details_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProvenanceLinkCreate:
    """Input payload for persisting a provenance link for a generated item."""

    source_entity_type: ItemType
    source_entity_id: str
    relation_type: ProvenanceRelationType | str
    evidence_strength: EvidenceStrength
    source_bullet_id: str | None = None
    matched_tokens_json: list[str] = field(default_factory=list)


class VerificationRepository:
    """Persistence API for verification runs, items, issues, and provenance."""

    def __init__(self, session: Session) -> None:
        """Create a repository bound to a SQLAlchemy session."""

        self.session = session

    def create_verification_run(
        self,
        *,
        generation_id: str | None = None,
        pipeline_run_id: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        jd_hash: str | None = None,
        status: VerificationStatus = VerificationStatus.PENDING,
        overall_score: ScoreValue | None = None,
        fallback_applied: bool = False,
        summary_status: VerificationStatus | None = None,
        raw_artifact_refs: dict[str, Any] | None = None,
    ) -> VerificationRunModel:
        """Create and flush a verification run aggregate record."""

        run = VerificationRunModel(
            generation_id=generation_id,
            pipeline_run_id=pipeline_run_id,
            candidate_id=candidate_id,
            job_id=job_id,
            jd_hash=jd_hash,
            status=status.value,
            overall_score=overall_score,
            fallback_applied=fallback_applied,
            summary_status=summary_status.value if summary_status is not None else None,
            raw_artifact_refs=raw_artifact_refs or {},
        )
        self.session.add(run)
        self.session.flush()
        return run

    def add_verification_item(
        self,
        *,
        verification_run_id: str,
        item_type: str,
        item_key: str,
        generated_text: str,
        status: VerificationStatus,
        confidence: ScoreValue | None = None,
        fallback_action: FallbackAction = FallbackAction.ACCEPT,
        evidence_strength: EvidenceStrength = EvidenceStrength.WEAK,
    ) -> VerificationItemModel:
        """Create and flush a generated item verification result."""

        item = VerificationItemModel(
            verification_run_id=verification_run_id,
            item_type=item_type,
            item_key=item_key,
            generated_text=generated_text,
            status=status.value,
            confidence=confidence,
            fallback_action=fallback_action.value,
            evidence_strength=evidence_strength.value,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def add_issues(
        self,
        *,
        verification_item_id: str,
        issues: Sequence[VerificationIssueCreate],
    ) -> list[VerificationIssueModel]:
        """Persist one or more verification issues for an item."""

        issue_rows = [
            VerificationIssueModel(
                verification_item_id=verification_item_id,
                category=issue.category.value,
                severity=issue.severity.value,
                message=issue.message,
                source_span_json=issue.source_span_json,
                generated_span_json=issue.generated_span_json,
                details_json=issue.details_json,
            )
            for issue in issues
        ]
        self.session.add_all(issue_rows)
        self.session.flush()
        return issue_rows

    def add_provenance_links(
        self,
        *,
        verification_item_id: str,
        links: Sequence[ProvenanceLinkCreate],
    ) -> list[ProvenanceLinkModel]:
        """Persist one or more provenance links for an item."""

        link_rows = [
            ProvenanceLinkModel(
                verification_item_id=verification_item_id,
                source_entity_type=link.source_entity_type.value,
                source_entity_id=link.source_entity_id,
                source_bullet_id=link.source_bullet_id,
                relation_type=(
                    link.relation_type.value
                    if isinstance(link.relation_type, ProvenanceRelationType)
                    else link.relation_type
                ),
                evidence_strength=link.evidence_strength.value,
                matched_tokens_json=link.matched_tokens_json,
            )
            for link in links
        ]
        self.session.add_all(link_rows)
        self.session.flush()
        return link_rows

    def finalize_run(
        self,
        *,
        verification_run_id: str,
        status: VerificationStatus,
        overall_score: ScoreValue | None = None,
        fallback_applied: bool | None = None,
        summary_status: VerificationStatus | None = None,
        finished_at: datetime | None = None,
        raw_artifact_refs_update: dict[str, Any] | None = None,
    ) -> VerificationRunModel:
        """Mark a verification run finished and update aggregate fields."""

        run = self._get_run_or_raise(verification_run_id)
        run.status = status.value
        run.finished_at = finished_at or datetime.now(timezone.utc)
        if overall_score is not None:
            run.overall_score = overall_score
        if fallback_applied is not None:
            run.fallback_applied = fallback_applied
        if summary_status is not None:
            run.summary_status = summary_status.value
        if raw_artifact_refs_update:
            run.raw_artifact_refs = {
                **(run.raw_artifact_refs or {}),
                **raw_artifact_refs_update,
            }
        self.session.flush()
        return run

    def fetch_report_by_run_id(self, verification_run_id: str) -> VerificationReport | None:
        """Fetch a verification run and return the API-facing report contract."""

        run = self.session.scalar(
            select(VerificationRunModel)
            .where(VerificationRunModel.id == verification_run_id)
            .options(
                selectinload(VerificationRunModel.items).selectinload(
                    VerificationItemModel.issues
                ),
                selectinload(VerificationRunModel.items).selectinload(
                    VerificationItemModel.provenance_links
                ),
            )
        )
        if run is None:
            return None

        fallback_actions = sorted(
            {FallbackAction(item.fallback_action) for item in run.items},
            key=lambda action: action.value,
        )
        decision_audit_payload = (run.raw_artifact_refs or {}).get("decision_audit")
        decision_audit = (
            VerificationDecisionAudit.model_validate(decision_audit_payload)
            if decision_audit_payload
            else VerificationDecisionAudit(
                outcome=self._run_decision_outcome(VerificationStatus(run.status), fallback_actions),
                confidence=float(run.overall_score or 0),
            )
        )
        return VerificationReport(
            verification_run_id=run.id,
            source_profile_id=run.candidate_id or "unknown.candidate",
            status=VerificationStatus(run.status),
            item_results=[self._to_item_result(item) for item in run.items],
            fallback_actions=fallback_actions,
            semantic_verification=SemanticVerificationAudit.model_validate(
                (run.raw_artifact_refs or {}).get("semantic_verification", {})
            ),
            decision_outcome=decision_audit.outcome,
            decision_confidence=decision_audit.confidence,
            decision_audit=decision_audit,
            repair_audit=VerificationRepairAudit.model_validate(
                (run.raw_artifact_refs or {}).get("repair_audit", {})
            ),
            renderable=VerificationStatus(run.status)
            in {VerificationStatus.PASSED, VerificationStatus.PASSED_WITH_WARNINGS},
            retryable=VerificationStatus(run.status) == VerificationStatus.NEEDS_RETRY,
        )

    def _get_run_or_raise(self, verification_run_id: str) -> VerificationRunModel:
        """Return a run by id or raise a ValueError for invalid repository usage."""

        run = self.session.get(VerificationRunModel, verification_run_id)
        if run is None:
            raise ValueError(f"verification run not found: {verification_run_id}")
        return run

    def _to_item_result(self, item: VerificationItemModel) -> VerificationItemResult:
        """Convert an ORM item row into the verification report item contract."""

        return VerificationItemResult(
            item_id=item.item_key,
            item_type=item.item_type,
            status=VerificationStatus(item.status),
            evidence_strength=EvidenceStrength(item.evidence_strength),
            provenance=[self._to_provenance_link(link) for link in item.provenance_links],
            issues=[self._to_issue(issue, item.item_key) for issue in item.issues],
            fallback_action=FallbackAction(item.fallback_action),
            decision_outcome=self._item_decision_outcome(
                status=VerificationStatus(item.status),
                fallback_action=FallbackAction(item.fallback_action),
            ),
            decision_confidence=float(item.confidence) if item.confidence is not None else 1.0,
            retryable=VerificationStatus(item.status) == VerificationStatus.NEEDS_RETRY,
        )

    def _item_decision_outcome(
        self,
        *,
        status: VerificationStatus,
        fallback_action: FallbackAction,
    ) -> VerificationDecisionOutcome:
        """Backfill item decision outcome when only legacy item rows are persisted."""

        if status == VerificationStatus.PASSED:
            return VerificationDecisionOutcome.PASS
        if status == VerificationStatus.PASSED_WITH_WARNINGS:
            if fallback_action in {
                FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                FallbackAction.USE_SOURCE_TEXT,
                FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
            }:
                return VerificationDecisionOutcome.REPAIR_AND_PASS
            return VerificationDecisionOutcome.PASS_WITH_WARNINGS
        if fallback_action == FallbackAction.BLOCK_RENDERING:
            return VerificationDecisionOutcome.FAIL_CLOSED
        if fallback_action == FallbackAction.REGENERATE_SPECIFIC_ITEM:
            return VerificationDecisionOutcome.REGENERATE_TARGET
        if fallback_action in {
            FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
            FallbackAction.USE_SOURCE_TEXT,
            FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
        }:
            return VerificationDecisionOutcome.REPAIR_AND_PASS
        return VerificationDecisionOutcome.FAIL_CLOSED

    def _run_decision_outcome(
        self,
        status: VerificationStatus,
        fallback_actions: Sequence[FallbackAction],
    ) -> VerificationDecisionOutcome:
        """Backfill run decision outcome when only legacy aggregate fields are stored."""

        if status == VerificationStatus.PASSED:
            return VerificationDecisionOutcome.PASS
        if status == VerificationStatus.PASSED_WITH_WARNINGS:
            if any(
                action in {
                    FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                    FallbackAction.USE_SOURCE_TEXT,
                    FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
                }
                for action in fallback_actions
            ):
                return VerificationDecisionOutcome.REPAIR_AND_PASS
            return VerificationDecisionOutcome.PASS_WITH_WARNINGS
        if any(action == FallbackAction.REGENERATE_SPECIFIC_ITEM for action in fallback_actions):
            return VerificationDecisionOutcome.REGENERATE_TARGET
        return VerificationDecisionOutcome.FAIL_CLOSED

    def _to_issue(self, issue: VerificationIssueModel, item_key: str) -> VerificationIssue:
        """Convert an ORM issue row into the verification issue contract."""

        details = issue.details_json or {}
        source_span = issue.source_span_json or {}
        source_item_ids = details.get("source_item_ids", source_span.get("source_item_ids", []))
        source_bullet_ids = details.get(
            "source_bullet_ids",
            source_span.get("source_bullet_ids", []),
        )
        return VerificationIssue(
            id=issue.id,
            category=IssueCategory(issue.category),
            severity=IssueSeverity(issue.severity),
            message=issue.message,
            generated_item_id=str(details.get("generated_item_id", item_key)),
            source_item_ids=[str(source_item_id) for source_item_id in source_item_ids],
            source_bullet_ids=[str(source_bullet_id) for source_bullet_id in source_bullet_ids],
            evidence_strength=EvidenceStrength(
                str(details.get("evidence_strength", EvidenceStrength.NONE.value))
            ),
            suggested_fallback=FallbackAction(
                str(details.get("suggested_fallback", FallbackAction.REQUIRE_HUMAN_REVIEW.value))
            ),
            validator_name=str(details.get("validator_name", "verification_repository")),
            retryable=bool(details.get("retryable", False)),
        )

    def _to_provenance_link(self, link: ProvenanceLinkModel) -> ProvenanceLink:
        """Convert an ORM provenance row into the verification provenance contract."""

        return ProvenanceLink(
            source_item_id=link.source_entity_id,
            source_item_type=ItemType(link.source_entity_type),
            source_bullet_id=link.source_bullet_id,
            evidence_strength=EvidenceStrength(link.evidence_strength),
            relation_type=ProvenanceRelationType(link.relation_type),
            generated_text_span=", ".join(link.matched_tokens_json) if link.matched_tokens_json else None,
        )
