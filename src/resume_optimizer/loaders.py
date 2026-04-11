"""File loading helpers for the Phase 0 master profile."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from backend.app.cache.codecs import deserialize_master_profile, serialize_model
from backend.app.cache.keys import build_cache_key, stable_code_hash, stable_file_hash
from backend.app.cache.storage import get_or_compute

from .config import DEFAULT_SETTINGS
from .models import MasterProfile
from .normalizers import normalize_master_profile
from .validators import ProfileValidationReport, parse_master_profile, validate_master_profile

PROFILE_LOAD_CACHE_NAMESPACE = "profile_load"
PROFILE_LOAD_CACHE_TTL_SECONDS = 24 * 60 * 60


def load_master_profile(path: str | Path) -> MasterProfile:
    """Load raw JSON from disk and parse it into a MasterProfile."""

    payload = _load_profile_payload(path)
    return parse_master_profile(payload)


def load_and_normalize_master_profile(path: str | Path) -> MasterProfile:
    """Load a profile from disk, parse it, and return a normalized model."""

    profile_path = Path(path).resolve()
    cache_key = build_cache_key(
        PROFILE_LOAD_CACHE_NAMESPACE,
        {
            "profile_content_hash": stable_file_hash(profile_path),
            "path": str(profile_path),
            "file_encoding": DEFAULT_SETTINGS.file_encoding,
            "loader_code_hash": stable_code_hash(
                load_master_profile,
                normalize_master_profile,
                parse_master_profile,
            ),
        },
    )
    cached, _ = get_or_compute(
        namespace=PROFILE_LOAD_CACHE_NAMESPACE,
        key=cache_key,
        compute=lambda: normalize_master_profile(load_master_profile(profile_path)),
        serialize=serialize_model,
        deserialize=deserialize_master_profile,
        ttl_seconds=PROFILE_LOAD_CACHE_TTL_SECONDS,
        metadata={"path": str(profile_path)},
    )
    return cached


def load_validate_and_normalize(path: str | Path) -> tuple[MasterProfile, ProfileValidationReport]:
    """Load a profile from disk, normalize it, and return its validation report."""

    profile = load_and_normalize_master_profile(path)
    report = validate_master_profile(profile)
    return profile, report


def _load_profile_payload(path: str | Path) -> dict[str, Any]:
    """Read and decode a master profile JSON file."""

    profile_path = Path(path)
    try:
        with profile_path.open("r", encoding=DEFAULT_SETTINGS.file_encoding) as file_obj:
            payload: Any = json.load(file_obj)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Master profile file not found: {profile_path}") from exc
    except OSError as exc:
        raise OSError(f"Unable to read master profile file: {profile_path}") from exc
    except JSONDecodeError as exc:
        raise ValueError(
            f"Malformed JSON in master profile file {profile_path} at line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(payload, dict):
        raise TypeError(f"Master profile JSON root must be an object: {profile_path}")

    return payload
