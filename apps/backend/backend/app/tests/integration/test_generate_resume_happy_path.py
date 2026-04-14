from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

from fastapi.testclient import TestClient

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
from backend.app.orchestration.adapters.latex_renderer_adapter import LatexRendererAdapter
from backend.app.orchestration.adapters.ranker_adapter import RankerAdapter
from backend.app.orchestration.adapters.verifier_adapter import VerifierAdapter
from backend.app.orchestration.artifacts import ArtifactManager
from backend.app.orchestration.artifacts.storage_backends import LocalArtifactStorageBackend
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
    strong_backend_job_analysis,
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


class _FailingSummaryService:
    def generate(self, summary_input):
        raise RuntimeError("summary provider unavailable")


class _DeterministicParserAdapter:
    stage_name = StageName.PARSE_JOB_DESCRIPTION

    def execute(self, stage_input, context: StageExecutionContext) -> ParseJobDescriptionOutput:
        analysis = strong_backend_job_analysis()
        return ParseJobDescriptionOutput(
            raw_analysis=ParsedJobAnalysisResponse(
                technical_skills=analysis.technical_skills,
                soft_skills=analysis.soft_skills,
                seniority_level=analysis.seniority_level.value if analysis.seniority_level is not None else None,
                role_type=analysis.role_type.value if analysis.role_type is not None else None,
                industry_domain=analysis.industry_domain,
                key_action_verbs=analysis.key_action_verbs,
                must_have_requirements=analysis.must_have_requirements,
                nice_to_have_requirements=analysis.nice_to_have_requirements,
                company_culture_signals=analysis.company_culture_signals,
            ),
            normalized_analysis=analysis,
        )

    def extract_artifacts(self, stage_output, context: StageExecutionContext):
        return []


class _PassingVerifierAdapter(VerifierAdapter):
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


def test_generate_resume_happy_path_persists_pdf_and_exposes_progress_stream(
    monkeypatch,
    tmp_path: Path,
) -> None:
    profile = strong_backend_engineer_profile()
    profile = profile.model_copy(
        update={
            "personal_profile": profile.personal_profile.model_copy(
                update={
                    "email": "taylor.backend@example.com",
                    "phone": "555-0100",
                    "location": "New York, NY",
                }
            )
        }
    )
    profile_path = tmp_path / "strong_backend_profile.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json", exclude_none=True), indent=2),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    orchestrator = _build_happy_path_orchestrator(artifact_root=artifact_root)
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        ResumeGenerationIdempotencyRegistry(),
    )

    run_id = "run.phase4.happy-path"
    payload = {
        "pipeline_run_id": run_id,
        "source_profile_path": str(profile_path),
        "job_description_text": (
            "Staff Backend Engineer. Build Python APIs on AWS, improve reliability, "
            "mentor engineers, and automate platform delivery with Kubernetes and Terraform."
        ),
        "template_id": "ats_standard",
        "generation_preferences": {
            "target_page_count": 1,
        },
        "persist_intermediate_artifacts": True,
    }

    with TestClient(app) as client:
        response = client.post("/api/generate-resume", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == run_id
        assert body["status"] in {"succeeded", "succeeded_with_warnings"}
        assert body["selected_experiences"]
        assert body["selected_skills"]
        assert body["completed_phases"] == [
            "load_source_profile",
            "normalize_source_data",
            "ingest_job_description",
            "parse_job_description",
            "rank_select_evidence",
            "generate_structured_content",
            "verify_generated_content",
            "render_deterministic_latex",
            "compile_pdf",
            "persist_artifacts",
        ]
        assert body["run_metadata"]["selected_experience_count"] >= 1
        assert body["run_metadata"]["selected_skill_count"] >= 1
        assert body["run_metadata"]["template_id"] == "ats_standard"
        assert body["run_metadata"]["page_length_pages"] == 1
        assert any(output["kind"] == "pdf" for output in body["available_outputs"])
        assert any(output["kind"] == "structured_json" for output in body["available_outputs"])

        assert body["final_file_reference"].startswith(f"/api/pipeline-runs/{run_id}/artifacts/")
        pdf_output = next(output for output in body["available_outputs"] if output["kind"] == "pdf")
        artifact_response = client.get(pdf_output["reference"])
        assert artifact_response.status_code == 200
        assert artifact_response.headers["content-type"].startswith("application/pdf")

        history = DEFAULT_PIPELINE_EVENT_EMITTER.history(run_id)
        assert stream_pipeline_progress(run_id).media_type == "text/event-stream"
        assert any(event.event_type.value == "run_started" for event in history)
        assert any(event.event_type.value == "stage_started" for event in history)
        assert any(event.event_type.value == "stage_completed" for event in history)
        assert any(event.event_type.value == "run_completed" for event in history)
        assert any(
            event.stage_name is not None
            and event.stage_name.value == "compile_pdf"
            and event.metadata.get("phase_id") == "compile_pdf"
            and event.metadata.get("phase_label") == "compile pdf"
            for event in history
        )

    # Manual verification checklist:
    # - Start backend on the expected API port and frontend on :5173.
    # - Paste the sample JD used in this test and click Generate once.
    # - Confirm progress phases advance from pending to completed without retries.
    # - Confirm the network tab shows one POST /api/generate-resume and one SSE /api/pipeline-runs/{run_id}/events.
    # - Confirm the final result includes selected evidence and a downloadable PDF.


def test_generate_resume_degrades_cleanly_when_summary_generation_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    profile = strong_backend_engineer_profile()
    profile_path = tmp_path / "strong_backend_profile.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json", exclude_none=True), indent=2),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    orchestrator = _build_happy_path_orchestrator(
        artifact_root=artifact_root,
        summary_service=_FailingSummaryService(),
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
                "pipeline_run_id": "run.phase5.summary-omitted",
                "source_profile_path": str(profile_path),
                "job_description_text": "Staff Backend Engineer. Build Python APIs on AWS and improve reliability.",
                "template_id": "ats_standard",
                "generation_preferences": {"target_page_count": 1},
                "persist_intermediate_artifacts": True,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"succeeded", "succeeded_with_warnings"}
        assert body["run_metadata"]["summary_state"] == "omitted"
        assert any(output["kind"] == "pdf" for output in body["available_outputs"])
        assert any(output["kind"] == "structured_json" for output in body["available_outputs"])


