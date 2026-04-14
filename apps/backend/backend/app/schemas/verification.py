"""Pydantic contracts for the Phase 6 resume verification gate.

The verification stage consumes structured Phase 3 resume content after
generation and before rendering acceptance. These schemas define the stable
handoff boundaries and item-level evidence contracts that future deterministic
and semantic validators will populate.

Compatibility note:
- Existing schema ids and a few exported class names still use `phase4`.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    ProvenanceRelationType,
    RepairExecutionStatus,
    VerificationDecisionOutcome,
    SemanticVerificationStatus,
    VerificationStatus,
)
from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.models import ItemType, MasterProfile, NonEmptyStr, ScoreValue, StableId, StrictModel
from resume_optimizer.phase3_models import (
    Phase3GenerationPayload,
    Phase3GenerationResult,
    SupportLevel,
)
from resume_optimizer.phase3_output_validation import Phase3ValidationReport

VERIFICATION_INPUT_SCHEMA_VERSION = "phase4.verification.input.v1"
VERIFICATION_REPORT_SCHEMA_VERSION = "phase4.verification.report.v1"
RENDERING_OUTPUT_SCHEMA_VERSION = "phase4.rendering.input.v1"


class ProvenanceLink(StrictModel):
    """Source-truth link used to evaluate support for a generated claim."""

    source_item_id: StableId
    source_item_type: ItemType
    source_bullet_id: StableId | None = None
    source_metric_ids: list[StableId] = Field(default_factory=list)
    source_excerpt: NonEmptyStr | None = None
    generated_text_span: NonEmptyStr | None = None
    evidence_strength: EvidenceStrength = EvidenceStrength.WEAK
    relation_type: ProvenanceRelationType | None = None
    support_level: SupportLevel | None = None
    support_score: ScoreValue | None = None

    @model_validator(mode="after")
    def validate_bullet_reference_shape(self) -> Self:
        """Reject bullet references on source item types that cannot own bullets."""

        if self.source_bullet_id is not None and self.source_item_type not in {
            ItemType.EXPERIENCE,
            ItemType.PROJECT,
            ItemType.EDUCATION,
        }:
            raise ValueError(
                "source_bullet_id is only valid for experience, project, or education items"
            )
        return self


class GeneratedBullet(StrictModel):
    """Generated resume bullet normalized for Phase 4 item-level verification."""

    id: StableId
    source_item_id: StableId
    source_item_type: Literal[ItemType.EXPERIENCE, ItemType.PROJECT]
    source_bullet_ids: list[StableId] = Field(min_length=1)
    text: NonEmptyStr
    claimed_metrics: list[NonEmptyStr] = Field(default_factory=list)
    claimed_tools: list[NonEmptyStr] = Field(default_factory=list)
    claimed_scope_terms: list[NonEmptyStr] = Field(default_factory=list)
    claimed_leadership_terms: list[NonEmptyStr] = Field(default_factory=list)
    claimed_keywords: list[NonEmptyStr] = Field(default_factory=list)
    provenance: list[ProvenanceLink] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance_alignment(self) -> Self:
        """Ensure declared source ids are represented by detailed provenance links."""

        source_item_ids = {link.source_item_id for link in self.provenance}
        if self.source_item_id not in source_item_ids:
            raise ValueError("source_item_id must be represented in provenance")

        provenance_bullet_ids = {
            link.source_bullet_id
            for link in self.provenance
            if link.source_bullet_id is not None
        }
        missing_bullet_ids = [
            bullet_id
            for bullet_id in self.source_bullet_ids
            if bullet_id not in provenance_bullet_ids
        ]
        if missing_bullet_ids:
            raise ValueError(
                "source_bullet_ids must be represented in provenance: "
                + ", ".join(missing_bullet_ids)
            )
        return self


class GeneratedSummaryClaim(StrictModel):
    """Atomic summary or headline claim to verify against source-truth evidence."""

    id: StableId
    text: NonEmptyStr
    claim_type: NonEmptyStr = "summary"
    source_item_ids: list[StableId] = Field(min_length=1)
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    claimed_metrics: list[NonEmptyStr] = Field(default_factory=list)
    claimed_tools: list[NonEmptyStr] = Field(default_factory=list)
    claimed_scope_terms: list[NonEmptyStr] = Field(default_factory=list)
    claimed_leadership_terms: list[NonEmptyStr] = Field(default_factory=list)
    claimed_keywords: list[NonEmptyStr] = Field(default_factory=list)
    provenance: list[ProvenanceLink] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance_alignment(self) -> Self:
        """Require every flattened source reference to have a provenance link."""

        provenance_item_ids = {link.source_item_id for link in self.provenance}
        missing_item_ids = [
            source_item_id
            for source_item_id in self.source_item_ids
            if source_item_id not in provenance_item_ids
        ]
        if missing_item_ids:
            raise ValueError(
                "source_item_ids must be represented in provenance: "
                + ", ".join(missing_item_ids)
            )

        provenance_bullet_ids = {
            link.source_bullet_id
            for link in self.provenance
            if link.source_bullet_id is not None
        }
        missing_bullet_ids = [
            bullet_id
            for bullet_id in self.source_bullet_ids
            if bullet_id not in provenance_bullet_ids
        ]
        if missing_bullet_ids:
            raise ValueError(
                "source_bullet_ids must be represented in provenance: "
                + ", ".join(missing_bullet_ids)
            )
        return self


class VerificationIssue(StrictModel):
    """Single verifier finding tied to generated content and source evidence."""

    id: StableId
    category: IssueCategory
    severity: IssueSeverity
    message: NonEmptyStr
    generated_item_id: StableId | None = None
    source_item_ids: list[StableId] = Field(default_factory=list)
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    suggested_fallback: FallbackAction = FallbackAction.REQUIRE_HUMAN_REVIEW
    validator_name: NonEmptyStr
    retryable: bool = False


class SemanticVerificationAudit(StrictModel):
    """Run-level audit of semantic verification execution and degradation."""

    enabled: bool = False
    strict_mode: bool = False
    fallback_behavior: NonEmptyStr = "block"
    status: SemanticVerificationStatus = SemanticVerificationStatus.DISABLED
    required_item_ids: list[StableId] = Field(default_factory=list)
    attempted_item_ids: list[StableId] = Field(default_factory=list)
    completed_item_ids: list[StableId] = Field(default_factory=list)
    degraded_item_ids: list[StableId] = Field(default_factory=list)
    messages: list[NonEmptyStr] = Field(default_factory=list)


class VerificationDecisionAudit(StrictModel):
    """Deterministic Phase 6 decision summary persisted with the report."""

    outcome: VerificationDecisionOutcome = VerificationDecisionOutcome.PASS
    confidence: ScoreValue = 1.0
    semantic_coverage: ScoreValue = 1.0
    degraded_semantic: bool = False
    issue_counts_by_severity: dict[NonEmptyStr, int] = Field(default_factory=dict)
    issue_counts_by_scope: dict[NonEmptyStr, int] = Field(default_factory=dict)
    reasons: list[NonEmptyStr] = Field(default_factory=list)


class VerificationRepairRecord(StrictModel):
    """One auditable repair attempt applied to generated content."""

    item_id: StableId
    item_type: NonEmptyStr
    fallback_action: FallbackAction
    status: RepairExecutionStatus
    strategy: NonEmptyStr
    original_text: NonEmptyStr | None = None
    repaired_text: NonEmptyStr | None = None
    removed_fragments: list[NonEmptyStr] = Field(default_factory=list)
    source_item_ids: list[StableId] = Field(default_factory=list)
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    requires_regeneration: bool = False
    notes: list[NonEmptyStr] = Field(default_factory=list)


class VerificationRepairAudit(StrictModel):
    """Aggregate repair execution details for the verification report."""

    attempted_item_ids: list[StableId] = Field(default_factory=list)
    repaired_item_ids: list[StableId] = Field(default_factory=list)
    failed_item_ids: list[StableId] = Field(default_factory=list)
    requires_regeneration_item_ids: list[StableId] = Field(default_factory=list)
    records: list[VerificationRepairRecord] = Field(default_factory=list)


class VerificationItemResult(StrictModel):
    """Verification result for one generated bullet, summary claim, or section item."""

    item_id: StableId
    item_type: NonEmptyStr
    status: VerificationStatus
    evidence_strength: EvidenceStrength
    provenance: list[ProvenanceLink] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    fallback_action: FallbackAction = FallbackAction.ACCEPT
    fallback_preview: NonEmptyStr | None = None
    decision_outcome: VerificationDecisionOutcome = VerificationDecisionOutcome.PASS
    decision_confidence: ScoreValue = 1.0
    decision_reasons: list[NonEmptyStr] = Field(default_factory=list)
    retryable: bool = False

    @model_validator(mode="after")
    def validate_status_consistency(self) -> Self:
        """Keep item status, issue severity, and fallback action coherent."""

        blocking_severities = {IssueSeverity.HIGH, IssueSeverity.CRITICAL}
        has_blocking_issue = any(issue.severity in blocking_severities for issue in self.issues)
        if self.status == VerificationStatus.PASSED and self.issues:
            raise ValueError("passed verification items must not contain issues")
        if self.status == VerificationStatus.FAILED and not has_blocking_issue:
            raise ValueError("failed verification items require an error or critical issue")
        if self.status == VerificationStatus.BLOCKED and self.fallback_action != FallbackAction.BLOCK_RENDERING:
            raise ValueError("blocked verification items must block rendering")
        if self.status == VerificationStatus.NEEDS_RETRY and not self.retryable:
            raise ValueError("needs_retry verification items must be retryable")
        return self


class VerificationReport(StrictModel):
    """Aggregate Phase 4 verification report for a generated resume artifact."""

    schema_version: NonEmptyStr = VERIFICATION_REPORT_SCHEMA_VERSION
    verification_run_id: StableId
    source_profile_id: StableId
    status: VerificationStatus
    item_results: list[VerificationItemResult] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    fallback_actions: list[FallbackAction] = Field(default_factory=list)
    deterministic_validator_names: list[NonEmptyStr] = Field(default_factory=list)
    semantic_validator_names: list[NonEmptyStr] = Field(default_factory=list)
    semantic_verification: SemanticVerificationAudit = Field(default_factory=SemanticVerificationAudit)
    decision_outcome: VerificationDecisionOutcome = VerificationDecisionOutcome.PASS
    decision_confidence: ScoreValue = 1.0
    decision_audit: VerificationDecisionAudit = Field(default_factory=VerificationDecisionAudit)
    repair_audit: VerificationRepairAudit = Field(default_factory=VerificationRepairAudit)
    renderable: bool = False
    retryable: bool = False

    @model_validator(mode="after")
    def validate_report_consistency(self) -> Self:
        """Enforce aggregate report state needed by rendering and retry orchestration."""

        item_issues = [issue for item in self.item_results for issue in item.issues]
        all_issues = [*self.issues, *item_issues]
        has_error = any(issue.severity == IssueSeverity.HIGH for issue in all_issues)
        has_critical = any(issue.severity == IssueSeverity.CRITICAL for issue in all_issues)

        if self.status == VerificationStatus.PASSED and all_issues:
            raise ValueError("passed verification reports must not contain issues")
        if self.status == VerificationStatus.PASSED_WITH_WARNINGS and not all_issues:
            raise ValueError("passed_with_warnings reports require at least one issue")
        if self.status == VerificationStatus.FAILED and not (has_error or has_critical):
            raise ValueError("failed verification reports require an error or critical issue")
        if self.status == VerificationStatus.BLOCKED and FallbackAction.BLOCK_RENDERING not in self.fallback_actions:
            raise ValueError("blocked verification reports must include block_rendering fallback")
        if self.renderable and self.status in {
            VerificationStatus.FAILED,
            VerificationStatus.BLOCKED,
            VerificationStatus.NEEDS_RETRY,
        }:
            raise ValueError("failed, blocked, or retryable reports cannot be renderable")
        if self.status == VerificationStatus.NEEDS_RETRY and not self.retryable:
            raise ValueError("needs_retry verification reports must be retryable")
        return self


class Phase3VerificationInput(StrictModel):
    """Stable input contract from Phase 3 generation into Phase 4 verification."""

    schema_version: NonEmptyStr = VERIFICATION_INPUT_SCHEMA_VERSION
    source_profile_id: StableId
    job_analysis: NormalizedJobAnalysis
    source_profile: MasterProfile
    generation_payload: Phase3GenerationPayload
    phase3_result: Phase3GenerationResult
    phase3_validation_report: Phase3ValidationReport | None = None

    @model_validator(mode="after")
    def validate_phase3_handoff_alignment(self) -> Self:
        """Ensure Phase 3 artifacts refer to the same source profile."""

        if self.source_profile_id != self.source_profile.id:
            raise ValueError("source_profile_id must match source_profile.id")
        if self.phase3_result.metadata.source_profile_id != self.source_profile_id:
            raise ValueError("phase3_result.metadata.source_profile_id must match source_profile_id")
        if self.generation_payload.validation_metadata.profile_id != self.source_profile_id:
            raise ValueError("generation_payload.validation_metadata.profile_id must match source_profile_id")
        return self


class Phase4RenderingOutput(StrictModel):
    """Stable output contract from Phase 4 verification into downstream rendering."""

    schema_version: NonEmptyStr = RENDERING_OUTPUT_SCHEMA_VERSION
    source_profile_id: StableId
    verified_result: Phase3GenerationResult
    verification_report: VerificationReport
    renderable: bool
    fallback_action: FallbackAction = FallbackAction.ACCEPT

    @model_validator(mode="after")
    def validate_rendering_gate(self) -> Self:
        """Require rendering decisions to match the aggregate verification report."""

        if self.verified_result.metadata.source_profile_id != self.source_profile_id:
            raise ValueError("verified_result.metadata.source_profile_id must match source_profile_id")
        if self.verification_report.source_profile_id != self.source_profile_id:
            raise ValueError("verification_report.source_profile_id must match source_profile_id")
        if self.renderable != self.verification_report.renderable:
            raise ValueError("renderable must match verification_report.renderable")
        if self.renderable and self.fallback_action == FallbackAction.BLOCK_RENDERING:
            raise ValueError("renderable output cannot block rendering")
        return self
