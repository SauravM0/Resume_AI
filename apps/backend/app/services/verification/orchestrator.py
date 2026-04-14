"""Stage-by-stage Phase 6 verification orchestrator.

Compatibility note:
- Several persisted schema ids and public class names still use `phase4` because
  those contracts have already shipped. Runtime behavior is Phase 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import Field as PydanticField

from backend.app.schemas.verification import (
    Phase3VerificationInput,
    Phase4RenderingOutput,
    SemanticVerificationAudit,
    VerificationIssue,
    VerificationItemResult,
    VerificationReport,
)
from backend.app.services.verification.decision_engine import (
    ItemDecision,
    VerificationDecisionEngine,
)
from backend.app.services.verification.audit_artifact import (
    build_verification_audit_artifact,
    serialize_verification_audit_artifact,
)
from backend.app.services.verification.deterministic_validators import (
    DeterministicValidationInput,
    DeterministicValidator,
    SelectedContentContext,
    SourceContext,
)
from backend.app.services.verification.fallback_repair import (
    FallbackRepairService,
    RepairExecutionResult,
)
from backend.app.services.verification.provenance_service import (
    ProvenanceMap,
    ProvenanceMatch,
    ProvenanceService,
)
from backend.app.services.verification.semantic_validator import (
    SemanticValidationInput,
    SemanticValidationError,
    SemanticValidatorService,
)
from backend.app.services.verification.summary_verifier import SummaryVerifier
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    SemanticVerificationStatus,
    SemanticVerifierUnavailableBehavior,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel
from resume_optimizer.phase3_models import GeneratedSkillHighlight, Phase3GenerationResult

if TYPE_CHECKING:
    from backend.app.db.repositories.verification_repository import VerificationRepository

logger = logging.getLogger(__name__)

SEMANTICALLY_REQUIRED_ITEM_TYPES = frozenset({"summary", "experience_bullet", "project_bullet"})


class VerificationPipelineItem(StrictModel):
    """Normalized generated item consumed by the verification pipeline."""

    item_id: StableId
    item_type: NonEmptyStr
    generated_text: NonEmptyStr
    confidence: float | None = PydanticField(default=None, ge=0.0, le=1.0)


class VerificationRunResult(StrictModel):
    """Full orchestrator output including report and downstream rendering contract."""

    verification_run_id: StableId
    started_at: datetime
    finished_at: datetime
    provenance_map: ProvenanceMap
    report: VerificationReport
    rendering_output: Phase4RenderingOutput


@dataclass(frozen=True, slots=True)
class SemanticVerificationPolicy:
    """Runtime policy controlling mandatory semantic verification behavior."""

    enabled: bool = False
    strict_mode: bool = False
    fallback_behavior: SemanticVerifierUnavailableBehavior = (
        SemanticVerifierUnavailableBehavior.BLOCK
    )


@dataclass(slots=True)
class SemanticExecutionOutcome:
    """Per-item semantic execution state for run-level audit aggregation."""

    required: bool
    attempted: bool = False
    completed: bool = False
    degraded: bool = False
    message: str | None = None
    fallback_preview: str | None = None


def build_default_semantic_verification_policy() -> SemanticVerificationPolicy:
    """Resolve the production semantic verification policy from settings."""

    raw_behavior = getattr(
        DEFAULT_SETTINGS,
        "phase6_semantic_verifier_unavailable_behavior",
        SemanticVerifierUnavailableBehavior.BLOCK.value,
    )
    try:
        fallback_behavior = SemanticVerifierUnavailableBehavior(raw_behavior)
    except ValueError:
        logger.warning(
            "invalid semantic verifier unavailable behavior; defaulting to block",
            extra={"configured_behavior": raw_behavior},
        )
        fallback_behavior = SemanticVerifierUnavailableBehavior.BLOCK
    return SemanticVerificationPolicy(
        enabled=getattr(DEFAULT_SETTINGS, "phase6_semantic_verification_enabled", True),
        strict_mode=getattr(DEFAULT_SETTINGS, "phase6_semantic_verification_strict_mode", True),
        fallback_behavior=fallback_behavior,
    )


def build_default_semantic_validator() -> SemanticValidatorService | None:
    """Construct the default semantic validator only when production policy enables it."""

    policy = build_default_semantic_verification_policy()
    if not policy.enabled:
        return None
    return SemanticValidatorService()


def build_default_verification_orchestrator(
    *,
    repository: "VerificationRepository | None" = None,
) -> "VerificationOrchestrator":
    """Create the production verifier with semantic verification wired in by default."""

    return VerificationOrchestrator(
        semantic_validator=build_default_semantic_validator(),
        semantic_policy=build_default_semantic_verification_policy(),
        repository=repository,
    )


@dataclass(slots=True)
class VerificationOrchestrator:
    """Run provenance, deterministic validation, semantic validation, and policy aggregation."""

    provenance_service: ProvenanceService = field(default_factory=ProvenanceService)
    deterministic_validator: DeterministicValidator = field(default_factory=DeterministicValidator)
    summary_verifier: SummaryVerifier = field(default_factory=SummaryVerifier)
    semantic_validator: SemanticValidatorService | None = None
    semantic_policy: SemanticVerificationPolicy = field(default_factory=SemanticVerificationPolicy)
    decision_engine: VerificationDecisionEngine = field(default_factory=VerificationDecisionEngine)
    repair_service: FallbackRepairService = field(default_factory=FallbackRepairService)
    repository: "VerificationRepository | None" = None

    def run(
        self,
        verification_input: Phase3VerificationInput,
        *,
        verification_run_id: str | None = None,
        generation_id: str | None = None,
        pipeline_run_id: str | None = None,
        job_id: str | None = None,
        jd_hash: str | None = None,
    ) -> VerificationRunResult:
        """Run the full Phase 6 verification pipeline for one Phase 3 artifact."""

        started_at = datetime.now(timezone.utc)
        run_id = verification_run_id or f"verify.{uuid4()}"
        logger.info("phase6 verification started", extra={"verification_run_id": run_id})

        items = _iter_phase3_items(verification_input.phase3_result)
        semantic_audit = self._build_semantic_audit(items)
        persisted_run = None
        if self.repository is not None:
            persisted_run = self.repository.create_verification_run(
                generation_id=generation_id,
                pipeline_run_id=pipeline_run_id,
                candidate_id=verification_input.source_profile_id,
                job_id=job_id,
                jd_hash=jd_hash,
                status=VerificationStatus.PENDING,
                raw_artifact_refs={
                    "phase3_schema_version": verification_input.phase3_result.metadata.schema_version,
                    "semantic_verification_policy": {
                        "enabled": semantic_audit.enabled,
                        "strict_mode": semantic_audit.strict_mode,
                        "fallback_behavior": semantic_audit.fallback_behavior,
                    },
                },
            )
            run_id = persisted_run.id

        provenance_map = self.provenance_service.build_for_phase3_result(
            source_profile=verification_input.source_profile,
            phase3_result=verification_input.phase3_result,
        )
        matches_by_item = _matches_by_item(provenance_map.matches)
        job_keywords = _job_keywords(verification_input)

        item_results: list[VerificationItemResult] = []
        item_decisions: list[ItemDecision] = []
        for item in items:
            item_matches = matches_by_item.get(item.item_id, [])
            issues, semantic_outcome = self._validate_item(
                item=item,
                item_matches=item_matches,
                verification_input=verification_input,
                job_keywords=job_keywords,
            )
            self._record_semantic_outcome(semantic_audit, item=item, outcome=semantic_outcome)
            evidence_strength = _strongest_evidence(item_matches)
            decision = self.decision_engine.decide_item(
                item_id=item.item_id,
                item_type=item.item_type,
                issues=issues,
                evidence_strength=evidence_strength,
            )
            item_decisions.append(decision)

            item_result = VerificationItemResult(
                item_id=item.item_id,
                item_type=item.item_type,
                status=decision.status,
                evidence_strength=decision.evidence_strength,
                provenance=[match.to_schema_link() for match in item_matches],
                issues=issues,
                fallback_action=decision.fallback_action,
                fallback_preview=semantic_outcome.fallback_preview,
                decision_outcome=decision.outcome,
                decision_confidence=decision.confidence,
                decision_reasons=decision.reasons,
                retryable=decision.retryable,
            )
            item_results.append(item_result)

            if self.repository is not None:
                self._persist_item(
                    verification_run_id=run_id,
                    item=item,
                    decision=decision,
                    item_matches=item_matches,
                    issues=issues,
                )

        repair_execution = self.repair_service.apply(
            phase3_result=verification_input.phase3_result,
            source_profile=verification_input.source_profile,
            generation_payload=verification_input.generation_payload,
            item_results=item_results,
        )
        item_results = repair_execution.repaired_item_results
        item_decisions = _apply_repair_results_to_decisions(
            item_decisions=item_decisions,
            repair_execution=repair_execution,
        )
        report_semantic_audit = self._finalize_semantic_audit(
            semantic_audit,
            run_status=VerificationStatus.PASSED,
        )
        run_decision = self.decision_engine.decide_run(
            item_decisions=item_decisions,
            semantic_audit=report_semantic_audit,
            item_results=item_results,
        )
        report = VerificationReport(
            verification_run_id=run_id,
            source_profile_id=verification_input.source_profile_id,
            status=run_decision.status,
            item_results=item_results,
            issues=[],
            fallback_actions=run_decision.fallback_actions,
            deterministic_validator_names=[
                "numeric_claim_validator",
                "tool_technology_validator",
                "keyword_support_validator",
                "role_inflation_validator",
                "seniority_leadership_inflation_validator",
                "summary_fact_validator",
                "summary_years_experience_validator",
                "summary_leadership_level_validator",
                "summary_functional_specialization_validator",
                "summary_domain_expertise_validator",
                "summary_architecture_scope_validator",
                "summary_product_ownership_validator",
                "summary_stakeholder_management_validator",
                "summary_breadth_inflation_validator",
                "summary_seniority_mismatch_validator",
                "summary_role_family_validator",
            ],
            semantic_validator_names=(
                ["semantic_faithfulness_validator"] if self.semantic_validator is not None else []
            ),
            decision_outcome=run_decision.outcome,
            decision_confidence=run_decision.confidence,
            decision_audit=run_decision.audit,
            repair_audit=repair_execution.repair_audit,
            renderable=run_decision.renderable,
            retryable=run_decision.retryable,
        )
        report.semantic_verification = self._finalize_semantic_audit(
            report_semantic_audit,
            run_status=run_decision.status,
        )
        rendering_output = Phase4RenderingOutput(
            source_profile_id=verification_input.source_profile_id,
            verified_result=repair_execution.repaired_result,
            verification_report=report,
            renderable=report.renderable,
            fallback_action=_run_fallback_action(run_decision.fallback_actions),
        )

        finished_at = datetime.now(timezone.utc)
        verification_audit_payload: dict[str, object] | None = None
        if getattr(DEFAULT_SETTINGS, "phase6_audit_persistence_enabled", True):
            verification_audit_artifact = build_verification_audit_artifact(
                run_id=run_id,
                verification_timestamp=finished_at,
                report=report,
            )
            verification_audit_payload, _verification_audit_json, _verification_audit_hash = (
                serialize_verification_audit_artifact(verification_audit_artifact)
            )
        if self.repository is not None:
            raw_artifact_refs_update = {
                "semantic_verification": report.semantic_verification.model_dump(mode="json"),
                "decision_audit": report.decision_audit.model_dump(mode="json"),
                "repair_audit": report.repair_audit.model_dump(mode="json"),
            }
            if verification_audit_payload is not None:
                raw_artifact_refs_update["verification_audit"] = verification_audit_payload
            self.repository.finalize_run(
                verification_run_id=run_id,
                status=run_decision.status,
                overall_score=run_decision.overall_score,
                fallback_applied=run_decision.fallback_applied,
                summary_status=_summary_status(item_results),
                finished_at=finished_at,
                raw_artifact_refs_update=raw_artifact_refs_update,
            )

        self._log_semantic_outcome(run_id=run_id, audit=report.semantic_verification)
        logger.info(
            "phase6 verification completed",
            extra={
                "verification_run_id": run_id,
                "status": report.status.value,
                "item_count": len(item_results),
                "issue_count": sum(len(item.issues) for item in item_results),
                "fallback_applied": run_decision.fallback_applied,
                "semantic_verification_status": report.semantic_verification.status.value,
                "semantic_degraded_items": list(report.semantic_verification.degraded_item_ids),
                "decision_outcome": report.decision_outcome.value,
                "audit_persisted": verification_audit_payload is not None,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            },
        )
        return VerificationRunResult(
            verification_run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            provenance_map=provenance_map,
            report=report,
            rendering_output=rendering_output,
        )

    def _validate_item(
        self,
        *,
        item: VerificationPipelineItem,
        item_matches: list[ProvenanceMatch],
        verification_input: Phase3VerificationInput,
        job_keywords: list[str],
    ) -> tuple[list[VerificationIssue], SemanticExecutionOutcome]:
        """Run deterministic validators and mandatory semantic validation where configured."""

        if item.item_type == "summary":
            return self._validate_summary(
                item=item,
                item_matches=item_matches,
                verification_input=verification_input,
                job_keywords=job_keywords,
            )

        issues = self.deterministic_validator.validate_item(
            DeterministicValidationInput(
                item_id=item.item_id,
                item_type=item.item_type,
                generated_text=item.generated_text,
                provenance_matches=item_matches,
                source_profile=verification_input.source_profile,
                job_keywords=job_keywords,
                generation_payload=verification_input.generation_payload,
            )
        )
        if not item_matches:
            issues.append(
                VerificationIssue(
                    id=f"issue.provenance_missing.{item.item_id}",
                    category=IssueCategory.PROVENANCE_MISSING,
                    severity=IssueSeverity.HIGH,
                    message="Generated item has no source provenance links.",
                    generated_item_id=item.item_id,
                    validator_name="provenance_presence_validator",
                    suggested_fallback=FallbackAction.MARK_NEEDS_REVIEW,
                )
            )

        semantic_outcome = SemanticExecutionOutcome(required=self._requires_semantic(item))
        if not semantic_outcome.required:
            return issues, semantic_outcome
        if self.semantic_validator is None:
            message = (
                f"Semantic verification is required for {item.item_type} {item.item_id}, "
                "but no semantic validator is configured."
            )
            issues.append(self._semantic_unavailable_issue(item=item, message=message))
            semantic_outcome.degraded = True
            semantic_outcome.message = message
            return issues, semantic_outcome
        if not item_matches:
            message = (
                f"Semantic verification could not run for {item.item_type} {item.item_id} "
                "because no provenance evidence was available."
            )
            issues.append(self._semantic_unavailable_issue(item=item, message=message))
            semantic_outcome.degraded = True
            semantic_outcome.message = message
            return issues, semantic_outcome

        semantic_outcome.attempted = True
        try:
            semantic_result = self.semantic_validator.validate_item(
                SemanticValidationInput(
                    item_id=item.item_id,
                    item_type=item.item_type,
                    generated_text=item.generated_text,
                    provenance_matches=item_matches,
                )
            )
        except SemanticValidationError as exc:
            message = (
                f"Semantic verification could not complete for {item.item_type} {item.item_id}: {exc}"
            )
            issues.append(self._semantic_unavailable_issue(item=item, message=message))
            semantic_outcome.degraded = True
            semantic_outcome.message = message
            return issues, semantic_outcome

        issues.extend(semantic_result.issues)
        semantic_outcome.completed = True
        if semantic_result.issues:
            semantic_outcome.message = (
                f"Semantic verification reported {len(semantic_result.issues)} issue(s) "
                f"for {item.item_id}."
            )
        return issues, semantic_outcome

    def _validate_summary(
        self,
        *,
        item: VerificationPipelineItem,
        item_matches: list[ProvenanceMatch],
        verification_input: Phase3VerificationInput,
        job_keywords: list[str],
    ) -> tuple[list[VerificationIssue], SemanticExecutionOutcome]:
        """Run the dedicated claim-level summary verifier."""

        deterministic_input = DeterministicValidationInput(
            item_id=item.item_id,
            item_type=item.item_type,
            generated_text=item.generated_text,
            provenance_matches=item_matches,
            source_profile=verification_input.source_profile,
            job_keywords=job_keywords,
            generation_payload=verification_input.generation_payload,
        )
        selected_context = SelectedContentContext.from_generation_payload(
            verification_input.generation_payload
        )
        source_context = SourceContext.from_entire_profile(verification_input.source_profile)
        result = self.summary_verifier.verify(
            validation_input=deterministic_input,
            source_context=source_context,
            selected_context=selected_context,
            semantic_validator=self.semantic_validator if self._requires_semantic(item) else None,
        )
        issues = list(result.issues)
        semantic_outcome = SemanticExecutionOutcome(
            required=self._requires_semantic(item),
            attempted=result.semantic_attempted,
            completed=result.semantic_completed,
            degraded=result.semantic_attempted and not result.semantic_completed and result.semantic_degraded_message is not None,
            message=result.semantic_degraded_message,
            fallback_preview=result.fallback_plan.safe_summary_text,
        )
        if result.fallback_plan.safe_summary_text:
            logger.info(
                "phase6 summary fallback plan prepared",
                extra={
                    "verification_item_id": item.item_id,
                    "fallback_preview": result.fallback_plan.safe_summary_text,
                    "removed_claim_count": len(result.fallback_plan.removed_claims),
                },
            )
        return issues, semantic_outcome

    def _requires_semantic(self, item: VerificationPipelineItem) -> bool:
        """Return true when this item must pass through semantic verification."""

        return item.item_type in SEMANTICALLY_REQUIRED_ITEM_TYPES and (
            self.semantic_policy.enabled or self.semantic_validator is not None
        )

    def _semantic_unavailable_issue(
        self,
        *,
        item: VerificationPipelineItem,
        message: str,
    ) -> VerificationIssue:
        """Create an explicit issue when semantic verification cannot run."""

        blocking = self.semantic_policy.strict_mode or (
            self.semantic_policy.fallback_behavior == SemanticVerifierUnavailableBehavior.BLOCK
        )
        return VerificationIssue(
            id=f"issue.semantic_verification_unavailable.{item.item_id}",
            category=IssueCategory.SEMANTIC_VERIFICATION_UNAVAILABLE,
            severity=IssueSeverity.CRITICAL if blocking else IssueSeverity.MEDIUM,
            message=message,
            generated_item_id=item.item_id,
            suggested_fallback=(
                FallbackAction.BLOCK_RENDERING if blocking else FallbackAction.MARK_NEEDS_REVIEW
            ),
            validator_name="semantic_faithfulness_validator",
            retryable=True,
        )

    def _build_semantic_audit(
        self,
        items: list[VerificationPipelineItem],
    ) -> SemanticVerificationAudit:
        """Create the initial run-level semantic verification audit payload."""

        required_item_ids = [
            item.item_id
            for item in items
            if item.item_type in SEMANTICALLY_REQUIRED_ITEM_TYPES
            and (self.semantic_policy.enabled or self.semantic_validator is not None)
        ]
        if not required_item_ids:
            return SemanticVerificationAudit()
        return SemanticVerificationAudit(
            enabled=True,
            strict_mode=self.semantic_policy.strict_mode,
            fallback_behavior=self.semantic_policy.fallback_behavior.value,
            status=SemanticVerificationStatus.COMPLETED,
            required_item_ids=required_item_ids,
        )

    def _record_semantic_outcome(
        self,
        audit: SemanticVerificationAudit,
        *,
        item: VerificationPipelineItem,
        outcome: SemanticExecutionOutcome,
    ) -> None:
        """Accumulate per-item semantic execution into the run-level audit."""

        if not outcome.required:
            return
        if outcome.attempted:
            audit.attempted_item_ids.append(item.item_id)
        if outcome.completed:
            audit.completed_item_ids.append(item.item_id)
        if outcome.degraded:
            audit.degraded_item_ids.append(item.item_id)
        if outcome.message:
            audit.messages.append(outcome.message)

    def _finalize_semantic_audit(
        self,
        audit: SemanticVerificationAudit,
        *,
        run_status: VerificationStatus,
    ) -> SemanticVerificationAudit:
        """Finalize semantic audit state after item and run decisions are known."""

        if not audit.enabled:
            return audit
        if audit.degraded_item_ids:
            audit.status = (
                SemanticVerificationStatus.BLOCKED
                if run_status == VerificationStatus.BLOCKED
                else SemanticVerificationStatus.DEGRADED
            )
            return audit
        audit.status = SemanticVerificationStatus.COMPLETED
        return audit

    def _log_semantic_outcome(
        self,
        *,
        run_id: str,
        audit: SemanticVerificationAudit,
    ) -> None:
        """Emit explicit semantic verification runtime logs."""

        if not audit.enabled:
            logger.info(
                "phase6 semantic verification disabled",
                extra={"verification_run_id": run_id},
            )
            return
        log_payload = {
            "verification_run_id": run_id,
            "semantic_status": audit.status.value,
            "required_item_ids": list(audit.required_item_ids),
            "completed_item_ids": list(audit.completed_item_ids),
            "degraded_item_ids": list(audit.degraded_item_ids),
        }
        if audit.status == SemanticVerificationStatus.COMPLETED:
            logger.info("phase6 semantic verification completed", extra=log_payload)
            return
        logger.warning("phase6 semantic verification degraded", extra=log_payload)

    def _persist_item(
        self,
        *,
        verification_run_id: str,
        item: VerificationPipelineItem,
        decision: ItemDecision,
        item_matches: list[ProvenanceMatch],
        issues: list[VerificationIssue],
    ) -> None:
        """Persist item, issues, and provenance through the repository layer."""

        from backend.app.db.repositories.verification_repository import (
            ProvenanceLinkCreate,
            VerificationIssueCreate,
        )

        assert self.repository is not None
        row = self.repository.add_verification_item(
            verification_run_id=verification_run_id,
            item_type=item.item_type,
            item_key=item.item_id,
            generated_text=item.generated_text,
            status=decision.status,
            confidence=item.confidence,
            fallback_action=decision.fallback_action,
            evidence_strength=decision.evidence_strength,
        )
        if issues:
            self.repository.add_issues(
                verification_item_id=row.id,
                issues=[
                    VerificationIssueCreate(
                        category=issue.category,
                        severity=issue.severity,
                        message=issue.message,
                        details_json={
                            "generated_item_id": issue.generated_item_id or item.item_id,
                            "source_item_ids": issue.source_item_ids,
                            "source_bullet_ids": issue.source_bullet_ids,
                            "evidence_strength": issue.evidence_strength.value,
                            "suggested_fallback": issue.suggested_fallback.value,
                            "validator_name": issue.validator_name,
                            "retryable": issue.retryable,
                        },
                    )
                    for issue in issues
                ],
            )
        if item_matches:
            self.repository.add_provenance_links(
                verification_item_id=row.id,
                links=[
                    ProvenanceLinkCreate(
                        source_entity_type=match.source_entity_type,
                        source_entity_id=match.source_entity_id,
                        source_bullet_id=match.source_bullet_id,
                        relation_type=match.relation_type,
                        evidence_strength=match.evidence_strength,
                        matched_tokens_json=list(match.matched_tokens),
                    )
                    for match in item_matches
                ],
            )


def _iter_phase3_items(result: Phase3GenerationResult) -> list[VerificationPipelineItem]:
    """Flatten Phase 3 generated content into verification targets."""

    items: list[VerificationPipelineItem] = []
    if result.summary is not None:
        items.append(
            VerificationPipelineItem(
                item_id="summary",
                item_type="summary",
                generated_text=result.summary.text,
                confidence=result.summary.confidence_score,
            )
        )
    for experience in result.selected_experiences:
        for bullet in experience.generated_bullets:
            items.append(
                VerificationPipelineItem(
                    item_id=bullet.id,
                    item_type="experience_bullet",
                    generated_text=bullet.rewritten_text,
                    confidence=bullet.confidence_score,
                )
            )
    for project in result.selected_projects:
        for bullet in project.generated_bullets:
            items.append(
                VerificationPipelineItem(
                    item_id=bullet.id,
                    item_type="project_bullet",
                    generated_text=bullet.rewritten_text,
                    confidence=bullet.confidence_score,
                )
            )
    for skill in result.skills_to_highlight:
        items.append(_skill_item(skill))
    return items


def _skill_item(skill: GeneratedSkillHighlight) -> VerificationPipelineItem:
    """Create a stable verification item for one skill highlight."""

    normalized = ".".join(skill.skill_name.lower().split())
    return VerificationPipelineItem(
        item_id=f"skill.{normalized}",
        item_type="skill_statement",
        generated_text=skill.skill_name,
        confidence=skill.confidence_score,
    )


def _matches_by_item(matches: list[ProvenanceMatch]) -> dict[str, list[ProvenanceMatch]]:
    """Group provenance matches by generated item key."""

    grouped: dict[str, list[ProvenanceMatch]] = {}
    for match in matches:
        grouped.setdefault(match.generated_item_key, []).append(match)
    return grouped


def _apply_repair_results_to_decisions(
    *,
    item_decisions: list[ItemDecision],
    repair_execution: RepairExecutionResult,
) -> list[ItemDecision]:
    """Reflect actual repair success or failure back into item decisions."""

    result_by_item = {item.item_id: item for item in repair_execution.repaired_item_results}
    repaired = set(repair_execution.repair_audit.repaired_item_ids)
    requires_regen = set(repair_execution.repair_audit.requires_regeneration_item_ids)
    updated: list[ItemDecision] = []
    for decision in item_decisions:
        item_result = result_by_item.get(decision.item_id)
        if item_result is None:
            updated.append(decision)
            continue
        if decision.item_id in repaired:
            updated.append(
                decision.model_copy(
                    update={
                        "status": item_result.status,
                        "outcome": item_result.decision_outcome,
                        "retryable": item_result.retryable,
                        "resolved_by_fallback": True,
                    }
                )
            )
            continue
        if decision.item_id in requires_regen:
            updated.append(
                decision.model_copy(
                    update={
                        "status": VerificationStatus.FAILED,
                        "outcome": VerificationDecisionOutcome.REGENERATE_TARGET,
                        "fallback_action": FallbackAction.REGENERATE_SPECIFIC_ITEM,
                        "retryable": True,
                        "resolved_by_fallback": False,
                        "reasons": [*decision.reasons, "safe_repair_failed_requires_regeneration"],
                    }
                )
            )
            continue
        updated.append(decision)
    return updated


def _job_keywords(verification_input: Phase3VerificationInput) -> list[str]:
    """Extract deterministic keyword checks from normalized job analysis."""

    job_analysis = verification_input.job_analysis
    values: list[str] = []
    for attr in (
        "technical_skills",
        "must_have_requirements",
        "preferred_requirements",
    ):
        raw = getattr(job_analysis, attr, None)
        if raw:
            values.extend(str(value) for value in raw)
    return sorted(set(values), key=str.casefold)


def _strongest_evidence(matches: list[ProvenanceMatch]) -> EvidenceStrength:
    """Resolve strongest evidence strength across provenance links."""

    order = {
        EvidenceStrength.NONE: 0,
        EvidenceStrength.WEAK: 1,
        EvidenceStrength.MODERATE: 2,
        EvidenceStrength.STRONG: 3,
        EvidenceStrength.EXACT: 4,
        EvidenceStrength.VERIFIED: 5,
    }
    if not matches:
        return EvidenceStrength.NONE
    return max((match.evidence_strength for match in matches), key=lambda strength: order[strength])


def _run_fallback_action(actions: list[FallbackAction]) -> FallbackAction:
    """Pick a single rendering-output fallback action from run-level actions."""

    if not actions or actions == [FallbackAction.PASS_AS_IS]:
        return FallbackAction.PASS_AS_IS
    if FallbackAction.BLOCK_RENDERING in actions:
        return FallbackAction.BLOCK_RENDERING
    if FallbackAction.MARK_NEEDS_REVIEW in actions:
        return FallbackAction.MARK_NEEDS_REVIEW
    if FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET in actions:
        return FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET
    return actions[0]


def _summary_status(item_results: list[VerificationItemResult]) -> VerificationStatus | None:
    """Return summary item status when a summary was verified."""

    for item in item_results:
        if item.item_type == "summary":
            return item.status
    return None
