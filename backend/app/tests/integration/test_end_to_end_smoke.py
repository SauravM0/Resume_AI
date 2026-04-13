"""End-to-end smoke test for resume generation pipeline."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_generate_resume_accepts_and_creates_run() -> None:
    """Verify /api/generate-resume accepts request and creates run_id."""
    client = TestClient(app)

    response = client.post(
        "/api/generate-resume",
        json={
            "job_description_text": "Software Engineer with Python experience",
            "source_profile_path": "C:/Users/Alexa/OneDrive/Desktop/ResumeAI/data/master_profile.example.json",
            "template_id": "ats_standard",
        },
    )

    assert response.status_code in {200, 202, 502, 500}

    if response.status_code >= 400:
        detail = response.json().get("detail", {})
        run_id = detail.get("run_id")
    else:
        data = response.json()
        run_id = data.get("run_id")

    assert run_id is not None
    assert run_id.startswith("run.")
