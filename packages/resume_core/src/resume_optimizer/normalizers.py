"""Deterministic normalization helpers for Phase 0 source data."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any

from .constants import (
    DOMAIN_ALIASES,
    ROLE_TYPE_ALIASES,
    ROLE_TYPES,
    SENIORITY_ALIASES,
    SENIORITY_LEVELS,
    SKILL_ALIASES,
    TITLE_ALIASES,
)
from .models import (
    AwardEntry,
    BulletEntry,
    CertificationEntry,
    EducationEntry,
    ExperienceEntry,
    MasterProfile,
    PartialDate,
    PersonalProfile,
    ProjectEntry,
    RoleType,
    SeniorityLevel,
    SkillEntry,
)
from .normalization import (
    normalize_domain,
    normalize_role_taxonomy,
    normalize_seniority_taxonomy,
    normalize_skill,
    normalize_title_taxonomy,
    normalize_tool,
)

TOOL_NAME_ALIASES: dict[str, str] = {
    **dict(SKILL_ALIASES),
    "k8s": "Kubernetes",
    "terraform io": "Terraform",
    "tf": "Terraform",
}


def normalize_skill_name(value: str) -> str:
    """Return a canonical skill name for common source-data variants."""

    cleaned = _normalize_text(value)
    if not cleaned:
        return cleaned

    return normalize_skill(cleaned).canonical


def normalize_tool_name(value: str) -> str:
    """Return a canonical tool name for common source-data variants."""

    cleaned = _normalize_text(value)
    if not cleaned:
        return cleaned

    taxonomy_value = normalize_tool(cleaned)
    if taxonomy_value.status.value != "passthrough":
        return taxonomy_value.canonical
    alias = TOOL_NAME_ALIASES.get(_fold_key(cleaned))
    if alias is not None:
        return alias
    return taxonomy_value.canonical


def normalize_title(value: str) -> str:
    """Expand common title abbreviations and normalize spacing/casing."""

    cleaned = _normalize_text(value)
    if not cleaned:
        return cleaned

    return normalize_title_taxonomy(cleaned).canonical


def normalize_role_type(value: str | RoleType | None) -> RoleType | None:
    """Map common source labels onto the canonical role-type enum."""

    if value is None:
        return None
    if isinstance(value, RoleType):
        return value

    cleaned = _normalize_text(value)
    canonical = normalize_role_taxonomy(cleaned).canonical
    if canonical not in ROLE_TYPES:
        canonical = ROLE_TYPE_ALIASES.get(_fold_key(cleaned))
    return RoleType(canonical) if canonical is not None else None


def normalize_seniority(value: str | SeniorityLevel | None) -> SeniorityLevel | None:
    """Map common seniority variants onto the canonical seniority enum."""

    if value is None:
        return None
    if isinstance(value, SeniorityLevel):
        return value

    cleaned = _normalize_text(value)
    canonical = normalize_seniority_taxonomy(cleaned).canonical
    if canonical not in SENIORITY_LEVELS:
        canonical = SENIORITY_ALIASES.get(_fold_key(cleaned))
    return SeniorityLevel(canonical) if canonical is not None else None


def normalize_domain_tag(value: str) -> str:
    """Return a canonical domain tag for common abbreviated variants."""

    cleaned = _normalize_text(value)
    if not cleaned:
        return cleaned

    taxonomy_value = normalize_domain(cleaned)
    if taxonomy_value.status.value != "passthrough":
        return taxonomy_value.canonical
    alias = DOMAIN_ALIASES.get(_fold_key(cleaned))
    if alias is not None:
        return alias
    return taxonomy_value.canonical


def normalize_partial_date(value: PartialDate | Mapping[str, Any] | str | None) -> PartialDate | None:
    """Return a normalized PartialDate while preserving raw source input."""

    if value is None:
        return None
    if isinstance(value, PartialDate):
        if value.normalized_value == value.raw_value:
            return value
        return PartialDate(raw_value=value.raw_value)
    if isinstance(value, str):
        return PartialDate(raw_value=_normalize_date_string(value))
    if isinstance(value, Mapping):
        raw_value = value.get("raw_value")
        if not isinstance(raw_value, str):
            raise TypeError("PartialDate mappings must include a string raw_value")
        return PartialDate(raw_value=_normalize_date_string(raw_value))
    raise TypeError("Unsupported date value for normalization")


def normalize_master_profile(profile: MasterProfile) -> MasterProfile:
    """Return a cleaned MasterProfile with canonicalized fields."""

    return MasterProfile(
        id=profile.id,
        personal_profile=_normalize_personal_profile(profile.personal_profile),
        experience=[_normalize_experience_entry(entry) for entry in profile.experience],
        projects=[_normalize_project_entry(entry) for entry in profile.projects],
        education=[_normalize_education_entry(entry) for entry in profile.education],
        certifications=[_normalize_certification_entry(entry) for entry in profile.certifications],
        awards=[_normalize_award_entry(entry) for entry in profile.awards],
        skills=[_normalize_skill_entry(entry) for entry in profile.skills],
    )


def normalize_master_profile_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a raw payload before Pydantic validation."""

    normalized = deepcopy(dict(payload))
    normalized = _normalize_nested_strings(normalized)

    personal = normalized.get("personal_profile")
    if isinstance(personal, dict):
        _normalize_payload_item(personal)

    for entry in _payload_list(normalized, "experience"):
        _normalize_payload_item(entry)
        _normalize_title_field(entry, "title")
        _normalize_optional_enum_field(entry, "role_type", normalize_role_type)
        _normalize_optional_enum_field(entry, "seniority_level", normalize_seniority)
        _normalize_string_list(entry, "tools", normalize_tool_name)
        _normalize_partial_date_field(entry, "start_date")
        _normalize_partial_date_field(entry, "end_date")
        if entry.get("current") is True:
            entry["end_date"] = None
        _normalize_bullet_payloads(entry)

    for entry in _payload_list(normalized, "projects"):
        _normalize_payload_item(entry)
        _normalize_title_field(entry, "role")
        _normalize_optional_enum_field(entry, "role_type", normalize_role_type)
        _normalize_optional_enum_field(entry, "seniority_level", normalize_seniority)
        _normalize_string_list(entry, "tools", normalize_tool_name)
        _normalize_partial_date_field(entry, "start_date")
        _normalize_partial_date_field(entry, "end_date")
        _normalize_bullet_payloads(entry)

    for entry in _payload_list(normalized, "education"):
        _normalize_payload_item(entry)
        _normalize_partial_date_field(entry, "start_date")
        _normalize_partial_date_field(entry, "end_date")
        _normalize_bullet_payloads(entry)

    for entry in _payload_list(normalized, "certifications"):
        _normalize_payload_item(entry)
        _normalize_partial_date_field(entry, "issue_date")
        _normalize_partial_date_field(entry, "expiration_date")

    for entry in _payload_list(normalized, "awards"):
        _normalize_payload_item(entry)
        _normalize_partial_date_field(entry, "award_date")
        _normalize_bullet_payloads(entry)

    for entry in _payload_list(normalized, "skills"):
        _normalize_payload_item(entry)
        if isinstance(entry.get("name"), str):
            entry["name"] = normalize_skill_name(entry["name"])
        _normalize_string_list(entry, "tools", normalize_tool_name)
        _normalize_optional_enum_field(entry, "role_type", normalize_role_type)
        _normalize_optional_enum_field(entry, "seniority_level", normalize_seniority)

    return normalized


