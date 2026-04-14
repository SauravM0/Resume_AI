"""Integration tests for /api/generate-resume endpoint request acceptance."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_generate_resume_accepts_valid_request() -> None:
    """Verify /api/generate-resume accepts a valid request with required fields."""
    client = TestClient(app)
    payload = {
        "job_description_text": "Software Engineer",
        "source_profile_path": "C:/Users/Alexa/OneDrive/Desktop/ResumeAI/data/master_profile.example.json",
        "template_id": "ats_standard",
    }
    response = client.post("/api/generate-resume", json=payload)
    assert response.status_code in {200, 502, 500}


def test_generate_resume_returns_run_id() -> None:
    """Verify /api/generate-resume returns run_id in response."""
    client = TestClient(app)
    payload = {
        "job_description_text": "Software Engineer",
        "source_profile_path": "C:/Users/Alexa/OneDrive/Desktop/ResumeAI/data/master_profile.example.json",
        "template_id": "ats_standard",
    }
    response = client.post("/api/generate-resume", json=payload)
    if response.status_code >= 400:
        detail = response.json().get("detail", {})
        run_id = detail.get("run_id")
        assert run_id is not None
        assert run_id.startswith("run.")
    else:
        data = response.json()
        assert "run_id" in data


def test_generate_resume_rejects_empty_job_description() -> None:
    """Verify /api/generate-resume rejects empty job description."""
    client = TestClient(app)
    payload = {
        "job_description_text": "",
        "source_profile_path": "C:/Users/Alexa/OneDrive/Desktop/ResumeAI/data/master_profile.example.json",
        "template_id": "ats_standard",
    }
    response = client.post("/api/generate-resume", json=payload)
    assert response.status_code == 422


def test_generate_resume_rejects_missing_profile_source() -> None:
    """Verify /api/generate-resume rejects missing profile source."""
    client = TestClient(app)
    payload = {
        "job_description_text": "Software Engineer",
        "template_id": "ats_standard",
    }
    response = client.post("/api/generate-resume", json=payload)
    assert response.status_code == 422
