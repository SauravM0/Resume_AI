"""Master profile API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.master_profile_service import (
    load_master_profile,
    save_master_profile,
    validate_master_profile,
    is_profile_valid,
    get_master_profile_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["master-profile"])


class MasterProfileResponse(BaseModel):
    profile_path: str
    is_valid: bool
    validation_errors: list[str]


class ValidationResponse(BaseModel):
    is_valid: bool
    errors: list[str]


@router.get("/master-profile")
def get_master_profile() -> MasterProfileResponse:
    """Get current master profile with validation status."""
    try:
        profile = load_master_profile()
        errors = validate_master_profile(profile)
        return MasterProfileResponse(
            profile_path=str(get_master_profile_path()),
            is_valid=is_profile_valid(profile),
            validation_errors=errors,
        )
    except Exception as e:
        logger.error(f"Failed to load master profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/master-profile/raw")
def get_master_profile_raw() -> dict:
    """Get raw master profile JSON."""
    try:
        profile = load_master_profile()
        return profile.model_dump()
    except Exception as e:
        logger.error(f"Failed to load master profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/master-profile/raw")
def update_master_profile_raw(profile_data: dict) -> dict:
    """Update master profile from raw JSON."""
    try:
        from resume_optimizer.models import MasterProfile

        profile = MasterProfile.model_validate(profile_data)
        errors = validate_master_profile(profile)

        if errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Profile validation failed",
                    "errors": errors,
                },
            )

        saved = save_master_profile(profile)
        return saved.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update master profile: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/master-profile/validate")
def validate_profile(profile_data: dict) -> ValidationResponse:
    """Validate master profile without saving."""
    try:
        from resume_optimizer.models import MasterProfile

        profile = MasterProfile.model_validate(profile_data)
        errors = validate_master_profile(profile)

        return ValidationResponse(
            is_valid=len(errors) == 0,
            errors=errors,
        )
    except Exception as e:
        logger.error(f"Failed to validate profile: {e}")
        return ValidationResponse(
            is_valid=False,
            errors=[str(e)],
        )
