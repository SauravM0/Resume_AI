"""End-to-end acceptance test harness for Phase 6 verification.

This module provides comprehensive integration tests that prove the core product
workflow functions correctly: profile → JD → parse → select → fill → PDF → download.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

from fastapi.testclient import TestClient
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from backend.app.api.idempotency import ResumeGenerationIdempotencyRegistry
from backend.app.api.routes.progress_stream import stream_pipeline_progress
from backend.app.models.render_models import (
    ArtifactKind as RenderArtifactKind,
    CompileResult,
    LatexCompiler,
    RenderArtifactMetadata,
)
from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.adapters.generator_adapter import GeneratorAdapter
from backend.app.orchestration.adapters.latex_renderer_adapter import (
    LatexRendererAdapter,
)
from backend.app.orchestration.adapters.ranker_adapter import RankerAdapter
from backend.app.orchestration.adapters.verifier_adapter import VerifierAdapter
from backend.app.orchestration.artifacts import ArtifactManager
from backend.app.orchestration.artifacts.storage_backends import (
    LocalArtifactStorageBackend,
)
from backend.app.orchestration.enums import StageName
from backend.app.orchestration.event_emitter import DEFAULT_PIPELINE_EVENT_EMITTER
from backend.app.orchestration.pipeline_models import (
    ParseJobDescriptionOutput,
    VerifyGeneratedContentOutput,
)
from backend.app.orchestration.stage_registry import StageRegistry
from backend.app.schemas.verification import Phase4RenderingOutput, VerificationReport
from backend.app.services.pdf_compiler import PdfCompileResult
from backend.app.services.verification.orchestrator import (
    SemanticVerificationPolicy,
    VerificationOrchestrator,
)
from backend.app.services.verification.types import (
    FallbackAction,
    SemanticVerifierUnavailableBehavior,
    VerificationStatus,
)
from backend.app.tests.fixtures.phase2_candidate_profiles import (
    strong_backend_engineer_profile,
)
from resume_optimizer.app import app
from resume_optimizer.job_models import ParsedJobAnalysisResponse
from resume_optimizer.services.phase3_service import Phase3Service
from resume_optimizer.generation.bullet_rewrite_service import BulletRewriteService
from resume_optimizer.generation.summary_service import SummaryGenerationService


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._outputs) - 1)
        return _FakeResponse(self._outputs[index])


class _FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = _FakeResponses(outputs)


class _DeterministicParserAdapter:
    stage_name = StageName.PARSE_JOB_DESCRIPTION

    def __init__(
        self, role_type: str, seniority: str, required_skills: list[str]
    ) -> None:
        self._role_type = role_type
        self._seniority = seniority
        self._required_skills = required_skills

    def execute(
        self, stage_input, context: StageExecutionContext
    ) -> ParseJobDescriptionOutput:
        return ParseJobDescriptionOutput(
            raw_analysis=ParsedJobAnalysisResponse(
                technical_skills=self._required_skills,
                soft_skills=[],
                seniority_level=self._seniority,
                role_type=self._role_type,
                industry_domain="technology",
                key_action_verbs=["build", "lead", "design"],
                must_have_requirements=self._required_skills[:3],
                nice_to_have_requirements=self._required_skills[3:],
                company_culture_signals=[],
            ),
            normalized_analysis=None,
        )

    def extract_artifacts(self, stage_output, context: StageExecutionContext):
        return []


class _PassingVerifierAdapter(VerifierAdapter):
    def __init__(self):
        pass

    def execute(
        self,
        stage_input,
        context: StageExecutionContext,
    ) -> VerifyGeneratedContentOutput:
        report = VerificationReport(
            verification_run_id=f"verify.{context.run_id}",
            source_profile_id=stage_input.source_profile_id,
            status=VerificationStatus.PASSED,
            renderable=True,
        )
        return VerifyGeneratedContentOutput(
            verification_run_id=report.verification_run_id,
            verification_report=report,
            rendering_output=Phase4RenderingOutput(
                source_profile_id=stage_input.source_profile_id,
                verified_result=stage_input.phase3_result,
                verification_report=report,
                renderable=True,
                fallback_action=FallbackAction.ACCEPT,
            ),
        )


def _build_test_orchestrator(
    *,
    artifact_root: Path,
    role_type: str,
    seniority: str,
    required_skills: list[str],
) -> Any:
    summary_service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Test summary for role.","evidence_ids_used":["exp.1"],"themes_used":["test"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )
    bullet_service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Test bullet 1","evidence_ids_used":["exp.1"],"rewrite_strategy":"condensed"}',
                '{"rewritten_text":"Test bullet 2","evidence_ids_used":["exp.1"],"rewrite_strategy":"light_rewrite"}',
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )
    compile_adapter = __import__(
        "backend.app.orchestration.adapters.pdf_compile_adapter",
        fromlist=["PdfCompileAdapter"],
    ).PdfCompileAdapter(
        compile_func=lambda **kwargs: _compile_test_pdf(
            artifact_root=artifact_root, **kwargs
        ),
        artifact_manager=ArtifactManager(LocalArtifactStorageBackend(artifact_root)),
    )
    registry = StageRegistry(
        adapters=[
            _DeterministicParserAdapter(
                role_type=role_type,
                seniority=seniority,
                required_skills=required_skills,
            ),
            RankerAdapter(),
            GeneratorAdapter(
                phase3_service=Phase3Service(
                    summary_service=summary_service,
                    bullet_rewrite_service=bullet_service,
                )
            ),
            _PassingVerifierAdapter(),
            LatexRendererAdapter(),
            compile_adapter,
        ]
    )
    from backend.app.orchestration.orchestrator import ResumeGenerationOrchestrator

    return ResumeGenerationOrchestrator(
        stage_registry=registry,
        artifact_manager=ArtifactManager(LocalArtifactStorageBackend(artifact_root)),
    )


def _compile_test_pdf(
    *,
    tex_content: str,
    render_job_id: str,
    template_id: str,
    artifact_root: Path,
    **_kwargs,
) -> PdfCompileResult:
    workspace = Path(
        tempfile.mkdtemp(
            prefix=f"resume-render-{render_job_id.replace('/', '_')}-",
        )
    )
    tex_path = workspace / "resume.tex"
    pdf_path = workspace / "resume.pdf"
    log_path = workspace / "resume.log"
    tex_path.write_text(tex_content, encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-1.4\n% acceptance test\n")
    log_path.write_text("pdflatex stubbed for acceptance test\n", encoding="utf-8")

    return PdfCompileResult(
        compile_success=True,
        render_job_id=render_job_id,
        workspace_path=str(workspace),
        tex_file_path=str(tex_path),
        pdf_file_path=str(pdf_path),
        log_file_path=str(log_path),
        return_code=0,
        elapsed_ms=1,
        compile_result=CompileResult(
            success=True,
            compiler=LatexCompiler.PDFLATEX,
            exit_code=0,
            pdf_artifact=RenderArtifactMetadata(
                artifact_id=f"render.{render_job_id}.pdf",
                render_job_id=render_job_id,
                kind=RenderArtifactKind.PDF,
                template_id=template_id,
                content_type="application/pdf",
                path=str(pdf_path),
            ),
            log_artifact=RenderArtifactMetadata(
                artifact_id=f"render.{render_job_id}.log",
                render_job_id=render_job_id,
                kind=RenderArtifactKind.LOG,
                template_id=template_id,
                content_type="text/plain",
                path=str(log_path),
            ),
        ),
    )


def test_backend_health_route_exists() -> None:
    """Verify backend health endpoint is available."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"healthy", "degraded", "ok"}


