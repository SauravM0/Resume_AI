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

from backend.app.metrics.storage import JsonlStageMetricsStore
from backend.app.schemas.api_responses import GenerateResumeVerificationResponse
from backend.app.schemas.verification import (
    Phase4RenderingOutput,
    VerificationReport,
)
from backend.app.services.verification.types import (
    FallbackAction,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.app import app
from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.phase2_models import JobAnalysisInput, Phase2SelectionResult
from resume_optimizer.phase3_models import (
    GenerationMetadata,
    Phase3AssemblerInput,
    Phase3GenerationResult,
)
from resume_optimizer.ranking_models import RankingResponse


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


class _MockPipelineService:
    def generate_resume_with_verification(self, request: Phase3AssemblerInput) -> GenerateResumeVerificationResponse:
        phase3_result = Phase3GenerationResult(
            metadata=GenerationMetadata(source_profile_id=request.source_profile.id),
        )
        report = VerificationReport(
            verification_run_id="verify.metrics.route",
            source_profile_id=request.source_profile.id,
            status=VerificationStatus.PASSED,
            item_results=[],
            fallback_actions=[FallbackAction.PASS_AS_IS],
            decision_outcome=VerificationDecisionOutcome.PASS,
            renderable=True,
            retryable=False,
        )
        return GenerateResumeVerificationResponse(
            status="verification_passed",
            pipeline_run_id="pipeline.metrics.route",
            verification_run_id="verify.metrics.route",
            phase3_result=phase3_result,
            verification_report=report,
            rendering_output=Phase4RenderingOutput(
                source_profile_id=request.source_profile.id,
                verified_result=phase3_result,
                verification_report=report,
                renderable=True,
                fallback_action=FallbackAction.PASS_AS_IS,
            ),
            warnings=[],
        )


def test_route_records_request_boundary_metrics(tmp_path: Path, monkeypatch) -> None:
    store = JsonlStageMetricsStore(tmp_path / "stage_metrics.jsonl")
    monkeypatch.setattr("backend.app.metrics.storage.DEFAULT_STAGE_METRICS_STORE", store)
    monkeypatch.setattr(
        "backend.app.api.routes.resume.DEFAULT_RESUME_PIPELINE_SERVICE",
        _MockPipelineService(),
    )

    response = TestClient(app).post(
        "/api/generate-resume-with-verification",
        json=_request().model_dump(mode="json", exclude_none=True, exclude_computed_fields=True),
    )

    assert response.status_code == 200
    records = store.load()
    assert [record.stage_name for record in records] == ["request_validation", "response_packaging"]
    assert all(record.request_id is not None for record in records)
    assert records[0].output_metadata["source_profile_id"] == "master.alex-morgan"
    assert "source_profile" not in records[0].output_metadata
    assert records[1].run_id == "pipeline.metrics.route"