def _normalize_personal_profile(profile: PersonalProfile) -> PersonalProfile:
    return profile.model_copy(
        update={
            "headline": _normalize_optional_title(profile.headline),
            "role_type": normalize_role_type(profile.role_type),
            "seniority_level": normalize_seniority(profile.seniority_level),
            "domain_tags": _normalize_unique(profile.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(profile.canonical_tags, _normalize_text),
        }
    )


def _normalize_experience_entry(entry: ExperienceEntry) -> ExperienceEntry:
    return entry.model_copy(
        update={
            "title": normalize_title(entry.title),
            "role_type": normalize_role_type(entry.role_type),
            "seniority_level": normalize_seniority(entry.seniority_level),
            "tools": _normalize_unique(entry.tools, normalize_tool_name),
            "domain_tags": _normalize_unique(entry.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(entry.canonical_tags, _normalize_text),
            "start_date": normalize_partial_date(entry.start_date),
            "end_date": None if entry.current else normalize_partial_date(entry.end_date),
            "bullets": [_normalize_bullet_entry(bullet) for bullet in entry.bullets],
        }
    )


def _normalize_project_entry(entry: ProjectEntry) -> ProjectEntry:
    normalized_role = _normalize_optional_title(entry.role)
    return entry.model_copy(
        update={
            "role": normalized_role,
            "role_type": normalize_role_type(entry.role_type),
            "seniority_level": normalize_seniority(entry.seniority_level),
            "tools": _normalize_unique(entry.tools, normalize_tool_name),
            "domain_tags": _normalize_unique(entry.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(entry.canonical_tags, _normalize_text),
            "start_date": normalize_partial_date(entry.start_date),
            "end_date": normalize_partial_date(entry.end_date),
            "bullets": [_normalize_bullet_entry(bullet) for bullet in entry.bullets],
        }
    )


def _normalize_education_entry(entry: EducationEntry) -> EducationEntry:
    return entry.model_copy(
        update={
            "domain_tags": _normalize_unique(entry.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(entry.canonical_tags, _normalize_text),
            "start_date": normalize_partial_date(entry.start_date),
            "end_date": normalize_partial_date(entry.end_date),
            "bullets": [_normalize_bullet_entry(bullet) for bullet in entry.bullets],
        }
    )


def _normalize_certification_entry(entry: CertificationEntry) -> CertificationEntry:
    return entry.model_copy(
        update={
            "domain_tags": _normalize_unique(entry.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(entry.canonical_tags, _normalize_text),
            "issue_date": normalize_partial_date(entry.issue_date),
            "expiration_date": normalize_partial_date(entry.expiration_date),
        }
    )


def _normalize_award_entry(entry: AwardEntry) -> AwardEntry:
    return entry.model_copy(
        update={
            "domain_tags": _normalize_unique(entry.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(entry.canonical_tags, _normalize_text),
            "award_date": normalize_partial_date(entry.award_date),
            "bullets": [_normalize_bullet_entry(bullet) for bullet in entry.bullets],
        }
    )


def _normalize_skill_entry(entry: SkillEntry) -> SkillEntry:
    return entry.model_copy(
        update={
            "name": normalize_skill_name(entry.name),
            "category": normalize_domain_tag(entry.category),
            "tools": _normalize_unique(entry.tools, normalize_tool_name),
            "role_type": normalize_role_type(entry.role_type),
            "seniority_level": normalize_seniority(entry.seniority_level),
            "domain_tags": _normalize_unique(entry.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(entry.canonical_tags, _normalize_text),
        }
    )


def _normalize_bullet_entry(entry: BulletEntry) -> BulletEntry:
    return entry.model_copy(
        update={
            "tools": _normalize_unique(entry.tools, normalize_tool_name),
            "domain_tags": _normalize_unique(entry.domain_tags, normalize_domain_tag),
            "canonical_tags": _normalize_unique(entry.canonical_tags, _normalize_text),
        }
    )


def _normalize_payload_item(entry: dict[str, Any]) -> None:
    _normalize_string_list(entry, "domain_tags", normalize_domain_tag)
    _normalize_string_list(entry, "canonical_tags", _normalize_text)


def _normalize_bullet_payloads(parent: dict[str, Any]) -> None:
    bullets = parent.get("bullets")
    if not isinstance(bullets, list):
        return

    for bullet in bullets:
        if not isinstance(bullet, dict):
            continue
        _normalize_payload_item(bullet)
        _normalize_string_list(bullet, "tools", normalize_tool_name)


def _normalize_title_field(entry: dict[str, Any], field_name: str) -> None:
    value = entry.get(field_name)
    if isinstance(value, str):
        entry[field_name] = normalize_title(value)


def _normalize_optional_enum_field(entry: dict[str, Any], field_name: str, normalizer: Any) -> None:
    value = entry.get(field_name)
    if value is None:
        return
    normalized = normalizer(value)
    if normalized is not None:
        entry[field_name] = normalized.value


def _normalize_partial_date_field(entry: dict[str, Any], field_name: str) -> None:
    value = entry.get(field_name)
    if value is None:
        return
    normalized = normalize_partial_date(value)
    if normalized is not None:
        entry[field_name] = {"raw_value": normalized.raw_value}


def _normalize_string_list(entry: dict[str, Any], field_name: str, normalizer: Any) -> None:
    values = entry.get(field_name)
    if not isinstance(values, list):
        return
    entry[field_name] = _normalize_unique(values, normalizer)


def _payload_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_nested_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_nested_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_nested_strings(item) for item in value]
    if isinstance(value, str):
        return _normalize_text(value)
    return value


def _normalize_optional_title(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_title(value)


def _normalize_unique(values: list[str], normalizer: Any) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = normalizer(value)
        if not normalized:
            continue
        key = _fold_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values


def _normalize_date_string(value: str) -> str:
    cleaned = _normalize_text(value)
    cleaned = cleaned.replace("/", "-").replace(".", "-")
    return cleaned


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _fold_key(value: str) -> str:
    return _normalize_text(value).casefold()


def _smart_title(value: str) -> str:
    words = re.split(r"(\s+|/|-)", value)
    normalized: list[str] = []
    preserve_upper = {"AI", "BI", "ML", "SQL", "AWS", "GCP", "API", "UI", "UX"}
    preserve_mixed = {"JavaScript", "TypeScript", "Node.js", "PostgreSQL", "GitHub", "Kubernetes"}

    for token in words:
        if token.isspace() or token in {"/", "-"}:
            normalized.append(token)
            continue

        if not token:
            continue

        if token in preserve_mixed:
            normalized.append(token)
            continue

        upper_token = token.upper()
        if upper_token in preserve_upper:
            normalized.append(upper_token)
            continue

        normalized.append(token.capitalize())

    return "".join(normalized)
