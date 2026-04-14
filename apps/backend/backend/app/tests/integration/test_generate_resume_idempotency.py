from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event
from time import sleep

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.api.idempotency import ResumeGenerationIdempotencyRegistry
from backend.app.orchestration.enums import PipelineStatus
from backend.app.orchestration.result_builder import GenerateResumePipelineResponse
from resume_optimizer.app import app
from resume_optimizer.loaders import load_and_normalize_master_profile


def _request_payload(*, job_description_text: str = "Build reliable Python APIs.", profile=None) -> dict[str, object]:
    source_profile = profile or load_and_normalize_master_profile("data/master_profile.example.json")
    return {
        "source_profile": source_profile.model_dump(mode="json", exclude_none=True),
        "job_description_text": job_description_text,
        "template_id": "ats_standard",
        "persist_intermediate_artifacts": True,
    }


class _CountingOrchestrator:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, request):
        self.calls += 1
        return GenerateResumePipelineResponse(
            run_id=request.pipeline_run_id,
            status=PipelineStatus.SUCCEEDED,
            warnings=[],
            available_outputs=[],
            final_file_reference="artifacts/resume.pdf",
            artifact_manifest=[],
            stage_events=[],
        )


class _BlockingOrchestrator:
    def __init__(self) -> None:
        self.calls = 0
        self.started = Event()
        self.release = Event()

    def run(self, request):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)
        sleep(0.1)
        return GenerateResumePipelineResponse(
            run_id=request.pipeline_run_id,
            status=PipelineStatus.SUCCEEDED,
            warnings=[],
            available_outputs=[],
            final_file_reference="artifacts/resume.pdf",
            artifact_manifest=[],
            stage_events=[],
        )


def test_completed_duplicate_reuses_recent_result(monkeypatch) -> None:
    orchestrator = _CountingOrchestrator()
    registry = ResumeGenerationIdempotencyRegistry()
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        registry,
    )
    client = TestClient(app)

    first = client.post(
        "/api/generate-resume",
        json=_request_payload(),
        headers={"Idempotency-Key": "resume-dup-1"},
    )
    second = client.post(
        "/api/generate-resume",
        json=_request_payload(),
        headers={"Idempotency-Key": "resume-dup-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    assert first.headers["X-Idempotency-Status"] == "new_execution"
    assert second.headers["X-Idempotency-Status"] == "replayed_completed_result"
    assert orchestrator.calls == 1


def test_inflight_duplicate_uses_internal_fingerprint(monkeypatch) -> None:
    orchestrator = _BlockingOrchestrator()
    registry = ResumeGenerationIdempotencyRegistry()
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        registry,
    )

    def send_request() -> object:
        with TestClient(app) as client:
            return client.post("/api/generate-resume", json=_request_payload())

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(send_request)
        assert orchestrator.started.wait(timeout=5)
        duplicate_response = send_request()
        orchestrator.release.set()
        first_response = first_future.result(timeout=5)

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 202
    assert duplicate_response.json()["status"] == PipelineStatus.RUNNING.value
    assert duplicate_response.headers["X-Idempotency-Status"] == "in_flight_duplicate"
    assert duplicate_response.json()["run_id"] == first_response.json()["run_id"]
    assert orchestrator.calls == 1


def test_changed_inputs_do_not_collide_with_same_idempotency_key(monkeypatch) -> None:
    orchestrator = _CountingOrchestrator()
    registry = ResumeGenerationIdempotencyRegistry()
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_RESUME_GENERATION_ORCHESTRATOR",
        orchestrator,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.generate_resume.DEFAULT_GENERATION_IDEMPOTENCY_REGISTRY",
        registry,
    )
    client = TestClient(app)
    profile_a = load_and_normalize_master_profile("data/master_profile.example.json")
    profile_b = profile_a.model_copy(update={"id": "master.alex-morgan-variant"})

    first = client.post(
        "/api/generate-resume",
        json=_request_payload(profile=profile_a),
        headers={"Idempotency-Key": "resume-dup-2"},
    )
    second = client.post(
        "/api/generate-resume",
        json=_request_payload(profile=profile_b),
        headers={"Idempotency-Key": "resume-dup-2"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["run_id"] != second.json()["run_id"]
    assert first.headers["X-Idempotency-Status"] == "new_execution"
    assert second.headers["X-Idempotency-Status"] == "new_execution"
    assert orchestrator.calls == 2
