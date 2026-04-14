"""Deterministic Phase 2 evidence deduplication and overlap resolution."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import re

from ..evidence_models import (
    EvidenceOverlapLink,
    EvidenceRelationshipType,
    EvidenceSourceType,
    EvidenceUnit,
    WeakEvidenceTag,
)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9.+#/-]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}
_SUMMARY_TYPES = {
    EvidenceSourceType.EXPERIENCE_SUMMARY,
    EvidenceSourceType.PROJECT_SUMMARY,
    EvidenceSourceType.PERSONAL_SUMMARY,
}
_SUPPORTING_TYPES = {
    EvidenceSourceType.SKILL_DECLARATION,
    EvidenceSourceType.CERTIFICATION,
    EvidenceSourceType.AWARD,
}


@dataclass(frozen=True)
class EvidenceOverlapResolution:
    evidence_units: list[EvidenceUnit]
    overlap_links: list[EvidenceOverlapLink]


class EvidenceOverlapResolutionService:
    """Build non-destructive overlap links and preserve legacy duplicate markers."""

    def resolve(self, evidence_units: list[EvidenceUnit]) -> EvidenceOverlapResolution:
        exact_groups = _group_exact_duplicates(evidence_units)
        primary_by_id: dict[str, str] = {}
        duplicate_tag_by_id: dict[str, WeakEvidenceTag] = {}
        links: list[EvidenceOverlapLink] = []

        for group in exact_groups:
            primary = _choose_primary(group)
            primary_by_id.setdefault(primary.evidence_id, primary.evidence_id)
            for unit in group:
                if unit.evidence_id == primary.evidence_id:
                    continue
                primary_by_id[unit.evidence_id] = primary.evidence_id
                duplicate_tag_by_id[unit.evidence_id] = WeakEvidenceTag.DUPLICATE
                links.append(
                    _build_overlap_link(
                        relationship_type=EvidenceRelationshipType.EXACT_DUPLICATE,
                        primary=primary,
                        related=unit,
                        confidence_score=1.0,
                        rationale="Exact duplicate canonical fingerprint and normalized text.",
                        suppress_as_repeat=True,
                    )
                )

        representatives = [_exact_group_primary(unit, exact_groups) for unit in evidence_units]
        unique_representatives = list({unit.evidence_id: unit for unit in representatives}.values())

        links.extend(self._near_duplicate_links(unique_representatives, primary_by_id, duplicate_tag_by_id))
        links.extend(self._parent_child_restatement_links(unique_representatives))
        links.extend(self._supporting_evidence_links(unique_representatives))

        resolved_units = [
            _apply_legacy_duplicate_marker(unit, primary_by_id, duplicate_tag_by_id)
            for unit in evidence_units
        ]
        return EvidenceOverlapResolution(
            evidence_units=resolved_units,
            overlap_links=_dedupe_links(links),
        )

    def _near_duplicate_links(
        self,
        evidence_units: list[EvidenceUnit],
        primary_by_id: dict[str, str],
        duplicate_tag_by_id: dict[str, WeakEvidenceTag],
    ) -> list[EvidenceOverlapLink]:
        links: list[EvidenceOverlapLink] = []
        for left_index, left in enumerate(evidence_units):
            for right in evidence_units[left_index + 1 :]:
                similarity = _near_duplicate_similarity(left, right)
                if similarity < 0.82:
                    continue
                primary = _choose_primary([left, right])
                related = right if primary.evidence_id == left.evidence_id else left
                current_primary = primary_by_id.get(related.evidence_id)
                if current_primary is None:
                    primary_by_id[related.evidence_id] = primary.evidence_id
                    duplicate_tag_by_id.setdefault(related.evidence_id, WeakEvidenceTag.NEAR_DUPLICATE)
                links.append(
                    _build_overlap_link(
                        relationship_type=EvidenceRelationshipType.NEAR_DUPLICATE,
                        primary=primary,
                        related=related,
                        confidence_score=round(similarity, 4),
                        rationale="High token overlap with aligned normalized skills/tools or metrics.",
                        suppress_as_repeat=True,
                    )
                )
        return links

    def _parent_child_restatement_links(
        self,
        evidence_units: list[EvidenceUnit],
    ) -> list[EvidenceOverlapLink]:
        links: list[EvidenceOverlapLink] = []
        by_parent: dict[str, list[EvidenceUnit]] = {}
        for unit in evidence_units:
            by_parent.setdefault(unit.parent_link.source_parent_id, []).append(unit)

        for group in by_parent.values():
            summaries = [unit for unit in group if unit.source_type in _SUMMARY_TYPES]
            details = [unit for unit in group if unit.source_type not in _SUMMARY_TYPES]
            for summary in summaries:
                for detail in details:
                    similarity = _restatement_similarity(summary, detail)
                    if similarity < 0.58:
                        continue
                    primary = _choose_primary([summary, detail])
                    related = detail if primary.evidence_id == summary.evidence_id else summary
                    links.append(
                        _build_overlap_link(
                            relationship_type=EvidenceRelationshipType.PARENT_CHILD_RESTATEMENT,
                            primary=primary,
                            related=related,
                            confidence_score=round(similarity, 4),
                            rationale="Summary and child evidence restate the same accomplishment within one parent entry.",
                            suppress_as_repeat=True,
                        )
                    )
        return links

    def _supporting_evidence_links(
        self,
        evidence_units: list[EvidenceUnit],
    ) -> list[EvidenceOverlapLink]:
        links: list[EvidenceOverlapLink] = []
        for left_index, left in enumerate(evidence_units):
            for right in evidence_units[left_index + 1 :]:
                support = _support_relationship(left, right)
                if support is None:
                    continue
                primary, related, confidence_score, rationale = support
                links.append(
                    _build_overlap_link(
                        relationship_type=EvidenceRelationshipType.SUPPORTING_EVIDENCE,
                        primary=primary,
                        related=related,
                        confidence_score=confidence_score,
                        rationale=rationale,
                        suppress_as_repeat=False,
                    )
                )
        return links


DEFAULT_EVIDENCE_OVERLAP_RESOLUTION_SERVICE = EvidenceOverlapResolutionService()


def _group_exact_duplicates(evidence_units: list[EvidenceUnit]) -> list[list[EvidenceUnit]]:
    groups: dict[str, list[EvidenceUnit]] = {}
    for unit in evidence_units:
        groups.setdefault(unit.dedupe_fingerprint, []).append(unit)
    return [group for group in groups.values() if len(group) > 1]


def _exact_group_primary(unit: EvidenceUnit, groups: list[list[EvidenceUnit]]) -> EvidenceUnit:
    for group in groups:
        if any(member.evidence_id == unit.evidence_id for member in group):
            return _choose_primary(group)
    return unit


def _choose_primary(units: list[EvidenceUnit]) -> EvidenceUnit:
    return max(units, key=_representation_score)


def _representation_score(unit: EvidenceUnit) -> tuple[float, int, int, int, str]:
    quality = unit.quality.overall_quality_score or unit.quality.specificity_score or 0.0
    metric_count = unit.coverage.source_metric_count
    detail_score = len(unit.normalized_tools) + len(unit.normalized_skills) + len(unit.normalized_domains)
    summary_penalty = 0 if unit.source_type in _SUMMARY_TYPES else 1
    return (
        quality,
        metric_count,
        detail_score,
        summary_penalty,
        unit.evidence_id,
    )


def _apply_legacy_duplicate_marker(
    unit: EvidenceUnit,
    primary_by_id: dict[str, str],
    duplicate_tag_by_id: dict[str, WeakEvidenceTag],
) -> EvidenceUnit:
    duplicate_of = primary_by_id.get(unit.evidence_id)
    if duplicate_of is None or duplicate_of == unit.evidence_id:
        return unit

    weak_tags = list(unit.quality.weak_evidence_tags)
    duplicate_tag = duplicate_tag_by_id.get(unit.evidence_id, WeakEvidenceTag.NEAR_DUPLICATE)
    if duplicate_tag not in weak_tags:
        weak_tags.append(duplicate_tag)
    return unit.model_copy(
        update={
            "duplicate_of": duplicate_of,
            "quality": unit.quality.model_copy(
                update={"weak_evidence_tags": list(dict.fromkeys(weak_tags))}
            ),
        }
    )


def _near_duplicate_similarity(left: EvidenceUnit, right: EvidenceUnit) -> float:
    left_tokens = _content_tokens(left.canonical_text)
    right_tokens = _content_tokens(right.canonical_text)
    if len(left_tokens) < 4 or len(right_tokens) < 4:
        return 0.0

    shared_skills = set(left.normalized_skills) & set(right.normalized_skills)
    shared_tools = set(left.normalized_tools) & set(right.normalized_tools)
    shared_domains = set(left.normalized_domains) & set(right.normalized_domains)
    shared_metrics = set(left.provenance.metric_ids) & set(right.provenance.metric_ids)

    jaccard = _jaccard(left_tokens, right_tokens)
    if jaccard < 0.72:
        return 0.0
    if len(left_tokens & right_tokens) < 5:
        return 0.0
    if not (shared_skills or shared_tools or shared_domains or shared_metrics or _same_outcome_shape(left, right)):
        return 0.0

    return min(1.0, jaccard + (0.08 if shared_skills or shared_tools else 0.0) + (0.04 if shared_metrics else 0.0))


def _restatement_similarity(summary: EvidenceUnit, detail: EvidenceUnit) -> float:
    summary_tokens = _content_tokens(summary.canonical_text)
    detail_tokens = _content_tokens(detail.canonical_text)
    if len(summary_tokens) < 3 or len(detail_tokens) < 3:
        return 0.0

    direct_overlap = _jaccard(summary_tokens, detail_tokens)
    shared_terms = (
        len(set(summary.normalized_skills) & set(detail.normalized_skills))
        + len(set(summary.normalized_tools) & set(detail.normalized_tools))
        + len(set(summary.normalized_domains) & set(detail.normalized_domains))
    )
    metric_bonus = 0.1 if summary.coverage.source_metric_count and detail.coverage.source_metric_count else 0.0
    if direct_overlap < 0.46 and shared_terms < 2:
        return 0.0
    return min(1.0, direct_overlap + min(shared_terms * 0.08, 0.24) + metric_bonus)


def _support_relationship(
    left: EvidenceUnit,
    right: EvidenceUnit,
) -> tuple[EvidenceUnit, EvidenceUnit, float, str] | None:
    if left.source_type == EvidenceSourceType.SKILL_DECLARATION or right.source_type == EvidenceSourceType.SKILL_DECLARATION:
        return _skill_support_relationship(left, right)

    if left.source_type in _SUPPORTING_TYPES or right.source_type in _SUPPORTING_TYPES:
        return _artifact_support_relationship(left, right)

    return None


def _skill_support_relationship(
    left: EvidenceUnit,
    right: EvidenceUnit,
) -> tuple[EvidenceUnit, EvidenceUnit, float, str] | None:
    if left.source_type == right.source_type == EvidenceSourceType.SKILL_DECLARATION:
        return None

    if left.source_type == EvidenceSourceType.SKILL_DECLARATION:
        declared, evidenced = left, right
    elif right.source_type == EvidenceSourceType.SKILL_DECLARATION:
        declared, evidenced = right, left
    else:
        return None

    shared_skills = set(declared.normalized_skills) & set(evidenced.normalized_skills)
    shared_tools = set(declared.normalized_tools) & set(evidenced.normalized_tools)
    if not shared_skills and not shared_tools:
        return None
    if evidenced.source_type in _SUMMARY_TYPES:
        return None

    strength = 0.62 + min(0.12 * len(shared_skills | shared_tools), 0.24)
    return (
        evidenced,
        declared,
        round(min(strength, 0.94), 4),
        "Declared skill is explicitly supported by stronger evidence-backed accomplishment text.",
    )


def _artifact_support_relationship(
    left: EvidenceUnit,
    right: EvidenceUnit,
) -> tuple[EvidenceUnit, EvidenceUnit, float, str] | None:
    if left.source_type == right.source_type == EvidenceSourceType.SKILL_DECLARATION:
        return None

    if left.source_type in _SUPPORTING_TYPES and right.source_type in _SUPPORTING_TYPES:
        return None

    if left.source_type in _SUPPORTING_TYPES:
        related, primary = left, right
    elif right.source_type in _SUPPORTING_TYPES:
        related, primary = right, left
    else:
        return None

    shared_skills = set(related.normalized_skills) & set(primary.normalized_skills)
    shared_tools = set(related.normalized_tools) & set(primary.normalized_tools)
    shared_domains = set(related.normalized_domains) & set(primary.normalized_domains)
    shared_tokens = _content_tokens(related.canonical_text) & _content_tokens(primary.canonical_text)
    token_similarity = _jaccard(_content_tokens(related.canonical_text), _content_tokens(primary.canonical_text))

    if related.source_type == EvidenceSourceType.CERTIFICATION:
        if not shared_tokens and len(shared_skills | shared_tools | shared_domains) < 2:
            return None
    elif related.source_type == EvidenceSourceType.AWARD:
        if token_similarity < 0.35 and len(shared_tokens) < 2:
            return None
    elif not (shared_skills or shared_tools or shared_domains) and token_similarity < 0.42:
        return None

    return (
        primary,
        related,
        round(min(0.55 + token_similarity * 0.35, 0.9), 4),
        "Credential or award supports a stronger primary evidence item without replacing source truth.",
    )


def _build_overlap_link(
    *,
    relationship_type: EvidenceRelationshipType,
    primary: EvidenceUnit,
    related: EvidenceUnit,
    confidence_score: float,
    rationale: str,
    suppress_as_repeat: bool,
) -> EvidenceOverlapLink:
    shared_tokens = sorted(_content_tokens(primary.canonical_text) & _content_tokens(related.canonical_text))[:8]
    relationship_key = "|".join(
        [
            relationship_type.value,
            primary.evidence_id,
            related.evidence_id,
            ",".join(shared_tokens),
        ]
    )
    relationship_id = f"overlap.{sha1(relationship_key.encode('utf-8')).hexdigest()[:12]}"
    return EvidenceOverlapLink(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        primary_evidence_id=primary.evidence_id,
        related_evidence_id=related.evidence_id,
        confidence_score=confidence_score,
        same_parent=primary.parent_link.source_parent_id == related.parent_link.source_parent_id,
        suppress_as_repeat=suppress_as_repeat,
        prefer_primary=True,
        shared_tokens=shared_tokens,
        shared_skills=sorted(set(primary.normalized_skills) & set(related.normalized_skills)),
        shared_tools=sorted(set(primary.normalized_tools) & set(related.normalized_tools)),
        shared_domains=sorted(set(primary.normalized_domains) & set(related.normalized_domains)),
        rationale=rationale,
    )


def _dedupe_links(links: list[EvidenceOverlapLink]) -> list[EvidenceOverlapLink]:
    return list({link.relationship_id: link for link in links}.values())


def _same_outcome_shape(left: EvidenceUnit, right: EvidenceUnit) -> bool:
    return bool(set(left.signals.impact_types) & set(right.signals.impact_types))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _content_tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_PATTERN.findall(text)
        if len(token) > 2 and token.casefold() not in _STOPWORDS
    }
