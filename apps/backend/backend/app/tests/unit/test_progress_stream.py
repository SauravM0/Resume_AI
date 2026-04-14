"""Tests for progress stream endpoint."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_events_invalid_run_id_returns_404() -> None:
    """Verify /events returns 404 for invalid run_id format."""
    client = TestClient(app)
    response = client.get("/api/pipeline-runs/invalid-id/events")
    assert response.status_code == 404
