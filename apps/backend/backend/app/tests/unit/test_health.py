"""Unit tests for health check endpoint."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_returns_200() -> None:
    """Verify /api/health returns 200 status code."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_response_ok_true() -> None:
    """Verify health response has ok=true."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True


def test_health_response_service() -> None:
    """Verify health response has expected service field."""
    client = TestClient(app)
    response = client.get("/api/health")
    data = response.json()
    assert data.get("service") == "resumeai-backend"
