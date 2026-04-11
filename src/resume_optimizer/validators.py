"""Validation utilities for master profile integrity checks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from email.utils import parseaddr
from enum import StrEnum
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .constants import VALIDATION_SEVERITIES
from .models import (
    AwardEntry,
    BulletEntry,
    CertificationEntry,
    EducationEntry,
    EmploymentType,
    EvidenceStrength,
    ExperienceEntry,
    ImpactLevel,
    ItemType,
    MasterProfile,
    PartialDate,
    PersonalProfile,
    ProfileItem,
    ProjectEntry,
    RoleType,
    SeniorityLevel,
    SkillEntry,
    VerifiedStatus,
)
from .normalizers import normalize_master_profile_payload


class ValidationSeverity(StrEnum):
    ERROR = VALIDATION_SEVERITIES[0]
    WARNING = VALIDATION_SEVERITIES[1]
    INFO = VALIDATION_SEVERITIES[2]


class ValidationIssue(BaseModel):
    code: str
    severity: ValidationSeverity
    entity_type: str
    entity_id: str
    message: str
    suggested_fix: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProfileValidationReport(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    summary: dict[str, int]

    model_config = ConfigDict(extra="forbid")


def parse_master_profile(payload: Mapping[str, Any]) -> MasterProfile:
    """Normalize and parse a raw payload into a strict MasterProfile."""

    normalized = normalize_master_profile_payload(payload)
    return MasterProfile.model_validate(normalized)


def parse_master_profile_json(payload: str) -> MasterProfile:
    """Parse a JSON string into a MasterProfile."""

    raw_payload = json.loads(payload)
    if not isinstance(raw_payload, dict):
        raise TypeError("Master profile JSON root must be an object")
    return parse_master_profile(raw_payload)


def validate_master_profile(profile: MasterProfile) -> ProfileValidationReport:
    """Run integrity checks that go beyond schema validation."""

    issues: list[ValidationIssue] = []

    all_items = list(_iter_profile_items(profile))
    all_ids = [item.id for item in all_items]
    all_ids.extend(metric.id for _, metric in _iter_metrics(profile))

    issues.extend(_validate_duplicate_ids(all_ids))
    issues.extend(_validate_orphan_references(profile, {item.id for item in all_items}))
    issues.extend(_validate_weak_bullets(profile))
    issues.extend(_validate_invalid_scores(profile))
    issues.extend(_validate_taxonomy_values(profile))
    issues.extend(_validate_conflicting_dates(profile))
    issues.extend(_validate_duplicate_bullet_text(profile))
    issues.extend(_validate_duplicate_skills(profile))
    issues.extend(_validate_contacts_and_urls(profile))

    severity_order = {
        ValidationSeverity.ERROR: 0,
        ValidationSeverity.WARNING: 1,
        ValidationSeverity.INFO: 2,
    }
    issues.sort(
        key=lambda issue: (
            severity_order[issue.severity],
            issue.entity_type,
            issue.entity_id,
            issue.code,
            issue.message,
        )
    )
    summary = _build_summary(issues)
    valid = summary[ValidationSeverity.ERROR.value] == 0
    return ProfileValidationReport(valid=valid, issues=issues, summary=summary)


def _iter_profile_items(profile: MasterProfile) -> Iterable[ProfileItem]:
    yield profile.personal_profile

    for entry in profile.experience:
        yield entry
        yield from entry.bullets

    for entry in profile.projects:
        yield entry
        yield from entry.bullets

    for entry in profile.education:
        yield entry
        yield from entry.bullets

    yield from profile.certifications
    for entry in profile.awards:
        yield entry
        yield from entry.bullets
    yield from profile.skills


def _iter_metrics(profile: MasterProfile) -> Iterable[tuple[ProfileItem, Any]]:
    for entry in profile.experience:
        for metric in entry.metrics:
            yield entry, metric
        for bullet in entry.bullets:
            for metric in bullet.metrics:
                yield bullet, metric

    for entry in profile.projects:
        for metric in entry.metrics:
            yield entry, metric
        for bullet in entry.bullets:
            for metric in bullet.metrics:
                yield bullet, metric

    for entry in profile.education:
        for bullet in entry.bullets:
            for metric in bullet.metrics:
                yield bullet, metric

    for entry in profile.skills:
        for metric in entry.metrics:
            yield entry, metric

    for entry in profile.awards:
        for bullet in entry.bullets:
            for metric in bullet.metrics:
                yield bullet, metric


def _validate_duplicate_ids(all_ids: list[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    duplicates = sorted(item_id for item_id, count in Counter(all_ids).items() if count > 1)
    for duplicate_id in duplicates:
        issues.append(
            ValidationIssue(
                code="duplicate_id",
                severity=ValidationSeverity.ERROR,
                entity_type="profile",
                entity_id=duplicate_id,
                message=f"Duplicate ID detected: {duplicate_id}",
                suggested_fix="Assign a unique stable ID to each entity and metric.",
            )
        )
    return issues


def _validate_orphan_references(profile: MasterProfile, known_ids: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in _iter_profile_items(profile):
        for link in item.source_links:
            if link.source_id in known_ids:
                continue
            if link.source_url is not None:
                continue
            issues.append(
                ValidationIssue(
                    code="orphan_reference",
                    severity=ValidationSeverity.WARNING,
                    entity_type=item.item_type.value,
                    entity_id=item.id,
                    message=f"Source link references unknown local entity ID '{link.source_id}'.",
                    suggested_fix="Point source_id at an existing entity ID or add a source_url for external evidence.",
                )
            )
    return issues


def _validate_weak_bullets(profile: MasterProfile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    suspicious_tokens = {
        "responsible for",
        "worked on",
        "helped with",
        "various tasks",
        "duties included",
        "participated in",
    }

    for parent_type, parent_id, bullet in _iter_bullets_with_parent(profile):
        text = bullet.text.strip()
        folded = text.casefold()

        if len(text) < 20:
            issues.append(
                ValidationIssue(
                    code="weak_bullet_short",
                    severity=ValidationSeverity.WARNING,
                    entity_type=bullet.item_type.value,
                    entity_id=bullet.id,
                    message=f"Bullet under {parent_type}:{parent_id} is too short to be informative.",
                    suggested_fix="Add concrete action, scope, and outcome details.",
                )
            )

        if folded in suspicious_tokens or any(token in folded for token in suspicious_tokens):
            issues.append(
                ValidationIssue(
                    code="weak_bullet_generic",
                    severity=ValidationSeverity.WARNING,
                    entity_type=bullet.item_type.value,
                    entity_id=bullet.id,
                    message=f"Bullet under {parent_type}:{parent_id} uses weak generic language.",
                    suggested_fix="Rewrite with specific actions, tools, metrics, or outcomes.",
                )
            )

        has_signal = bool(bullet.metrics or bullet.tools or any(char.isdigit() for char in text))
        if not has_signal and len(text.split()) < 8:
            issues.append(
                ValidationIssue(
                    code="weak_bullet_low_signal",
                    severity=ValidationSeverity.INFO,
                    entity_type=bullet.item_type.value,
                    entity_id=bullet.id,
                    message=f"Bullet under {parent_type}:{parent_id} has limited evidence of impact or specificity.",
                    suggested_fix="Consider adding tools used, measurable impact, or clearer scope.",
                )
            )

    return issues


def _validate_invalid_scores(profile: MasterProfile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in _iter_profile_items(profile):
        for field_name in ("impact_score", "recency_score"):
            value = getattr(item, field_name, None)
            if value is None:
                continue
            if not 0.0 <= float(value) <= 1.0:
                issues.append(
                    ValidationIssue(
                        code="invalid_score_range",
                        severity=ValidationSeverity.ERROR,
                        entity_type=item.item_type.value,
                        entity_id=item.id,
                        message=f"{field_name} must be between 0.0 and 1.0.",
                        suggested_fix="Clamp or recompute the score into the allowed range.",
                    )
                )
    return issues


def _validate_taxonomy_values(profile: MasterProfile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    taxonomy_fields: tuple[tuple[str, type[StrEnum]], ...] = (
        ("item_type", ItemType),
        ("role_type", RoleType),
        ("seniority_level", SeniorityLevel),
        ("impact_level", ImpactLevel),
        ("evidence_strength", EvidenceStrength),
        ("employment_type", EmploymentType),
        ("verified_status", VerifiedStatus),
    )

    for item in _iter_profile_items(profile):
        for field_name, enum_type in taxonomy_fields:
            value = getattr(item, field_name, None)
            if value is None:
                continue
            if not isinstance(value, enum_type):
                issues.append(
                    ValidationIssue(
                        code="invalid_taxonomy_value",
                        severity=ValidationSeverity.ERROR,
                        entity_type=item.item_type.value if hasattr(item, "item_type") else "unknown",
                        entity_id=item.id,
                        message=f"{field_name} has invalid value '{value}'.",
                        suggested_fix=f"Use one of: {', '.join(member.value for member in enum_type)}",
                    )
                )
    return issues


def _validate_conflicting_dates(profile: MasterProfile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for entry in profile.experience:
        issues.extend(
            _date_range_issues(
                entity_type=entry.item_type.value,
                entity_id=entry.id,
                start_date=entry.start_date,
                end_date=entry.end_date,
            )
        )
        if entry.current and entry.end_date is not None:
            issues.append(
                ValidationIssue(
                    code="conflicting_current_end_date",
                    severity=ValidationSeverity.ERROR,
                    entity_type=entry.item_type.value,
                    entity_id=entry.id,
                    message="Current experience entry should not have an end date.",
                    suggested_fix="Remove end_date or mark current as false.",
                )
            )

    for entry in profile.projects:
        issues.extend(
            _date_range_issues(
                entity_type=entry.item_type.value,
                entity_id=entry.id,
                start_date=entry.start_date,
                end_date=entry.end_date,
            )
        )

    for entry in profile.education:
        issues.extend(
            _date_range_issues(
                entity_type=entry.item_type.value,
                entity_id=entry.id,
                start_date=entry.start_date,
                end_date=entry.end_date,
            )
        )

    for entry in profile.certifications:
        issues.extend(
            _date_range_issues(
                entity_type=entry.item_type.value,
                entity_id=entry.id,
                start_date=entry.issue_date,
                end_date=entry.expiration_date,
            )
        )

    return issues


def _date_range_issues(
    *,
    entity_type: str,
    entity_id: str,
    start_date: PartialDate | None,
    end_date: PartialDate | None,
) -> list[ValidationIssue]:
    if start_date is None or end_date is None:
        return []

    if start_date.precision != end_date.precision:
        return [
            ValidationIssue(
                code="date_precision_mismatch",
                severity=ValidationSeverity.INFO,
                entity_type=entity_type,
                entity_id=entity_id,
                message="Start and end dates use different precision, so ordering is only partially comparable.",
                suggested_fix="Use matching date precision if strict ordering matters.",
            )
        ]

    if end_date.comparable_key() < start_date.comparable_key():
        return [
            ValidationIssue(
                code="date_range_conflict",
                severity=ValidationSeverity.ERROR,
                entity_type=entity_type,
                entity_id=entity_id,
                message="End date cannot be before start date.",
                suggested_fix="Correct the date range or remove the less reliable date.",
            )
        ]

    return []


def _validate_duplicate_bullet_text(profile: MasterProfile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for parent_type, parent_id, bullets in _iter_parent_bullet_groups(profile):
        seen: dict[str, str] = {}
        for bullet in bullets:
            normalized_text = " ".join(bullet.text.casefold().split())
            if normalized_text in seen:
                issues.append(
                    ValidationIssue(
                        code="duplicate_bullet_text",
                        severity=ValidationSeverity.WARNING,
                        entity_type=parent_type,
                        entity_id=parent_id,
                        message=f"Duplicate bullet text detected within {parent_type}:{parent_id}.",
                        suggested_fix=f"Deduplicate bullet '{bullet.id}' or make the accomplishment more specific.",
                    )
                )
            else:
                seen[normalized_text] = bullet.id
    return issues


def _validate_duplicate_skills(profile: MasterProfile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen: dict[str, str] = {}
    for skill in profile.skills:
        canonical_name = " ".join(skill.name.casefold().split())
        if canonical_name in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate_skill",
                    severity=ValidationSeverity.WARNING,
                    entity_type=skill.item_type.value,
                    entity_id=skill.id,
                    message=f"Skill duplicates canonical name already used by '{seen[canonical_name]}'.",
                    suggested_fix="Merge the duplicate skill or rename it to reflect a distinct capability.",
                )
            )
        else:
            seen[canonical_name] = skill.id
    return issues


def _validate_contacts_and_urls(profile: MasterProfile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    personal = profile.personal_profile

    if personal.email is not None:
        _, parsed = parseaddr(personal.email)
        if not parsed or "@" not in parsed:
            issues.append(
                ValidationIssue(
                    code="malformed_email",
                    severity=ValidationSeverity.ERROR,
                    entity_type=personal.item_type.value,
                    entity_id=personal.id,
                    message="Personal profile email is malformed.",
                    suggested_fix="Provide a valid email address or omit the field.",
                )
            )

    if personal.phone is not None:
        digits = sum(char.isdigit() for char in personal.phone)
        if digits < 7:
            issues.append(
                ValidationIssue(
                    code="malformed_phone",
                    severity=ValidationSeverity.WARNING,
                    entity_type=personal.item_type.value,
                    entity_id=personal.id,
                    message="Personal profile phone number appears incomplete.",
                    suggested_fix="Use a fuller contact number or omit the field.",
                )
            )

    url_fields = (
        ("linkedin_url", personal.linkedin_url),
        ("github_url", personal.github_url),
        ("website_url", personal.website_url),
    )
    for field_name, value in url_fields:
        if value is None:
            continue
        text = str(value)
        if not text.startswith(("http://", "https://")):
            issues.append(
                ValidationIssue(
                    code="malformed_url",
                    severity=ValidationSeverity.ERROR,
                    entity_type=personal.item_type.value,
                    entity_id=personal.id,
                    message=f"{field_name} must use http or https.",
                    suggested_fix="Store the full URL including scheme.",
                )
            )

    for entry in profile.projects:
        if entry.link_url is not None and not str(entry.link_url).startswith(("http://", "https://")):
            issues.append(
                ValidationIssue(
                    code="malformed_url",
                    severity=ValidationSeverity.ERROR,
                    entity_type=entry.item_type.value,
                    entity_id=entry.id,
                    message="Project link_url must use http or https.",
                    suggested_fix="Store the full project URL including scheme.",
                )
            )

    for entry in profile.certifications:
        if entry.credential_url is not None and not str(entry.credential_url).startswith(("http://", "https://")):
            issues.append(
                ValidationIssue(
                    code="malformed_url",
                    severity=ValidationSeverity.ERROR,
                    entity_type=entry.item_type.value,
                    entity_id=entry.id,
                    message="Certification credential_url must use http or https.",
                    suggested_fix="Store the full credential URL including scheme.",
                )
            )

    return issues


def _iter_parent_bullet_groups(
    profile: MasterProfile,
) -> Iterable[tuple[str, str, list[BulletEntry]]]:
    for entry in profile.experience:
        yield entry.item_type.value, entry.id, entry.bullets
    for entry in profile.projects:
        yield entry.item_type.value, entry.id, entry.bullets
    for entry in profile.education:
        yield entry.item_type.value, entry.id, entry.bullets
    for entry in profile.awards:
        yield entry.item_type.value, entry.id, entry.bullets


def _iter_bullets_with_parent(
    profile: MasterProfile,
) -> Iterable[tuple[str, str, BulletEntry]]:
    for parent_type, parent_id, bullets in _iter_parent_bullet_groups(profile):
        for bullet in bullets:
            yield parent_type, parent_id, bullet


def _build_summary(issues: list[ValidationIssue]) -> dict[str, int]:
    counts = {severity.value: 0 for severity in ValidationSeverity}
    for issue in issues:
        counts[issue.severity.value] += 1
    return counts
