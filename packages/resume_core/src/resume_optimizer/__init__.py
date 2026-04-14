"""Core data-layer package for Resume Optimizer."""

from __future__ import annotations

from typing import Any

__all__ = [
    "MasterProfile",
    "load_master_profile",
]


def __getattr__(name: str) -> Any:
    if name == "MasterProfile":
        from .models import MasterProfile

        return MasterProfile
    if name == "load_master_profile":
        from .loaders import load_master_profile

        return load_master_profile
    raise AttributeError(name)
