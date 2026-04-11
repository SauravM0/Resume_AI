"""Provenance map builder for Phase 4 verification.

The service links generated Phase 3 resume content back to the master resume
source of truth. The algorithm is deterministic:

1. Use Phase 3 stable source item and bullet IDs whenever present.
2. Classify relation type from explicit support shape and source text equality.
3. Capture matched tokens/spans for debugging.
4. Use token-overlap fallback only when stable IDs cannot produce a link.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from backend.app.schemas.verification import ProvenanceLink
from backend.app.services.verification.matchers import (
    SimilarityMatch,
    SourceBulletRecord,
    SourceEntityRecord,
    SourceIndex,
    find_best_bullet_fallback,
    find_best_entity_fallback,
    normalize_text,
    score_text_overlap,
)
from backend.app.services.verification.types import EvidenceStrength, ProvenanceRelationType
from resume_optimizer.models import ItemType, MasterProfile, NonEmptyStr, StableId, StrictModel
from resume_optimizer.phase3_models import (
    GeneratedBullet as Phase3GeneratedBullet,
    GeneratedSkillHighlight,
    GeneratedSummary,
    Phase3GenerationResult,
    SourceReference,
    SupportLevel,
)

if TYPE_CHECKING:
    from backend.app.db.repositories.verification_repository import VerificationRepository


class ProvenanceMatch(StrictModel):
    """One deterministic provenance edge from generated text to source truth."""

    generated_item_key: StableId
    generated_item_type: NonEmptyStr
    generated_text: NonEmptyStr
    source_entity_type: ItemType
    source_entity_id: StableId
    source_bullet_id: StableId | None = None
    relation_type: ProvenanceRelationType
    evidence_strength: EvidenceStrength
    matched_tokens: list[NonEmptyStr] = Field(default_factory=list)
    source_span_json: dict[str, object] = Field(default_factory=dict)
    generated_span_json: dict[str, object] = Field(default_factory=dict)
    support_level: SupportLevel | None = None
    support_score: float | None = Field(default=None, ge=0.0, le=1.0)

    def to_schema_link(self) -> ProvenanceLink:
        """Convert this match into the public verification provenance schema."""

        return ProvenanceLink(
            source_item_id=self.source_entity_id,
            source_item_type=self.source_entity_type,
            source_bullet_id=self.source_bullet_id,
            generated_text_span=", ".join(self.matched_tokens) if self.matched_tokens else None,
            evidence_strength=self.evidence_strength,
            relation_type=self.relation_type,
            support_level=self.support_level,
            support_score=self.support_score,
        )


class ProvenanceMap(StrictModel):
    """Complete provenance result for a generated Phase 3 resume artifact."""

    source_profile_id: StableId
    matches: list[ProvenanceMatch] = Field(default_factory=list)
    unmatched_item_keys: list[StableId] = Field(default_factory=list)


class ProvenanceService:
    """Build and persist provenance maps for generated resume content."""

    def build_for_phase3_result(
        self,
        *,
        source_profile: MasterProfile,
        phase3_result: Phase3GenerationResult,
    ) -> ProvenanceMap:
        """Build provenance links for all supported Phase 3 generated item types."""

        source_index = SourceIndex(source_profile)
        matches: list[ProvenanceMatch] = []
        unmatched: list[str] = []

        if phase3_result.summary is not None:
            summary_matches = self.map_generated_summary(
                summary=phase3_result.summary,
                source_index=source_index,
            )
            matches.extend(summary_matches)
            if not summary_matches:
                unmatched.append("summary")

        for experience in phase3_result.selected_experiences:
            for bullet in experience.generated_bullets:
                bullet_matches = self.map_generated_experience_bullet(
                    bullet=bullet,
                    source_index=source_index,
                )
                matches.extend(bullet_matches)
                if not bullet_matches:
                    unmatched.append(bullet.id)

        for project in phase3_result.selected_projects:
            for bullet in project.generated_bullets:
                bullet_matches = self.map_generated_project_bullet(
                    bullet=bullet,
                    source_index=source_index,
                )
                matches.extend(bullet_matches)
                if not bullet_matches:
                    unmatched.append(bullet.id)

        for skill in phase3_result.skills_to_highlight:
            skill_matches = self.map_generated_skill_highlight(
                skill=skill,
                source_index=source_index,
            )
            matches.extend(skill_matches)
            if not skill_matches:
                unmatched.append(f"skill.{normalize_text(skill.skill_name).replace(' ', '.')}")

        return ProvenanceMap(
            source_profile_id=source_profile.id,
            matches=matches,
            unmatched_item_keys=unmatched,
        )

    def map_generated_experience_bullet(
        self,
        *,
        bullet: Phase3GeneratedBullet,
        source_index: SourceIndex,
    ) -> list[ProvenanceMatch]:
        """Map a generated experience bullet to source experience bullet evidence."""

        return self._map_generated_bullet(
            bullet=bullet,
            source_index=source_index,
            expected_source_type=ItemType.EXPERIENCE,
        )

    def map_generated_project_bullet(
        self,
        *,
        bullet: Phase3GeneratedBullet,
        source_index: SourceIndex,
    ) -> list[ProvenanceMatch]:
        """Map a generated project bullet to source project bullet evidence."""

        return self._map_generated_bullet(
            bullet=bullet,
            source_index=source_index,
            expected_source_type=ItemType.PROJECT,
        )

    def map_generated_summary(
        self,
        *,
        summary: GeneratedSummary,
        source_index: SourceIndex,
    ) -> list[ProvenanceMatch]:
        """Map a generated summary statement to one or more source entities/bullets."""

        return self._map_generated_text_item(
            item_key="summary",
            item_type="summary",
            generated_text=summary.text,
            source_references=summary.provenance,
            source_index=source_index,
            fallback_allowed=True,
        )

    def map_generated_skill_highlight(
        self,
        *,
        skill: GeneratedSkillHighlight,
        source_index: SourceIndex,
    ) -> list[ProvenanceMatch]:
        """Map a highlighted skill to explicit skill records or bullet evidence."""

        matches = self._map_generated_text_item(
            item_key=f"skill.{normalize_text(skill.skill_name).replace(' ', '.')}",
            item_type="skill_statement",
            generated_text=skill.skill_name,
            source_references=skill.provenance,
            source_index=source_index,
            fallback_allowed=False,
        )
        if matches:
            return matches

        skill_entry = source_index.skills_by_normalized_name.get(normalize_text(skill.skill_name))
        if skill_entry is not None:
            similarity = score_text_overlap(skill.skill_name, skill_entry.name)
            return [
                self._match_from_entity(
                    item_key=f"skill.{normalize_text(skill.skill_name).replace(' ', '.')}",
                    item_type="skill_statement",
                    generated_text=skill.skill_name,
                    entity=SourceEntityRecord(
                        entity_id=skill_entry.id,
                        entity_type=ItemType.SKILL,
                        text=skill_entry.name,
                    ),
                    relation_type=ProvenanceRelationType.DIRECT_COPY,
                    similarity=similarity,
                    support_level=skill.support_level,
                    support_score=skill.confidence_score,
                )
            ]

        fallback = find_best_bullet_fallback(
            generated_text=skill.skill_name,
            source_index=source_index,
        )
        if fallback is None:
            return []
        source_bullet, similarity = fallback
        return [
            self._match_from_bullet(
                item_key=f"skill.{normalize_text(skill.skill_name).replace(' ', '.')}",
                item_type="skill_statement",
                generated_text=skill.skill_name,
                source_bullet=source_bullet,
                relation_type=ProvenanceRelationType.DIRECT_REWRITE,
                similarity=similarity,
                support_level=skill.support_level,
                support_score=skill.confidence_score,
            )
        ]

    def persist_matches(
        self,
        *,
        repository: "VerificationRepository",
        verification_item_id: str,
        matches: list[ProvenanceMatch],
    ) -> None:
        """Persist provenance matches through the Task 2 repository layer."""

        from backend.app.db.repositories.verification_repository import ProvenanceLinkCreate

        repository.add_provenance_links(
            verification_item_id=verification_item_id,
            links=[
                ProvenanceLinkCreate(
                    source_entity_type=match.source_entity_type,
                    source_entity_id=match.source_entity_id,
                    source_bullet_id=match.source_bullet_id,
                    relation_type=match.relation_type,
                    evidence_strength=match.evidence_strength,
                    matched_tokens_json=list(match.matched_tokens),
                )
                for match in matches
            ],
        )

    def _map_generated_bullet(
        self,
        *,
        bullet: Phase3GeneratedBullet,
        source_index: SourceIndex,
        expected_source_type: ItemType,
    ) -> list[ProvenanceMatch]:
        """ID-first mapping for generated bullets with similarity fallback."""

        explicit_matches = self._map_generated_text_item(
            item_key=bullet.id,
            item_type=f"{expected_source_type.value}_bullet",
            generated_text=bullet.rewritten_text,
            source_references=bullet.provenance,
            source_index=source_index,
            fallback_allowed=False,
        )
        explicit_matches = [
            match for match in explicit_matches if match.source_entity_type == expected_source_type
        ]
        if explicit_matches:
            return explicit_matches

        fallback = find_best_bullet_fallback(
            generated_text=bullet.rewritten_text,
            source_index=source_index,
            allowed_entity_type=expected_source_type,
        )
        if fallback is None:
            return []
        source_bullet, similarity = fallback
        return [
            self._match_from_bullet(
                item_key=bullet.id,
                item_type=f"{expected_source_type.value}_bullet",
                generated_text=bullet.rewritten_text,
                source_bullet=source_bullet,
                relation_type=ProvenanceRelationType.DIRECT_REWRITE,
                similarity=similarity,
                support_level=bullet.support_level,
                support_score=bullet.confidence_score,
            )
        ]

    def _map_generated_text_item(
        self,
        *,
        item_key: str,
        item_type: str,
        generated_text: str,
        source_references: list[SourceReference],
        source_index: SourceIndex,
        fallback_allowed: bool,
    ) -> list[ProvenanceMatch]:
        """Map arbitrary generated text using explicit source references first."""

        matches: list[ProvenanceMatch] = []
        seen: set[tuple[str, str | None]] = set()
        relation_type = self._relation_type_for_references(
            item_type,
            generated_text,
            source_references,
            source_index,
        )
        for reference in source_references:
            key = (reference.source_item_id, reference.source_bullet_id)
            if key in seen:
                continue
            seen.add(key)
            if reference.source_bullet_id is not None:
                source_bullet = source_index.bullets_by_id.get(reference.source_bullet_id)
                if source_bullet is None:
                    continue
                matches.append(
                    self._match_from_bullet(
                        item_key=item_key,
                        item_type=item_type,
                        generated_text=generated_text,
                        source_bullet=source_bullet,
                        relation_type=relation_type,
                        similarity=score_text_overlap(generated_text, source_bullet.text),
                        support_level=reference.support_level,
                        support_score=reference.support_score,
                    )
                )
                continue

            source_entity = source_index.entities_by_id.get(reference.source_item_id)
            if source_entity is None:
                continue
            matches.append(
                self._match_from_entity(
                    item_key=item_key,
                    item_type=item_type,
                    generated_text=generated_text,
                    entity=source_entity,
                    relation_type=relation_type,
                    similarity=score_text_overlap(generated_text, source_entity.text),
                    support_level=reference.support_level,
                    support_score=reference.support_score,
                )
            )

        if matches or not fallback_allowed:
            return matches

        fallback = find_best_entity_fallback(
            generated_text=generated_text,
            source_index=source_index,
        )
        if fallback is None:
            return []
        source_entity, similarity = fallback
        return [
            self._match_from_entity(
                item_key=item_key,
                item_type=item_type,
                generated_text=generated_text,
                entity=source_entity,
                relation_type=ProvenanceRelationType.DIRECT_REWRITE,
                similarity=similarity,
                support_level=None,
                support_score=similarity.score,
            )
        ]

    def _relation_type_for_references(
        self,
        item_type: str,
        generated_text: str,
        source_references: list[SourceReference],
        source_index: SourceIndex,
    ) -> ProvenanceRelationType:
        """Classify generated/source relation from explicit reference shape."""

        unique_bullet_ids = {
            reference.source_bullet_id
            for reference in source_references
            if reference.source_bullet_id is not None
        }
        unique_item_ids = {reference.source_item_id for reference in source_references}
        if item_type == "summary" and len(unique_item_ids) > 1:
            return ProvenanceRelationType.INFERRED_FROM_MULTIPLE_SUPPORTED_SOURCES
        if len(unique_bullet_ids) > 1:
            return ProvenanceRelationType.MERGED_FROM_MULTIPLE
        if len(unique_item_ids) > 1:
            return ProvenanceRelationType.INFERRED_FROM_MULTIPLE_SUPPORTED_SOURCES

        if len(unique_bullet_ids) == 1:
            bullet_id = next(iter(unique_bullet_ids))
            source_bullet = source_index.bullets_by_id.get(bullet_id)
            if source_bullet is not None and normalize_text(generated_text) == normalize_text(source_bullet.text):
                return ProvenanceRelationType.DIRECT_COPY
        return ProvenanceRelationType.DIRECT_REWRITE

    def _match_from_bullet(
        self,
        *,
        item_key: str,
        item_type: str,
        generated_text: str,
        source_bullet: SourceBulletRecord,
        relation_type: ProvenanceRelationType,
        similarity: SimilarityMatch,
        support_level: SupportLevel | None,
        support_score: float | None,
    ) -> ProvenanceMatch:
        """Create a provenance match from a source bullet record."""

        evidence_strength = (
            EvidenceStrength.EXACT
            if relation_type == ProvenanceRelationType.DIRECT_COPY
            else similarity.evidence_strength
        )
        return ProvenanceMatch(
            generated_item_key=item_key,
            generated_item_type=item_type,
            generated_text=generated_text,
            source_entity_type=source_bullet.entity_type,
            source_entity_id=source_bullet.entity_id,
            source_bullet_id=source_bullet.bullet_id,
            relation_type=relation_type,
            evidence_strength=evidence_strength,
            matched_tokens=similarity.matched_tokens,
            source_span_json={"text": source_bullet.text, "matched_tokens": similarity.matched_tokens},
            generated_span_json={"text": generated_text, "matched_tokens": similarity.matched_tokens},
            support_level=support_level,
            support_score=support_score,
        )

    def _match_from_entity(
        self,
        *,
        item_key: str,
        item_type: str,
        generated_text: str,
        entity: SourceEntityRecord,
        relation_type: ProvenanceRelationType,
        similarity: SimilarityMatch,
        support_level: SupportLevel | None,
        support_score: float | None,
    ) -> ProvenanceMatch:
        """Create a provenance match from a source entity record."""

        evidence_strength = (
            EvidenceStrength.EXACT
            if relation_type == ProvenanceRelationType.DIRECT_COPY
            else similarity.evidence_strength
        )
        return ProvenanceMatch(
            generated_item_key=item_key,
            generated_item_type=item_type,
            generated_text=generated_text,
            source_entity_type=entity.entity_type,
            source_entity_id=entity.entity_id,
            relation_type=relation_type,
            evidence_strength=evidence_strength,
            matched_tokens=similarity.matched_tokens,
            source_span_json={"text": entity.text, "matched_tokens": similarity.matched_tokens},
            generated_span_json={"text": generated_text, "matched_tokens": similarity.matched_tokens},
            support_level=support_level,
            support_score=support_score,
        )
