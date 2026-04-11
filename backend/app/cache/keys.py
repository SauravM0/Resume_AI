"""Stable cache key builders for safe deterministic backend caching."""

from __future__ import annotations

from hashlib import sha256
import inspect
import json
from pathlib import Path
from typing import Any


def stable_text_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def stable_file_hash(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def stable_json_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")).hexdigest()


def stable_model_hash(model: object) -> str:
    model_dump = getattr(model, "model_dump", None)
    if callable(model_dump):
        return stable_json_hash(model_dump(mode="json", exclude_none=True))
    if hasattr(model, "__dict__"):
        return stable_json_hash(vars(model))
    return stable_text_hash(str(model))


def stable_code_hash(*objects: object) -> str:
    chunks: list[str] = []
    for obj in objects:
        try:
            chunks.append(inspect.getsource(obj))
        except (OSError, TypeError):
            module = inspect.getmodule(obj)
            if module is not None and getattr(module, "__file__", None):
                chunks.append(Path(module.__file__).read_text(encoding="utf-8"))
            else:
                chunks.append(repr(obj))
    return stable_text_hash("".join(chunks))


def build_cache_key(namespace: str, parts: dict[str, object]) -> str:
    payload = {
        "namespace": namespace,
        **parts,
    }
    return stable_json_hash(payload)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)
