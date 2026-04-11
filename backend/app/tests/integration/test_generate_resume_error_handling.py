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

from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import OrchestrationError
from resume_optimizer.app import app


class _FailingOrchestrator:
    def run(self, _request):
        raise OrchestrationError(
            "provider leaked secret sk-test-123 and raw resume text",
            failure_type=OrchestrationFailureType.GENERATION_PROVIDER,
            stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
            run_id="run.safe-error-test",
        )


def test_generate_resume_exposes_only_safe_error_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        _FailingOrchestrator(),
    )

    response = TestClient(app).post(
        "/api/generate-resume",
        json={
            "source_profile_path": str((Path.cwd() / "data" / "master_profile.example.json").resolve()),
            "job_description_text": "Build reliable Python APIs.",
            "template_id": "ats_standard",
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["message"] == "Structured resume generation is temporarily unavailable."
    assert detail["failure_type"] == "generation_provider"
    assert detail["failure_category"] == "upstream_ai_error"
    assert detail["stage_name"] == "generate_structured_content"
    assert "sk-test-123" not in str(detail)
    assert "raw resume text" not in str(detail)
