"""Helpers for building and validating Phase 2 provenance payloads."""

from __future__ import annotations

from .evidence_models import CanonicalEvidenceUnit, EvidenceSourceType
from .models import MasterProfile


def build_provenance_payload(evidence_unit: CanonicalEvidenceUnit) -> dict[str, object]:
    """Return a structured, API-safe provenance payload for a scored evidence unit."""

    provenance = evidence_unit.provenance
    return {
        "evidence_id": evidence_unit.evidence_id,
        "evidence_unit_id": evidence_unit.evidence_unit_id,
        "source_type": evidence_unit.source_type.value,
        "source_section": provenance.source_section.value,
        "source_item_type": provenance.source_item_type.value,
        "source_entity_id": provenance.source_parent_id,
        "source_parent_id": provenance.source_parent_id,
        "source_entity_title": provenance.source_parent_title,
        "source_parent_title": provenance.source_parent_title,
        "source_organization": provenance.source_organization,
        "source_child_id": provenance.source_child_id,
        "source_child_type": provenance.source_child_type.value if provenance.source_child_type is not None else None,
        "source_child_index": provenance.source_child_index,
        "source_bullet_id": evidence_unit.source_bullet_id,
        "extraction_method": provenance.extraction_method,
        "metric_ids": provenance.metric_ids,
        "source_links": [link.model_dump(mode="json") for link in provenance.source_links],
    }


def validate_provenance_against_profile(
    evidence_unit: CanonicalEvidenceUnit,
    profile: MasterProfile,
) -> list[str]:
    """Return provenance validation warnings for a canonical evidence unit."""

    warnings: list[str] = []
    provenance = evidence_unit.provenance

    entity_ids = {
        *(entry.id for entry in profile.experience),
        *(entry.id for entry in profile.projects),
        *(entry.id for entry in profile.education),
        *(entry.id for entry in profile.certifications),
        *(entry.id for entry in profile.awards),
        *(entry.id for entry in profile.skills),
    }
    if provenance.source_parent_id not in entity_ids:
        warnings.append(f"missing source entity reference: {provenance.source_parent_id}")

    if evidence_unit.source_type in {
        EvidenceSourceType.EXPERIENCE_BULLET,
        EvidenceSourceType.PROJECT_BULLET,
    }:
        bullet_ids = {
            *(bullet.id for entry in profile.experience for bullet in entry.bullets),
            *(bullet.id for entry in profile.projects for bullet in entry.bullets),
        }
        if evidence_unit.source_bullet_id is None or evidence_unit.source_bullet_id not in bullet_ids:
            warnings.append(
                f"missing source bullet reference: {evidence_unit.source_bullet_id or 'none'}"
            )

    return warnings


def selection_provenance_payload(scored_payload: dict[str, object]) -> dict[str, object]:
    """Project scored-item provenance into the minimal selection-safe payload."""

    return {
        "evidence_unit_id": scored_payload.get("evidence_unit_id"),
        "source_type": scored_payload.get("source_type"),
        "source_section": scored_payload.get("source_section"),
        "source_item_type": scored_payload.get("source_item_type"),
        "source_entity_id": scored_payload.get("source_entity_id"),
        "source_parent_id": scored_payload.get("source_parent_id"),
        "source_entity_title": scored_payload.get("source_entity_title"),
        "source_parent_title": scored_payload.get("source_parent_title"),
        "source_organization": scored_payload.get("source_organization"),
        "source_child_id": scored_payload.get("source_child_id"),
        "source_child_index": scored_payload.get("source_child_index"),
        "source_bullet_id": scored_payload.get("source_bullet_id"),
    }
