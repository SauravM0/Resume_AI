"""Master profile storage service."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from resume_optimizer.models import MasterProfile, StableId

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = "data/master_profile.json"


def get_master_profile_path() -> Path:
    """Get the master profile path from environment or default."""
    env_path = os.environ.get("MASTER_PROFILE_PATH")
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_PROFILE_PATH)


def load_master_profile() -> MasterProfile:
    """Load master profile from configured storage path.

    If profile file does not exist, creates empty scaffold safely.
    """
    profile_path = get_master_profile_path()

    if profile_path.exists():
        try:
            profile_data = profile_path.read_text(encoding="utf-8")
            return MasterProfile.model_validate_json(profile_data)
        except Exception as e:
            logger.warning(f"Failed to load profile from {profile_path}: {e}")

    return create_empty_profile()


def create_empty_profile() -> MasterProfile:
    """Create an empty profile scaffold with required IDs."""
    return MasterProfile(
        id="profile.default",
        personal_profile=create_empty_personal_profile(),
        experience=[],
        projects=[],
        education=[],
        certifications=[],
        awards=[],
        skills=[],
    )


def create_empty_personal_profile() -> "resume_optimizer.models.PersonalProfile":
    """Create an empty personal profile section."""
    from resume_optimizer.models import (
        PersonalProfile,
        RoleType,
        VerifiedStatus,
    )

    return PersonalProfile(
        id="personal.default",
        item_type="personal_profile",
        full_name="Your Name",
        headline=None,
        summary=None,
        email=None,
        phone=None,
        location=None,
        linkedin_url=None,
        github_url=None,
        website_url=None,
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=None,
        source_links=[],
        canonical_tags=[],
        domain_tags=[],
        verified_status=VerifiedStatus.UNVERIFIED,
        evidence_strength="weak",
        rewrite_allowed=True,
    )


def save_master_profile(profile: MasterProfile) -> MasterProfile:
    """Save master profile to configured storage path."""
    profile_path = get_master_profile_path()

    profile_path.parent.mkdir(parents=True, exist_ok=True)

    profile_json = profile.model_dump_json(indent=2, exclude_none=True)
    profile_path.write_text(profile_json, encoding="utf-8")

    logger.info(f"Master profile saved to {profile_path}")
    return profile


def validate_master_profile(profile: MasterProfile) -> list[str]:
    """Validate master profile and return list of validation errors."""
    errors = []

    if not profile.id or len(profile.id) < 3:
        errors.append("profile ID must be at least 3 characters")

    if not profile.personal_profile:
        errors.append("personal profile section is required")
    else:
        if not profile.personal_profile.full_name:
            errors.append("personal profile full_name is required")
        if not profile.personal_profile.id:
            errors.append("personal profile ID is required")

    for idx, exp in enumerate(profile.experience):
        if not exp.id:
            errors.append(f"experience[{idx}]: ID is required")
        if not exp.organization:
            errors.append(f"experience[{idx}]: organization is required")
        if not exp.title:
            errors.append(f"experience[{idx}]: title is required")
        if not exp.start_date:
            errors.append(f"experience[{idx}]: start_date is required")
        for bidx, bullet in enumerate(exp.bullets):
            if not bullet.id:
                errors.append(f"experience[{idx}].bullets[{bidx}]: ID is required")
            if not bullet.text:
                errors.append(f"experience[{idx}].bullets[{bidx}]: text is required")

    for idx, proj in enumerate(profile.projects):
        if not proj.id:
            errors.append(f"project[{idx}]: ID is required")
        if not proj.name:
            errors.append(f"project[{idx}]: name is required")
        for bidx, bullet in enumerate(proj.bullets):
            if not bullet.id:
                errors.append(f"project[{idx}].bullets[{bidx}]: ID is required")
            if not bullet.text:
                errors.append(f"project[{idx}].bullets[{bidx}]: text is required")

    for idx, edu in enumerate(profile.education):
        if not edu.id:
            errors.append(f"education[{idx}]: ID is required")
        if not edu.institution:
            errors.append(f"education[{idx}]: institution is required")
        if not edu.degree:
            errors.append(f"education[{idx}]: degree is required")

    for idx, cert in enumerate(profile.certifications):
        if not cert.id:
            errors.append(f"certification[{idx}]: ID is required")
        if not cert.name:
            errors.append(f"certification[{idx}]: name is required")
        if not cert.issuer:
            errors.append(f"certification[{idx}]: issuer is required")

    for idx, skill in enumerate(profile.skills):
        if not skill.id:
            errors.append(f"skill[{idx}]: ID is required")
        if not skill.name:
            errors.append(f"skill[{idx}]: name is required")
        if not skill.category:
            errors.append(f"skill[{idx}]: category is required")

    return errors


def is_profile_valid(profile: MasterProfile) -> bool:
    """Check if profile is valid for generation."""
    return len(validate_master_profile(profile)) == 0
