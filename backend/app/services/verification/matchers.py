"""Deterministic provenance matching helpers for Phase 4 verification.

The helpers in this module are intentionally simple and auditable. They prefer
stable Phase 3 source IDs and only use token overlap as a secondary fallback
when IDs are missing or unusable.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from backend.app.services.verification.types import EvidenceStrength
from resume_optimizer.models import (
    BulletEntry,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    ProjectEntry,
    SkillEntry,
)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9+#.]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True, slots=True)
class SourceEntityRecord:
    """Indexed source-truth entity available for provenance matching."""

    entity_id: str
    entity_type: ItemType
    text: str


@dataclass(frozen=True, slots=True)
class SourceBulletRecord:
    """Indexed source-truth bullet with its owning source entity."""

    bullet_id: str
    entity_id: str
    entity_type: ItemType
    text: str


@dataclass(frozen=True, slots=True)
class SimilarityMatch:
    """Transparent token-overlap match result used only as fallback evidence."""

    score: float
    evidence_strength: EvidenceStrength
    matched_tokens: list[str]


class SourceIndex:
    """Lookup index for stable source IDs and deterministic fallback search."""

    def __init__(self, profile: MasterProfile) -> None:
        """Build entity and bullet indexes from the master resume profile."""

        self.entities_by_id: dict[str, SourceEntityRecord] = {}
        self.bullets_by_id: dict[str, SourceBulletRecord] = {}
        self.skills_by_normalized_name: dict[str, SkillEntry] = {}

        for experience in profile.experience:
            self._add_experience(experience)
        for project in profile.projects:
            self._add_project(project)
        for skill in profile.skills:
            self._add_skill(skill)

    def _add_experience(self, experience: ExperienceEntry) -> None:
        bullet_text = " ".join(bullet.text for bullet in experience.bullets)
        self.entities_by_id[experience.id] = SourceEntityRecord(
            entity_id=experience.id,
            entity_type=ItemType.EXPERIENCE,
            text=" ".join(
                part
                for part in [
                    experience.organization,
                    experience.title,
                    " ".join(experience.tools),
                    bullet_text,
                ]
                if part
            ),
        )
        self._add_bullets(experience.id, ItemType.EXPERIENCE, experience.bullets)

    def _add_project(self, project: ProjectEntry) -> None:
        bullet_text = " ".join(bullet.text for bullet in project.bullets)
        self.entities_by_id[project.id] = SourceEntityRecord(
            entity_id=project.id,
            entity_type=ItemType.PROJECT,
            text=" ".join(
                part
                for part in [
                    project.name,
                    project.role,
                    project.summary,
                    " ".join(project.tools),
                    bullet_text,
                ]
                if part
            ),
        )
        self._add_bullets(project.id, ItemType.PROJECT, project.bullets)

    def _add_skill(self, skill: SkillEntry) -> None:
        self.entities_by_id[skill.id] = SourceEntityRecord(
            entity_id=skill.id,
            entity_type=ItemType.SKILL,
            text=" ".join(part for part in [skill.name, skill.category, " ".join(skill.tools)] if part),
        )
        self.skills_by_normalized_name[normalize_text(skill.name)] = skill

    def _add_bullets(
        self,
        entity_id: str,
        entity_type: ItemType,
        bullets: Iterable[BulletEntry],
    ) -> None:
        for bullet in bullets:
            self.bullets_by_id[bullet.id] = SourceBulletRecord(
                bullet_id=bullet.id,
                entity_id=entity_id,
                entity_type=entity_type,
                text=bullet.text,
            )


def normalize_text(value: str) -> str:
    """Normalize text for exact-copy and token fallback comparisons."""

    return " ".join(tokenize(value))


def tokenize(value: str) -> list[str]:
    """Tokenize text deterministically, dropping low-signal stopwords."""

    return [
        token.lower()
        for token in _TOKEN_PATTERN.findall(value)
        if token.lower() not in _STOPWORDS
    ]


def score_text_overlap(generated_text: str, source_text: str) -> SimilarityMatch:
    """Score generated/source overlap using deterministic token containment.

    The denominator is the shorter token set so concise generated claims can
    match longer source bullets without being penalized for unrelated context.
    """

    generated_tokens = set(tokenize(generated_text))
    source_tokens = set(tokenize(source_text))
    if not generated_tokens or not source_tokens:
        return SimilarityMatch(score=0.0, evidence_strength=EvidenceStrength.WEAK, matched_tokens=[])

    matched_tokens = sorted(generated_tokens & source_tokens)
    score = len(matched_tokens) / max(1, min(len(generated_tokens), len(source_tokens)))
    return SimilarityMatch(
        score=score,
        evidence_strength=evidence_strength_for_score(score),
        matched_tokens=matched_tokens,
    )


def evidence_strength_for_score(score: float) -> EvidenceStrength:
    """Convert an auditable token-overlap score into evidence strength."""

    if score >= 0.95:
        return EvidenceStrength.EXACT
    if score >= 0.70:
        return EvidenceStrength.STRONG
    if score >= 0.40:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.WEAK


def find_best_bullet_fallback(
    *,
    generated_text: str,
    source_index: SourceIndex,
    allowed_entity_type: ItemType | None = None,
) -> tuple[SourceBulletRecord, SimilarityMatch] | None:
    """Find the best source bullet by text overlap when stable IDs are absent."""

    best: tuple[SourceBulletRecord, SimilarityMatch] | None = None
    for bullet in source_index.bullets_by_id.values():
        if allowed_entity_type is not None and bullet.entity_type != allowed_entity_type:
            continue
        similarity = score_text_overlap(generated_text, bullet.text)
        if best is None or similarity.score > best[1].score:
            best = (bullet, similarity)
    if best is None or best[1].score <= 0:
        return None
    return best


def find_best_entity_fallback(
    *,
    generated_text: str,
    source_index: SourceIndex,
) -> tuple[SourceEntityRecord, SimilarityMatch] | None:
    """Find the best source entity by text overlap when stable IDs are absent."""

    best: tuple[SourceEntityRecord, SimilarityMatch] | None = None
    for entity in source_index.entities_by_id.values():
        similarity = score_text_overlap(generated_text, entity.text)
        if best is None or similarity.score > best[1].score:
            best = (entity, similarity)
    if best is None or best[1].score <= 0:
        return None
    return best
