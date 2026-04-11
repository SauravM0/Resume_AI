from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.schemas.api_responses import GenerateResumeVerificationResponse
from backend.app.schemas.verification import (
    Phase4RenderingOutput,
    VerificationIssue,
    VerificationItemResult,
    VerificationReport,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.app import app
from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.phase2_models import JobAnalysisInput, Phase2SelectionResult
from resume_optimizer.phase3_models import (
    GenerationMetadata,
    Phase3AssemblerInput,
    Phase3GenerationResult,
)
from resume_optimizer.ranking_models import RankingResponse
from resume_optimizer.loaders import load_and_normalize_master_profile


def _request() -> Phase3AssemblerInput:
    profile = load_and_normalize_master_profile("data/master_profile.example.json")
    job_analysis = NormalizedJobAnalysis(
        role_type="individual_contributor",
        seniority_level="senior",
        technical_skills=["Python"],
        must_have_requirements=["Build backend APIs."],
    )
    return Phase3AssemblerInput(
        job_analysis=job_analysis,
        phase2_selection=Phase2SelectionResult(
            job_analysis=JobAnalysisInput.model_validate(job_analysis.model_dump()),
            candidate_profile_id=profile.id,
        ),
        phase2_ranking=RankingResponse(),
        source_profile=profile,
    )


def _api_response(status: VerificationStatus) -> GenerateResumeVerificationResponse:
    source_profile_id = "master.example"
    phase3_result = Phase3GenerationResult(
        metadata=GenerationMetadata(source_profile_id=source_profile_id),
    )
    issues: list[VerificationIssue] = []
    fallback_action = FallbackAction.PASS_AS_IS
    item_status = VerificationStatus.PASSED
    renderable = status != VerificationStatus.FAILED
    if status == VerificationStatus.PASSED_WITH_WARNINGS:
        issues = [
            VerificationIssue(
                id="issue.warning.gen",
                category=IssueCategory.PROVENANCE_WEAK,
                severity=IssueSeverity.MEDIUM,
                message="Verification passed with a reviewable warning.",
                generated_item_id="summary",
                validator_name="semantic_faithfulness_validator",
            )
        ]
        fallback_action = FallbackAction.MARK_NEEDS_REVIEW
        item_status = VerificationStatus.PASSED_WITH_WARNINGS
    if status == VerificationStatus.FAILED:
        issues = [
            VerificationIssue(
                id="issue.failed.gen",
                category=IssueCategory.UNSUPPORTED_TOOL,
                severity=IssueSeverity.HIGH,
                message="Unsupported generated tool claim.",
                generated_item_id="summary",
                validator_name="tool_technology_validator",
            )
        ]
        fallback_action = FallbackAction.REGENERATE_SPECIFIC_ITEM
        item_status = VerificationStatus.FAILED

    report = VerificationReport(
        verification_run_id=f"verify.{status.value}",
        source_profile_id=source_profile_id,
        status=status,
        item_results=[
            VerificationItemResult(
                item_id="summary",
                item_type="summary",
                status=item_status,
                evidence_strength=EvidenceStrength.STRONG,
                issues=issues,
                fallback_action=fallback_action,
                decision_outcome=(
                    VerificationDecisionOutcome.PASS
                    if item_status == VerificationStatus.PASSED
                    else (
                        VerificationDecisionOutcome.PASS_WITH_WARNINGS
                        if item_status == VerificationStatus.PASSED_WITH_WARNINGS
                        else VerificationDecisionOutcome.REGENERATE_TARGET
                    )
                ),
                retryable=status == VerificationStatus.FAILED,
            )
        ],
        fallback_actions=[fallback_action],
        decision_outcome=(
            VerificationDecisionOutcome.PASS
            if status == VerificationStatus.PASSED
            else (
                VerificationDecisionOutcome.PASS_WITH_WARNINGS
                if status == VerificationStatus.PASSED_WITH_WARNINGS
                else VerificationDecisionOutcome.REGENERATE_TARGET
            )
        ),
        renderable=renderable,
        retryable=status == VerificationStatus.FAILED,
    )
    return GenerateResumeVerificationResponse(
        status={
            VerificationStatus.PASSED: "verification_passed",
            VerificationStatus.PASSED_WITH_WARNINGS: "verification_passed_with_warnings",
            VerificationStatus.FAILED: "verification_failed",
        }[status],
        pipeline_run_id=f"pipeline.{status.value}",
        verification_run_id=f"verify.{status.value}",
        phase3_result=phase3_result,
        verification_report=report,
        rendering_output=Phase4RenderingOutput(
            source_profile_id=source_profile_id,
            verified_result=phase3_result,
            verification_report=report,
            renderable=renderable,
            fallback_action=fallback_action,
        ),
        warnings=[issue.message for issue in issues],
    )


class _MockPipelineService:
    def __init__(self, status: VerificationStatus) -> None:
        self.status = status
        self.seen_request = None

    def generate_resume_with_verification(self, request: Phase3AssemblerInput):
        self.seen_request = request
        return _api_response(self.status)


def test_generate_resume_with_verification_returns_pass(monkeypatch) -> None:
    service = _MockPipelineService(VerificationStatus.PASSED)
    monkeypatch.setattr(
        "backend.app.api.routes.resume.DEFAULT_RESUME_PIPELINE_SERVICE",
        service,
    )

    response = TestClient(app).post(
        "/api/generate-resume-with-verification",
        json=_request().model_dump(mode="json", exclude_none=True, exclude_computed_fields=True),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "verification_passed"
    assert payload["rendering_output"]["renderable"] is True
    assert "source_profile" not in payload
    assert service.seen_request is not None


def test_generate_resume_with_verification_returns_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.api.routes.resume.DEFAULT_RESUME_PIPELINE_SERVICE",
        _MockPipelineService(VerificationStatus.PASSED_WITH_WARNINGS),
    )

    response = TestClient(app).post(
        "/api/generate-resume-with-verification",
        json=_request().model_dump(mode="json", exclude_none=True, exclude_computed_fields=True),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "verification_passed_with_warnings"
    assert payload["warnings"] == ["Verification passed with a reviewable warning."]
    assert payload["rendering_output"]["fallback_action"] == "mark_needs_review"


def test_generate_resume_with_verification_returns_structured_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.api.routes.resume.DEFAULT_RESUME_PIPELINE_SERVICE",
        _MockPipelineService(VerificationStatus.FAILED),
    )

    response = TestClient(app).post(
        "/api/generate-resume-with-verification",
        json=_request().model_dump(mode="json", exclude_none=True, exclude_computed_fields=True),
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["status"] == "verification_failed"
    assert detail["verification_report"]["status"] == "failed"
    assert detail["verification_report"]["item_results"][0]["issues"][0]["category"] == "unsupported_tool"
