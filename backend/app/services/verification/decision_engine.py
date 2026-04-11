"""Centralized Phase 6 severity classification and decision policy."""

from __future__ import annotations

from collections import Counter

from pydantic import Field

from backend.app.schemas.verification import (
    SemanticVerificationAudit,
    VerificationDecisionAudit,
    VerificationIssue,
    VerificationItemResult,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.models import NonEmptyStr, ScoreValue, StableId, StrictModel


class ItemDecision(StrictModel):
    """Policy decision for one generated item after all validators run."""

    item_id: StableId
    item_type: NonEmptyStr
    status: VerificationStatus
    outcome: VerificationDecisionOutcome
    fallback_action: FallbackAction
    evidence_strength: EvidenceStrength
    confidence: ScoreValue = 1.0
    reasons: list[NonEmptyStr] = Field(default_factory=list)
    retryable: bool = False
    resolved_by_fallback: bool = False
    issue_counts_by_severity: dict[NonEmptyStr, int] = Field(default_factory=dict)
    issue_scope: NonEmptyStr = "item"
    semantic_degraded: bool = False


class RunDecision(StrictModel):
    """Aggregate policy decision for a verification run."""

    status: VerificationStatus
    outcome: VerificationDecisionOutcome
    fallback_actions: list[FallbackAction] = Field(default_factory=list)
    renderable: bool
    retryable: bool = False
    fallback_applied: bool = False
    overall_score: ScoreValue = Field(ge=0.0, le=1.0)
    confidence: ScoreValue = Field(ge=0.0, le=1.0)
    audit: VerificationDecisionAudit = Field(default_factory=VerificationDecisionAudit)


class VerificationDecisionEngine:
    """Translate verification issues into deterministic, inspectable actions."""

    _SEVERITY_WEIGHTS = {
        IssueSeverity.INFO: 0.01,
        IssueSeverity.LOW: 0.05,
        IssueSeverity.MEDIUM: 0.14,
        IssueSeverity.HIGH: 0.28,
        IssueSeverity.CRITICAL: 0.48,
    }
    _EVIDENCE_CONFIDENCE = {
        EvidenceStrength.NONE: 0.45,
        EvidenceStrength.WEAK: 0.62,
        EvidenceStrength.MODERATE: 0.78,
        EvidenceStrength.STRONG: 0.88,
        EvidenceStrength.EXACT: 0.95,
        EvidenceStrength.VERIFIED: 0.98,
    }
    _CRITICAL_UNSUPPORTED_CATEGORIES = {
        IssueCategory.UNSUPPORTED_METRIC,
        IssueCategory.UNSUPPORTED_TOOL,
        IssueCategory.UNSUPPORTED_CLAIM,
        IssueCategory.UNSUPPORTED_YEARS_EXPERIENCE,
        IssueCategory.ROLE_FAMILY_MISMATCH,
        IssueCategory.SENIORITY_MISMATCH,
    }
    _SUMMARY_SAFE_FALLBACK_CATEGORIES = {
        IssueCategory.UNSUPPORTED_YEARS_EXPERIENCE,
        IssueCategory.SENIORITY_MISMATCH,
        IssueCategory.ROLE_FAMILY_MISMATCH,
        IssueCategory.BREADTH_INFLATION,
        IssueCategory.UNSUPPORTED_SCOPE,
        IssueCategory.UNSUPPORTED_DOMAIN,
        IssueCategory.UNSUPPORTED_CLAIM,
        IssueCategory.UNSUPPORTED_CERTIFICATION,
        IssueCategory.UNSUPPORTED_AWARD,
        IssueCategory.UNSUPPORTED_LEADERSHIP,
    }
    _BULLET_REPAIRABLE_CATEGORIES = {
        IssueCategory.UNSUPPORTED_METRIC,
        IssueCategory.UNSUPPORTED_TOOL,
        IssueCategory.UNSUPPORTED_SCOPE,
        IssueCategory.UNSUPPORTED_LEADERSHIP,
        IssueCategory.UNSUPPORTED_KEYWORD,
        IssueCategory.UNSUPPORTED_CLAIM,
        IssueCategory.UNSUPPORTED_DOMAIN,
    }

    def decide_item(
        self,
        *,
        item_id: str,
        item_type: str,
        issues: list[VerificationIssue],
        evidence_strength: EvidenceStrength,
    ) -> ItemDecision:
        """Return the action for one item from issue severity, scope, and repairability."""

        severity_counts = self._severity_counts(issues)
        categories = {issue.category for issue in issues}
        scope = self._scope_for_item_type(item_type)
        semantic_degraded = IssueCategory.SEMANTIC_VERIFICATION_UNAVAILABLE in categories
        reasons: list[str] = []

        if not issues:
            return ItemDecision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.PASSED,
                outcome=VerificationDecisionOutcome.PASS,
                fallback_action=FallbackAction.PASS_AS_IS,
                evidence_strength=evidence_strength,
                confidence=self._item_confidence(
                    evidence_strength=evidence_strength,
                    issues=issues,
                    semantic_degraded=False,
                ),
                issue_counts_by_severity=severity_counts,
                issue_scope=scope,
                semantic_degraded=False,
            )

        has_critical = severity_counts.get(IssueSeverity.CRITICAL.value, 0) > 0
        has_high = severity_counts.get(IssueSeverity.HIGH.value, 0) > 0
        has_medium = severity_counts.get(IssueSeverity.MEDIUM.value, 0) > 0

        if semantic_degraded:
            reasons.append("semantic_verification_degraded")
        if has_critical and categories & self._CRITICAL_UNSUPPORTED_CATEGORIES:
            reasons.append("critical_unsupported_claim_detected")
        if categories == {IssueCategory.SEMANTIC_VERIFICATION_UNAVAILABLE}:
            if has_critical:
                reasons.append("semantic_verification_unavailable_in_blocking_mode")
                return self._build_item_decision(
                    item_id=item_id,
                    item_type=item_type,
                    status=VerificationStatus.BLOCKED,
                    outcome=VerificationDecisionOutcome.FAIL_CLOSED,
                    fallback_action=FallbackAction.BLOCK_RENDERING,
                    evidence_strength=EvidenceStrength.NONE,
                    reasons=reasons,
                    retryable=True,
                    resolved_by_fallback=False,
                    severity_counts=severity_counts,
                    scope=scope,
                    semantic_degraded=True,
                    issues=issues,
                )
            reasons.append("semantic_verification_unavailable_requires_review")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
                fallback_action=FallbackAction.MARK_NEEDS_REVIEW,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=False,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=True,
                issues=issues,
            )

        if item_type == "summary":
            decision = self._decide_summary_item(
                item_id=item_id,
                item_type=item_type,
                evidence_strength=evidence_strength,
                severity_counts=severity_counts,
                categories=categories,
                reasons=reasons,
                semantic_degraded=semantic_degraded,
            )
        elif item_type == "skill_statement":
            reasons.append("unsupported_skill_highlight_can_be_removed_safely")
            decision = self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
                fallback_action=FallbackAction.REMOVE_CLAIM,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=True,
                severity_counts=severity_counts,
                scope="skills",
                semantic_degraded=semantic_degraded,
                issues=issues,
            )
        elif item_type.endswith("_bullet"):
            decision = self._decide_bullet_item(
                item_id=item_id,
                item_type=item_type,
                evidence_strength=evidence_strength,
                severity_counts=severity_counts,
                categories=categories,
                reasons=reasons,
                semantic_degraded=semantic_degraded,
            )
        elif has_high or has_critical:
            reasons.append("high_severity_section_issue_requires_regeneration")
            decision = self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.FAILED,
                outcome=VerificationDecisionOutcome.REGENERATE_TARGET,
                fallback_action=FallbackAction.REGENERATE_SPECIFIC_ITEM,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=True,
                resolved_by_fallback=False,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=semantic_degraded,
                issues=issues,
            )
        elif has_medium:
            reasons.append("medium_section_issue_requires_repair")
            decision = self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
                fallback_action=FallbackAction.USE_SOURCE_TEXT,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=True,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=semantic_degraded,
                issues=issues,
            )
        else:
            reasons.append("low_severity_issue_marked_for_review")
            decision = self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
                fallback_action=FallbackAction.MARK_NEEDS_REVIEW,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=False,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=semantic_degraded,
                issues=issues,
            )
        return decision

    def decide_run(
        self,
        *,
        item_decisions: list[ItemDecision],
        semantic_audit: SemanticVerificationAudit,
        item_results: list[VerificationItemResult] | None = None,
    ) -> RunDecision:
        """Aggregate item decisions into a run-level render gate and audit artifact."""

        if not item_decisions:
            audit = VerificationDecisionAudit(
                outcome=VerificationDecisionOutcome.FAIL_CLOSED,
                confidence=0.0,
                semantic_coverage=0.0,
                degraded_semantic=semantic_audit.status.value == "degraded",
                reasons=["verification_run_contains_no_items"],
            )
            return RunDecision(
                status=VerificationStatus.BLOCKED,
                outcome=VerificationDecisionOutcome.FAIL_CLOSED,
                fallback_actions=[FallbackAction.BLOCK_RENDERING],
                renderable=False,
                overall_score=0.0,
                confidence=0.0,
                audit=audit,
            )

        fallback_actions = sorted(
            {decision.fallback_action for decision in item_decisions},
            key=lambda action: action.value,
        )
        retryable = any(decision.retryable for decision in item_decisions)
        resolved_repairs = [
            decision
            for decision in item_decisions
            if decision.outcome == VerificationDecisionOutcome.REPAIR_AND_PASS
        ]
        targeted_regens = [
            decision
            for decision in item_decisions
            if decision.outcome == VerificationDecisionOutcome.REGENERATE_TARGET
        ]
        fail_closed = [
            decision
            for decision in item_decisions
            if decision.outcome == VerificationDecisionOutcome.FAIL_CLOSED
        ]
        warnings = [
            decision
            for decision in item_decisions
            if decision.outcome == VerificationDecisionOutcome.PASS_WITH_WARNINGS
        ]
        section_medium_counts = Counter(
            decision.issue_scope
            for decision in item_decisions
            if decision.issue_counts_by_severity.get(IssueSeverity.MEDIUM.value, 0) > 0
        )
        reasons: list[str] = []
        if semantic_audit.degraded_item_ids:
            reasons.append("semantic_verification_degraded")
        for scope, count in sorted(section_medium_counts.items()):
            if count >= 2:
                reasons.append(f"multiple_medium_issues_in_{scope}")

        semantic_coverage = self._semantic_coverage(semantic_audit)
        confidence = self._run_confidence(
            item_decisions=item_decisions,
            semantic_coverage=semantic_coverage,
            semantic_degraded=bool(semantic_audit.degraded_item_ids),
        )
        overall_score = round(
            sum(decision.confidence for decision in item_decisions) / len(item_decisions),
            4,
        )
        audit = VerificationDecisionAudit(
            outcome=VerificationDecisionOutcome.PASS,
            confidence=confidence,
            semantic_coverage=semantic_coverage,
            degraded_semantic=bool(semantic_audit.degraded_item_ids),
            issue_counts_by_severity=self._aggregate_severity_counts(item_decisions),
            issue_counts_by_scope=self._aggregate_scope_counts(item_decisions),
            reasons=reasons,
        )

        if fail_closed:
            audit.outcome = VerificationDecisionOutcome.FAIL_CLOSED
            audit.reasons.extend(["critical_issue_without_safe_fallback"])
            return RunDecision(
                status=VerificationStatus.FAILED,
                outcome=VerificationDecisionOutcome.FAIL_CLOSED,
                fallback_actions=sorted(
                    {*fallback_actions, FallbackAction.BLOCK_RENDERING},
                    key=lambda action: action.value,
                ),
                renderable=False,
                retryable=retryable,
                fallback_applied=True,
                overall_score=overall_score,
                confidence=confidence,
                audit=audit,
            )

        if any(count >= 2 for count in section_medium_counts.values()):
            audit.outcome = VerificationDecisionOutcome.REGENERATE_TARGET
            audit.reasons.extend(["repeated_medium_issues_escalated_to_regeneration"])
            return RunDecision(
                status=VerificationStatus.FAILED,
                outcome=VerificationDecisionOutcome.REGENERATE_TARGET,
                fallback_actions=sorted(
                    {*fallback_actions, FallbackAction.REGENERATE_SPECIFIC_ITEM},
                    key=lambda action: action.value,
                ),
                renderable=False,
                retryable=True,
                fallback_applied=bool(fallback_actions),
                overall_score=overall_score,
                confidence=confidence,
                audit=audit,
            )

        if targeted_regens:
            audit.outcome = VerificationDecisionOutcome.REGENERATE_TARGET
            audit.reasons.extend(["targeted_regeneration_required"])
            return RunDecision(
                status=VerificationStatus.FAILED,
                outcome=VerificationDecisionOutcome.REGENERATE_TARGET,
                fallback_actions=fallback_actions,
                renderable=False,
                retryable=True,
                fallback_applied=bool(fallback_actions),
                overall_score=overall_score,
                confidence=confidence,
                audit=audit,
            )

        if resolved_repairs:
            audit.outcome = VerificationDecisionOutcome.REPAIR_AND_PASS
            audit.reasons.extend(["safe_fallback_or_repair_available"])
            return RunDecision(
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
                fallback_actions=fallback_actions,
                renderable=True,
                retryable=retryable,
                fallback_applied=True,
                overall_score=overall_score,
                confidence=confidence,
                audit=audit,
            )

        if warnings or semantic_audit.degraded_item_ids:
            audit.outcome = VerificationDecisionOutcome.PASS_WITH_WARNINGS
            if semantic_audit.degraded_item_ids:
                audit.reasons.extend(["confidence_reduced_due_to_semantic_degradation"])
            return RunDecision(
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
                fallback_actions=fallback_actions,
                renderable=True,
                retryable=retryable,
                fallback_applied=any(action != FallbackAction.PASS_AS_IS for action in fallback_actions),
                overall_score=overall_score,
                confidence=confidence,
                audit=audit,
            )

        audit.outcome = VerificationDecisionOutcome.PASS
        return RunDecision(
            status=VerificationStatus.PASSED,
            outcome=VerificationDecisionOutcome.PASS,
            fallback_actions=fallback_actions,
            renderable=True,
            retryable=False,
            fallback_applied=False,
            overall_score=1.0,
            confidence=confidence,
            audit=audit,
        )

    def _decide_summary_item(
        self,
        *,
        item_id: str,
        item_type: str,
        evidence_strength: EvidenceStrength,
        severity_counts: dict[str, int],
        categories: set[IssueCategory],
        reasons: list[str],
        semantic_degraded: bool,
    ) -> ItemDecision:
        has_critical = severity_counts.get(IssueSeverity.CRITICAL.value, 0) > 0
        has_high = severity_counts.get(IssueSeverity.HIGH.value, 0) > 0
        has_medium = severity_counts.get(IssueSeverity.MEDIUM.value, 0) > 0

        if has_critical and categories & self._SUMMARY_SAFE_FALLBACK_CATEGORIES:
            reasons.append("critical_summary_claim_repaired_by_safe_summary_fallback")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.FAILED,
                outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
                fallback_action=FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=True,
                severity_counts=severity_counts,
                scope="summary",
                semantic_degraded=semantic_degraded,
            )

        if has_critical:
            reasons.append("critical_summary_claim_requires_fail_closed")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.BLOCKED,
                outcome=VerificationDecisionOutcome.FAIL_CLOSED,
                fallback_action=FallbackAction.BLOCK_RENDERING,
                evidence_strength=EvidenceStrength.NONE,
                reasons=reasons,
                retryable=True,
                resolved_by_fallback=False,
                severity_counts=severity_counts,
                scope="summary",
                semantic_degraded=semantic_degraded,
            )

        if has_high:
            fallback = (
                FallbackAction.USE_SAFE_SUMMARY_FALLBACK
                if categories & self._SUMMARY_SAFE_FALLBACK_CATEGORIES
                else FallbackAction.REGENERATE_SPECIFIC_ITEM
            )
            outcome = (
                VerificationDecisionOutcome.REPAIR_AND_PASS
                if fallback == FallbackAction.USE_SAFE_SUMMARY_FALLBACK
                else VerificationDecisionOutcome.REGENERATE_TARGET
            )
            reasons.append("high_severity_summary_issue")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.FAILED,
                outcome=outcome,
                fallback_action=fallback,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=fallback == FallbackAction.REGENERATE_SPECIFIC_ITEM,
                resolved_by_fallback=fallback == FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
                severity_counts=severity_counts,
                scope="summary",
                semantic_degraded=semantic_degraded,
            )

        if has_medium:
            reasons.append("medium_summary_issue_passes_with_warnings")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
                fallback_action=FallbackAction.MARK_NEEDS_REVIEW,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=False,
                severity_counts=severity_counts,
                scope="summary",
                semantic_degraded=semantic_degraded,
            )

        reasons.append("low_summary_issue_marked_for_review")
        return self._build_item_decision(
            item_id=item_id,
            item_type=item_type,
            status=VerificationStatus.PASSED_WITH_WARNINGS,
            outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
            fallback_action=FallbackAction.MARK_NEEDS_REVIEW,
            evidence_strength=evidence_strength,
            reasons=reasons,
            retryable=False,
            resolved_by_fallback=False,
            severity_counts=severity_counts,
            scope="summary",
            semantic_degraded=semantic_degraded,
        )

    def _decide_bullet_item(
        self,
        *,
        item_id: str,
        item_type: str,
        evidence_strength: EvidenceStrength,
        severity_counts: dict[str, int],
        categories: set[IssueCategory],
        reasons: list[str],
        semantic_degraded: bool,
    ) -> ItemDecision:
        has_critical = severity_counts.get(IssueSeverity.CRITICAL.value, 0) > 0
        has_high = severity_counts.get(IssueSeverity.HIGH.value, 0) > 0
        has_medium = severity_counts.get(IssueSeverity.MEDIUM.value, 0) > 0
        scope = self._scope_for_item_type(item_type)

        if (has_critical or has_high) and categories & self._BULLET_REPAIRABLE_CATEGORIES:
            reasons.append("unsupported_bullet_claim_repaired_via_source_fallback")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.FAILED,
                outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
                fallback_action=FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                evidence_strength=EvidenceStrength.NONE,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=True,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=semantic_degraded,
            )

        if has_critical:
            reasons.append("critical_bullet_issue_without_safe_fallback")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.BLOCKED,
                outcome=VerificationDecisionOutcome.FAIL_CLOSED,
                fallback_action=FallbackAction.BLOCK_RENDERING,
                evidence_strength=EvidenceStrength.NONE,
                reasons=reasons,
                retryable=True,
                resolved_by_fallback=False,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=semantic_degraded,
            )

        if has_high:
            reasons.append("high_severity_bullet_issue_requires_regeneration")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.FAILED,
                outcome=VerificationDecisionOutcome.REGENERATE_TARGET,
                fallback_action=FallbackAction.REGENERATE_SPECIFIC_ITEM,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=True,
                resolved_by_fallback=False,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=semantic_degraded,
            )

        if has_medium:
            reasons.append("medium_bullet_issue_repaired_via_source_fallback")
            return self._build_item_decision(
                item_id=item_id,
                item_type=item_type,
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
                fallback_action=FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                evidence_strength=evidence_strength,
                reasons=reasons,
                retryable=False,
                resolved_by_fallback=True,
                severity_counts=severity_counts,
                scope=scope,
                semantic_degraded=semantic_degraded,
            )

        reasons.append("low_bullet_issue_marked_for_review")
        return self._build_item_decision(
            item_id=item_id,
            item_type=item_type,
            status=VerificationStatus.PASSED_WITH_WARNINGS,
            outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
            fallback_action=FallbackAction.MARK_NEEDS_REVIEW,
            evidence_strength=evidence_strength,
            reasons=reasons,
            retryable=False,
            resolved_by_fallback=False,
            severity_counts=severity_counts,
            scope=scope,
            semantic_degraded=semantic_degraded,
        )

    def _build_item_decision(
        self,
        *,
        item_id: str,
        item_type: str,
        status: VerificationStatus,
        outcome: VerificationDecisionOutcome,
        fallback_action: FallbackAction,
        evidence_strength: EvidenceStrength,
        reasons: list[str],
        retryable: bool,
        resolved_by_fallback: bool,
        severity_counts: dict[str, int],
        scope: str,
        semantic_degraded: bool,
        issues: list[VerificationIssue] | None = None,
    ) -> ItemDecision:
        return ItemDecision(
            item_id=item_id,
            item_type=item_type,
            status=status,
            outcome=outcome,
            fallback_action=fallback_action,
            evidence_strength=evidence_strength,
            confidence=self._item_confidence(
                evidence_strength=evidence_strength,
                issues=issues or [],
                semantic_degraded=semantic_degraded,
            ),
            reasons=reasons,
            retryable=retryable,
            resolved_by_fallback=resolved_by_fallback,
            issue_counts_by_severity=severity_counts,
            issue_scope=scope,
            semantic_degraded=semantic_degraded,
        )

    def _severity_counts(self, issues: list[VerificationIssue]) -> dict[str, int]:
        counts = Counter(issue.severity.value for issue in issues)
        return {severity: count for severity, count in sorted(counts.items())}

    def _aggregate_severity_counts(self, item_decisions: list[ItemDecision]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for decision in item_decisions:
            counts.update(decision.issue_counts_by_severity)
        return {severity: count for severity, count in sorted(counts.items())}

    def _aggregate_scope_counts(self, item_decisions: list[ItemDecision]) -> dict[str, int]:
        counts = Counter(
            decision.issue_scope for decision in item_decisions if decision.issue_counts_by_severity
        )
        return {scope: count for scope, count in sorted(counts.items())}

    def _scope_for_item_type(self, item_type: str) -> str:
        if item_type.endswith("_bullet"):
            return item_type.removesuffix("_bullet")
        return item_type

    def _semantic_coverage(self, audit: SemanticVerificationAudit) -> float:
        required = len(audit.required_item_ids)
        if required == 0:
            return 1.0
        return round(len(audit.completed_item_ids) / required, 4)

    def _item_confidence(
        self,
        *,
        evidence_strength: EvidenceStrength,
        issues: list[VerificationIssue],
        semantic_degraded: bool,
    ) -> float:
        confidence = self._EVIDENCE_CONFIDENCE[evidence_strength]
        confidence -= sum(self._SEVERITY_WEIGHTS[issue.severity] for issue in issues)
        if semantic_degraded:
            confidence -= 0.2
        return round(max(0.0, min(1.0, confidence)), 4)

    def _run_confidence(
        self,
        *,
        item_decisions: list[ItemDecision],
        semantic_coverage: float,
        semantic_degraded: bool,
    ) -> float:
        base = sum(decision.confidence for decision in item_decisions) / len(item_decisions)
        if semantic_coverage < 1.0:
            base *= semantic_coverage
        if semantic_degraded:
            base -= 0.08
        return round(max(0.0, min(1.0, base)), 4)
