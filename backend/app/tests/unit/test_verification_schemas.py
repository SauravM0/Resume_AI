from __future__ import annotations

from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.schemas.verification import (
    GeneratedBullet,
    Phase3VerificationInput,
    Phase4RenderingOutput,
    ProvenanceLink,
    VerificationIssue,
    VerificationItemResult,
    VerificationReport,
)
from backend.app.services.verification.contracts import (
    Phase3VerificationInput as ContractPhase3VerificationInput,
)
from backend.app.services.verification.contracts import (
    Phase4RenderingOutput as ContractPhase4RenderingOutput,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.models import ItemType
from resume_optimizer.phase3_models import (
    GenerationMetadata,
    Phase3GenerationPayload,
    Phase3GenerationResult,
    Phase3RoleContext,
    Phase3ValidationMetadata,
    SupportLevel,
)

DATA_DIR = REPO_ROOT / "data"


def _build_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type="individual_contributor",
        seniority_level="senior",
        technical_skills=["Python", "PostgreSQL"],
        must_have_requirements=["Build backend APIs"],
    )


def _build_phase3_payload(profile_id: str) -> Phase3GenerationPayload:
    return Phase3GenerationPayload(
        role_context=Phase3RoleContext(
            target_role_title="Senior Backend Engineer",
            must_have_skills=["Python", "PostgreSQL"],
        ),
        validation_metadata=Phase3ValidationMetadata(profile_id=profile_id),
    )


def _build_phase3_result(profile_id: str) -> Phase3GenerationResult:
    return Phase3GenerationResult(
        metadata=GenerationMetadata(source_profile_id=profile_id),
    )


def test_verification_enums_are_stable_string_values() -> None:
    assert VerificationStatus.PASSED.value == "passed"
    assert IssueSeverity.CRITICAL.value == "critical"
    assert IssueSeverity.HIGH.value == "high"
    assert IssueCategory.UNSUPPORTED_METRIC.value == "unsupported_metric"
    assert EvidenceStrength.VERIFIED.value == "verified"
    assert FallbackAction.BLOCK_RENDERING.value == "block_rendering"
    assert VerificationDecisionOutcome.REPAIR_AND_PASS.value == "repair_and_pass"
    assert VerificationStatus("needs_retry") is VerificationStatus.NEEDS_RETRY


def test_generated_bullet_requires_source_bullet_provenance() -> None:
    with pytest.raises(ValidationError, match="source_bullet_ids must be represented"):
        GeneratedBullet(
            id="gen.bullet.1",
            source_item_id="exp.acme",
            source_item_type=ItemType.EXPERIENCE,
            source_bullet_ids=["bullet.acme.1"],
            text="Built APIs with Python and PostgreSQL.",
            claimed_tools=["Python", "PostgreSQL"],
            provenance=[
                ProvenanceLink(
                    source_item_id="exp.acme",
                    source_item_type=ItemType.EXPERIENCE,
                    evidence_strength=EvidenceStrength.STRONG,
                    support_level=SupportLevel.DIRECT,
                )
            ],
        )


def test_verification_item_result_rejects_failed_status_without_blocking_issue() -> None:
    warning_issue = VerificationIssue(
        id="issue.warning.1",
        category=IssueCategory.PROVENANCE_WEAK,
        severity=IssueSeverity.MEDIUM,
        message="Evidence is present but weak.",
        generated_item_id="gen.bullet.1",
        evidence_strength=EvidenceStrength.WEAK,
        validator_name="provenance_strength",
    )

    with pytest.raises(ValidationError, match="failed verification items require"):
        VerificationItemResult(
            item_id="gen.bullet.1",
            item_type="bullet",
            status=VerificationStatus.FAILED,
            evidence_strength=EvidenceStrength.WEAK,
            issues=[warning_issue],
            fallback_action=FallbackAction.REQUIRE_HUMAN_REVIEW,
        )


def test_verification_report_blocks_rendering_for_critical_unsupported_metric() -> None:
    critical_issue = VerificationIssue(
        id="issue.metric.1",
        category=IssueCategory.UNSUPPORTED_METRIC,
        severity=IssueSeverity.CRITICAL,
        message="Generated metric is not supported by source evidence.",
        generated_item_id="gen.bullet.1",
        source_item_ids=["exp.acme"],
        evidence_strength=EvidenceStrength.NONE,
        suggested_fallback=FallbackAction.BLOCK_RENDERING,
        validator_name="metric_support",
    )

    report = VerificationReport(
        verification_run_id="verify.run.1",
        source_profile_id="master.example",
        status=VerificationStatus.BLOCKED,
        issues=[critical_issue],
        fallback_actions=[FallbackAction.BLOCK_RENDERING],
        deterministic_validator_names=["metric_support"],
        renderable=False,
    )

    assert report.status is VerificationStatus.BLOCKED
    assert report.fallback_actions == [FallbackAction.BLOCK_RENDERING]


def test_phase3_to_phase4_input_contract_requires_profile_alignment() -> None:
    profile = load_and_normalize_master_profile(DATA_DIR / "master_profile.example.json")

    handoff = Phase3VerificationInput(
        source_profile_id=profile.id,
        job_analysis=_build_job_analysis(),
        source_profile=profile,
        generation_payload=_build_phase3_payload(profile.id),
        phase3_result=_build_phase3_result(profile.id),
    )

    assert handoff.source_profile_id == profile.id
    assert ContractPhase3VerificationInput is Phase3VerificationInput

    with pytest.raises(ValidationError, match="source_profile_id must match source_profile.id"):
        Phase3VerificationInput(
            source_profile_id="master.other",
            job_analysis=_build_job_analysis(),
            source_profile=profile,
            generation_payload=_build_phase3_payload(profile.id),
            phase3_result=_build_phase3_result(profile.id),
        )


def test_phase4_rendering_output_requires_report_gate_alignment() -> None:
    result = _build_phase3_result("master.example")
    report = VerificationReport(
        verification_run_id="verify.run.1",
        source_profile_id="master.example",
        status=VerificationStatus.PASSED,
        renderable=True,
    )

    output = Phase4RenderingOutput(
        source_profile_id="master.example",
        verified_result=result,
        verification_report=report,
        renderable=True,
    )

    assert output.renderable is True
    assert output.fallback_action is FallbackAction.ACCEPT
    assert ContractPhase4RenderingOutput is Phase4RenderingOutput

    with pytest.raises(ValidationError, match="renderable must match verification_report.renderable"):
        Phase4RenderingOutput(
            source_profile_id="master.example",
            verified_result=result,
            verification_report=report,
            renderable=False,
        )