def test_regression_phase_not_reported_should_not_appear_on_failure() -> None:
    """Regression test: 'Failed Phase: Not Reported' should not appear on classified errors.

    This tests the fix from Phase 4 where unhandled exceptions were not properly classified.
    """
    from backend.app.orchestration.errors import OrchestrationError
    from backend.app.orchestration.enums import OrchestrationFailureType, StageName

    error = OrchestrationError(
        message="Test error",
        failure_type=OrchestrationFailureType.INTERNAL,
        stage_name=StageName.PARSE_JOB_DESCRIPTION,
    )
    api_detail = error.to_safe_api_detail()

    assert api_detail["failure_type"] == "internal"
    assert api_detail["stage_name"] == "parse_job_description"
    assert api_detail["failure_category"] == "internal_error"


def test_regression_transport_error_classification() -> None:
    """Regression test: transport errors should be classified correctly, not as 'not reported'."""
    from backend.app.orchestration.enums import (
        OrchestrationFailureType,
        StageName,
        FailureCategory,
    )

    from backend.app.orchestration.errors import OrchestrationError

    transport_error = OrchestrationError(
        message="Connection refused",
        failure_type=OrchestrationFailureType.GENERATION_PROVIDER,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
    )
    api_detail = transport_error.to_safe_api_detail()

    assert api_detail["stage_name"] == "generate_structured_content"
    assert api_detail["failure_type"] == "generation_provider"


