"""Storage backend abstractions for Phase 6 artifacts."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Protocol

from backend.app.orchestration.artifacts.models import ArtifactWriteResult


class ArtifactStorageBackend(Protocol):
    """Protocol for durable artifact storage implementations."""

    storage_kind: str

    def write_json(self, *, run_id: str, relative_name: str, payload: dict[str, Any]) -> ArtifactWriteResult:
        """Persist JSON content and return a durable reference."""

    def write_text(self, *, run_id: str, relative_name: str, content: str, content_type: str) -> ArtifactWriteResult:
        """Persist text content and return a durable reference."""

    def copy_file(self, *, run_id: str, relative_name: str, source_path: Path, content_type: str) -> ArtifactWriteResult:
        """Copy a local file to durable storage and return a durable reference."""


class LocalArtifactStorageBackend:
    """Durable local filesystem backend for development and single-node runs."""

    storage_kind = "local_file"

    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path

    def write_json(self, *, run_id: str, relative_name: str, payload: dict[str, Any]) -> ArtifactWriteResult:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return self.write_text(
            run_id=run_id,
            relative_name=relative_name,
            content=content,
            content_type="application/json",
        )

    def write_text(self, *, run_id: str, relative_name: str, content: str, content_type: str) -> ArtifactWriteResult:
        destination = self._destination(run_id, relative_name)
        destination.write_text(content, encoding="utf-8")
        return _build_write_result(destination, storage_kind=self.storage_kind, content_type=content_type)

    def copy_file(self, *, run_id: str, relative_name: str, source_path: Path, content_type: str) -> ArtifactWriteResult:
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"artifact source file does not exist: {source_path}")
        destination = self._destination(run_id, relative_name)
        shutil.copy2(source_path, destination)
        return _build_write_result(destination, storage_kind=self.storage_kind, content_type=content_type)

    def _destination(self, run_id: str, relative_name: str) -> Path:
        safe_run_id = _safe_path_token(run_id)
        safe_relative = Path(*[_safe_path_token(part) for part in Path(relative_name).parts if part not in {"", "."}])
        destination = self.root_path / safe_run_id / safe_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination


def _build_write_result(path: Path, *, storage_kind: str, content_type: str) -> ArtifactWriteResult:
    data = path.read_bytes()
    return ArtifactWriteResult(
        storage_kind=storage_kind,
        storage_path_or_key=str(path),
        content_hash="sha256:" + sha256(data).hexdigest(),
        size_bytes=len(data),
        content_type=content_type,
    )


def _safe_path_token(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in value)[:160]
