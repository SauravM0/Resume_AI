"""Compatibility adapter from canonical evidence units to legacy ranking items."""

from __future__ import annotations

from .evidence_builder import build_canonical_evidence_units
from .evidence_models import CanonicalEvidenceUnit, EvidenceSourceType
from .models import CertificationEntry, ExperienceEntry, ItemType, MasterProfile, ProjectEntry
from .ranking_models import CandidateEvidenceItem


def build_evidence_pool(profile: MasterProfile) -> list[CandidateEvidenceItem]:
    """Return legacy ranking items derived from canonical evidence units."""

    return [_to_candidate_evidence_item(unit) for unit in build_canonical_evidence_units(profile)]


def build_experience_evidence_items(
    entries: list[ExperienceEntry],
) -> list[CandidateEvidenceItem]:
    """Return legacy ranking items derived from experience-related evidence units."""

    profile = MasterProfile(
        id="master.synthetic-experience-only",
        personal_profile=_empty_personal_profile(),
        experience=entries,
    )
    return [
        item for item in build_evidence_pool(profile)
        if item.item_type == ItemType.EXPERIENCE
    ]


def build_project_evidence_items(entries: list[ProjectEntry]) -> list[CandidateEvidenceItem]:
    """Return legacy ranking items derived from project-related evidence units."""

    profile = MasterProfile(
        id="master.synthetic-project-only",
        personal_profile=_empty_personal_profile(),
        projects=entries,
    )
    return [
        item for item in build_evidence_pool(profile)
        if item.item_type == ItemType.PROJECT
    ]


def build_certification_evidence_items(
    entries: list[CertificationEntry],
) -> list[CandidateEvidenceItem]:
    """Return legacy ranking items derived from certification evidence units."""

    profile = MasterProfile(
        id="master.synthetic-cert-only",
        personal_profile=_empty_personal_profile(),
        certifications=entries,
    )
    return [
        item for item in build_evidence_pool(profile)
        if item.item_type == ItemType.CERTIFICATION
    ]


def _to_candidate_evidence_item(unit: CanonicalEvidenceUnit) -> CandidateEvidenceItem:
    item_type = _legacy_item_type(unit.source_type)
    return CandidateEvidenceItem(
        id=unit.evidence_unit_id,
        item_type=item_type,
        title=unit.provenance.source_entity_title or unit.raw_text,
        source_item_id=unit.source_entity_id,
        source_bullet_ids=[unit.source_bullet_id] if unit.source_bullet_id else [],
        domain_tags=unit.normalized_domains,
        relevant_for=_normalize_token_list([
            *unit.inferred_role_types,
            *unit.impact_signals,
            *unit.seniority_signals,
        ]),
        keywords=_normalize_token_list([
            *unit.normalized_skills,
            *unit.normalized_tools,
        ]),
        bullets=[unit.raw_text] if unit.source_bullet_id else [],
        impact=0.9 if "high_impact_score" in unit.impact_signals else None,
        level=unit.seniority_signals[0] if unit.seniority_signals else None,
        start=unit.recency.start_date,
        end=unit.recency.end_date,
    )


def _normalize_token_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = _normalize_text(value).casefold()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized
def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _legacy_item_type(source_type: EvidenceSourceType) -> ItemType:
    if source_type in {
        EvidenceSourceType.EXPERIENCE_BULLET,
        EvidenceSourceType.EXPERIENCE_SUMMARY,
    }:
        return ItemType.EXPERIENCE
    if source_type in {
        EvidenceSourceType.PROJECT_BULLET,
        EvidenceSourceType.PROJECT_SUMMARY,
    }:
        return ItemType.PROJECT
    if source_type == EvidenceSourceType.CERTIFICATION:
        return ItemType.CERTIFICATION
    return ItemType.SKILL


def _empty_personal_profile():
    from .models import PersonalProfile

    return PersonalProfile(
        id="person.synthetic",
        item_type="personal_profile",
        full_name="Synthetic Profile",
    )