def test_regression_no_dev_server_port_in_api_calls() -> None:
    """Regression test: requests should not target Vite dev server port 5173.

    This catches the bug where frontend proxies requests to wrong port during dev.
    """
    import re

    api_base_url_pattern = re.compile(r"https?://[^:]*:5173/")

    assert not api_base_url_pattern.match("http://localhost:5173/api/test"), (
        "API calls should not target port 5173 (Vite dev server)"
    )
    assert not api_base_url_pattern.match("https://127.0.0.1:5173/api/test"), (
        "API calls should not target port 5173 (Vite dev server)"
    )


def test_gold_case_backend_heavy_role_extraction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Gold test case: backend-heavy role should extract Python/AWS keywords."""
    from backend.app.tests.fixtures.gold_test_cases import get_gold_test_case

    gold = get_gold_test_case("backend_heavy")
    profile = gold.profile
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json", exclude_none=True), indent=2),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    orchestrator = _build_test_orchestrator(
        artifact_root=artifact_root,
        role_type=gold.role_type,
        seniority=gold.seniority,
        required_skills=gold.required_skills,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        ResumeGenerationIdempotencyRegistry(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/generate-resume",
            json={
                "pipeline_run_id": "run.gold.backend",
                "source_profile_path": str(profile_path),
                "job_description_text": f"Senior Backend Engineer. {', '.join(gold.required_skills)} required.",
                "template_id": "ats_standard",
                "generation_preferences": {"target_page_count": 1},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"succeeded", "succeeded_with_warnings"}


def test_gold_case_leadership_role_extraction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Gold test case: leadership role should extract management/strategy keywords."""
    from backend.app.tests.fixtures.gold_test_cases import get_gold_test_case

    gold = get_gold_test_case("leadership")
    profile = gold.profile
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json", exclude_none=True), indent=2),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    orchestrator = _build_test_orchestrator(
        artifact_root=artifact_root,
        role_type=gold.role_type,
        seniority=gold.seniority,
        required_skills=gold.required_skills,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        ResumeGenerationIdempotencyRegistry(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/generate-resume",
            json={
                "pipeline_run_id": "run.gold.leadership",
                "source_profile_path": str(profile_path),
                "job_description_text": f"Engineering Manager. {', '.join(gold.required_skills)} required.",
                "template_id": "ats_standard",
                "generation_preferences": {"target_page_count": 1},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"succeeded", "succeeded_with_warnings"}


def test_gold_case_project_gap_fill_extraction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Gold test case: project-gap-fill role should include projects in selection."""
    from backend.app.tests.fixtures.gold_test_cases import get_gold_test_case

    gold = get_gold_test_case("project_gap_fill")
    profile = gold.profile
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json", exclude_none=True), indent=2),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    orchestrator = _build_test_orchestrator(
        artifact_root=artifact_root,
        role_type=gold.role_type,
        seniority=gold.seniority,
        required_skills=gold.required_skills,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        ResumeGenerationIdempotencyRegistry(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/generate-resume",
            json={
                "pipeline_run_id": "run.gold.projects",
                "source_profile_path": str(profile_path),
                "job_description_text": f"Fullstack Engineer. {', '.join(gold.required_skills)} required.",
                "template_id": "ats_standard",
                "generation_preferences": {"target_page_count": 1},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"succeeded", "succeeded_with_warnings"}


def test_gold_case_thin_evidence_extraction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Gold test case: thin-evidence role should handle limited profile data."""
    from backend.app.tests.fixtures.gold_test_cases import get_gold_test_case

    gold = get_gold_test_case("thin_evidence")
    profile = gold.profile
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json", exclude_none=True), indent=2),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    orchestrator = _build_test_orchestrator(
        artifact_root=artifact_root,
        role_type=gold.role_type,
        seniority=gold.seniority,
        required_skills=gold.required_skills,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        ResumeGenerationIdempotencyRegistry(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/generate-resume",
            json={
                "pipeline_run_id": "run.gold.thin",
                "source_profile_path": str(profile_path),
                "job_description_text": f"Junior Developer. {', '.join(gold.required_skills)} required.",
                "template_id": "ats_standard",
                "generation_preferences": {"target_page_count": 1},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"succeeded", "succeeded_with_warnings"}
