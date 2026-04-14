"""Public Phase 4 verification handoff contracts.

This module is the service-domain import surface for orchestration code. The
schema definitions live in ``backend.app.schemas.verification`` so API and
service layers share one contract.
"""

from __future__ import annotations

from backend.app.schemas.verification import (
    Phase3VerificationInput,
    Phase4RenderingOutput,
    VerificationReport,
)

__all__ = [
    "Phase3VerificationInput",
    "Phase4RenderingOutput",
    "VerificationReport",
]