def _build_happy_path_orchestrator(*, artifact_root: Path, summary_service=None):
    summary_service = summary_service or SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Staff backend engineer building Python platform services on AWS with a focus on reliability and delivery.","evidence_ids_used":["fixture.backend.exp.current"],"themes_used":["Improve reliability and delivery for platform services"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )
    bullet_service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Architected AWS and Kubernetes platform services with Terraform, reducing deployment time by 68%.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"condensed"}',
                '{"rewritten_text":"Led Python and PostgreSQL API reliability work, reducing Sev-1 incidents by 42% and improving p95 latency by 33%.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"light_rewrite"}',
                '{"rewritten_text":"Owned CI/CD automation and self-serve provisioning used by 14 engineering teams.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"light_rewrite"}',
                '{"rewritten_text":"Built Go payment services with Redis caching, increasing checkout throughput by 27%.","evidence_ids_used":["fixture.backend.exp.prev"],"rewrite_strategy":"condensed"}',
                '{"rewritten_text":"Built Python APIs and React workflows that cut environment setup time by 80%.","evidence_ids_used":["fixture.backend.project"],"rewrite_strategy":"condensed"}',
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )
    compile_adapter = __import__(
        "backend.app.orchestration.adapters.pdf_compile_adapter",
        fromlist=["PdfCompileAdapter"],
    ).PdfCompileAdapter(
        compile_func=lambda **kwargs: _compile_test_pdf(artifact_root=artifact_root, **kwargs),
        artifact_manager=ArtifactManager(LocalArtifactStorageBackend(artifact_root)),
    )
    registry = StageRegistry(
        adapters=[
            _DeterministicParserAdapter(),
            RankerAdapter(),
            GeneratorAdapter(
                phase3_service=Phase3Service(
                    summary_service=summary_service,
                    bullet_rewrite_service=bullet_service,
                )
            ),
            _PassingVerifierAdapter(
                orchestrator_factory=lambda: VerificationOrchestrator(
                    semantic_validator=None,
                    semantic_policy=SemanticVerificationPolicy(
                        enabled=False,
                        strict_mode=False,
                        fallback_behavior=SemanticVerifierUnavailableBehavior.MARK_NEEDS_REVIEW,
                    ),
                )
            ),
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
    pdf_path.write_bytes(b"%PDF-1.4\n% happy path integration test\n")
    log_path.write_text("pdflatex stubbed for integration test\n", encoding="utf-8")

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
