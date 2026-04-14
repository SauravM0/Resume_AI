"""API response schemas for verification-aware backend pipeline responses."""

from __future__ import annotations

from pydantic import Field

from backend.app.schemas.verification import Phase4RenderingOutput, VerificationReport
from backend.app.services.verification.types import VerificationStatus
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel
from resume_optimizer.phase3_models import Phase3GenerationResult


class GenerateResumeVerificationResponse(StrictModel):
    """Backend response for Phase 3 generation followed by the Phase 6 gate."""

    status: NonEmptyStr
    pipeline_run_id: StableId
    verification_run_id: StableId
    phase3_result: Phase3GenerationResult
    verification_report: VerificationReport
    rendering_output: Phase4RenderingOutput
    warnings: list[NonEmptyStr] = Field(default_factory=list)


def api_status_from_verification(status: VerificationStatus) -> str:
    """Map internal verification status to API-visible pipeline status."""

    if status == VerificationStatus.PASSED:
        return "verification_passed"
    if status == VerificationStatus.PASSED_WITH_WARNINGS:
        return "verification_passed_with_warnings"
    return "verification_failed"
