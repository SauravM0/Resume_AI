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

from resume_optimizer.app import app


def test_health_route_reports_api_and_runtime_configuration() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api"] is True
    assert payload["profile_path_configured"] is True
    assert payload["template_configured"] is True
    assert payload["ok"] is True
