"""Artifact download routes for completed pipeline runs."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api", tags=["pipeline-artifacts"])


@router.get("/pipeline-runs/{run_id}/artifacts/{artifact_id}")
def download_pipeline_artifact(
    run_id: str,
    artifact_id: str,
    path: str = Query(..., description="Resolved local artifact path"),
) -> FileResponse:
    """Serve a persisted local artifact through the API for browser-safe downloads."""

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not found.")

    safe_run_id = _safe_path_token(run_id)
    if safe_run_id not in resolved.as_posix():
        raise HTTPException(status_code=404, detail="Artifact does not belong to the requested run.")

    return FileResponse(path=resolved, filename=resolved.name)


def _safe_path_token(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in value)
