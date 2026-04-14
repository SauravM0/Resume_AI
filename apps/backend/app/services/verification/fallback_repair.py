"""Conservative Phase 6 fallback repair service."""

from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.schemas.verification import (
    VerificationItemResult,
    VerificationRepairAudit,
    VerificationRepairRecord,
)
from backend.app.services.verification.deterministic_validators import (
    SelectedContentContext,
    SourceContext,
)
from backend.app.services.verification.summary_verifier import (
    build_summary_fallback_plan,
    extract_summary_claims,
)
from backend.app.services.verification.types import (
    FallbackAction,
    IssueCategory,
    RepairExecutionStatus,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.models import BulletEntry, MasterProfile, NonEmptyStr
from resume_optimizer.phase3_models import (
    GeneratedBullet,
    GeneratedSkillHighlight,
    Phase3GenerationPayload,
    Phase3GenerationResult,
)

_VERB_DOWNGRADE_MAP: tuple[tuple[str, str], ...] = (
    ("spearheaded", "helped deliver"),
    ("architected", "helped build"),
    ("owned", "supported"),
    ("drove", "helped advance"),
    ("led", "contributed to"),
    ("managed", "collaborated with"),
    ("mentored", "supported"),
)
_PHRASE_DOWNGRADE_MAP: tuple[tuple[str, str], ...] = (
    ("end-to-end ownership", "delivery support"),
    ("stakeholder management", "cross-functional collaboration"),
    ("people management", "team collaboration"),
    ("technical leadership", "technical contribution"),
    ("technical direction", "technical contribution"),
)
_STRIP_PHRASES_BY_CATEGORY: dict[IssueCategory, tuple[str, ...]] = {
    IssueCategory.UNSUPPORTED_CERTIFICATION: (
        "aws certified",
        "google cloud certified",
        "microsoft certified",
        "certified",
        "certification",
    ),
    IssueCategory.UNSUPPORTED_AWARD: (
        "award-winning",
        "dean's list",
        "honors",
        "scholarship",
        "top performer",
        "with distinction",
    ),
    IssueCategory.UNSUPPORTED_DOMAIN: (
        "machine learning",
        "ai/ml",
        "artificial intelligence",
        "distributed systems",
        "security",
        "payments",
        "fintech",
        "healthcare",
    ),
    IssueCategory.UNSUPPORTED_SCOPE: (
        "architecture",
        "company-wide",
        "org-wide",
        "global scale",
        "large-scale",
        "multi-region",
        "platform strategy",
        "system design",
    ),
    IssueCategory.UNSUPPORTED_LEADERSHIP: (
        "leadership",
        "people management",
        "stakeholder management",
        "technical leadership",
        "technical direction",
        "managed a team",
        "managed engineers",
    ),
}
_SKILL_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "amazon web services": ("aws",),
    "aws": ("amazon web services",),
    "google cloud": ("gcp", "google cloud platform"),
    "gcp": ("google cloud", "google cloud platform"),
    "postgres": ("postgresql",),
    "postgresql": ("postgres",),
    "js": ("javascript",),
    "javascript": ("js",),
    "ts": ("typescript",),
    "typescript": ("ts",),
    "k8s": ("kubernetes",),
    "kubernetes": ("k8s",),
}


@dataclass(slots=True)
class RepairExecutionResult:
    """Mutable Phase 3 artifact plus explicit repair audit."""

    repaired_result: Phase3GenerationResult
    repaired_item_results: list[VerificationItemResult]
    repair_audit: VerificationRepairAudit


class FallbackRepairService:
    """Apply deterministic, source-backed repairs for verifier-approved fallbacks."""

    def apply(
        self,
        *,
        phase3_result: Phase3GenerationResult,
        source_profile: MasterProfile,
        generation_payload: Phase3GenerationPayload,
        item_results: list[VerificationItemResult],
    ) -> RepairExecutionResult:
        repaired_result = phase3_result.model_copy(deep=True)
        repaired_item_results = [item.model_copy(deep=True) for item in item_results]
        audit = VerificationRepairAudit()
        bullet_by_id = _generated_bullets_by_id(repaired_result)
        source_bullets = _source_bullets_by_id(source_profile)
        skill_indexes = _generated_skill_indexes(repaired_result)
        summary_item = repaired_result.summary
        selected_context = SelectedContentContext.from_generation_payload(generation_payload)
        source_context = SourceContext.from_entire_profile(source_profile)

        for item in repaired_item_results:
            if item.fallback_action not in {
                FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
                FallbackAction.REMOVE_CLAIM,
                FallbackAction.USE_SOURCE_TEXT,
                FallbackAction.DROP_ITEM,
            }:
                continue
            audit.attempted_item_ids.append(item.item_id)
            if item.item_type.endswith("_bullet"):
                record = self._repair_bullet(
                    item=item,
                    bullet=bullet_by_id.get(item.item_id),
                    source_bullets=source_bullets,
                )
            elif item.item_type == "summary":
                record = self._repair_summary(
                    item=item,
                    summary=summary_item,
                    source_context=source_context,
                    selected_context=selected_context,
                )
            elif item.item_type == "skill_statement":
                record = self._repair_skill(
                    item=item,
                    repaired_result=repaired_result,
                    skill_indexes=skill_indexes,
                    source_profile=source_profile,
                )
            else:
                record = VerificationRepairRecord(
                    item_id=item.item_id,
                    item_type=item.item_type,
                    fallback_action=item.fallback_action,
                    status=RepairExecutionStatus.FAILED,
                    strategy="no_supported_repair_strategy",
                    requires_regeneration=True,
                    notes=["No conservative repair strategy was available for this item type."],
                )
            audit.records.append(record)
            if record.status is RepairExecutionStatus.APPLIED:
                audit.repaired_item_ids.append(item.item_id)
                item.decision_outcome = VerificationDecisionOutcome.REPAIR_AND_PASS
                item.status = VerificationStatus.PASSED_WITH_WARNINGS
            else:
                audit.failed_item_ids.append(item.item_id)
                item.retryable = True
                item.status = VerificationStatus.FAILED
                item.decision_outcome = VerificationDecisionOutcome.REGENERATE_TARGET
            if record.requires_regeneration:
                audit.requires_regeneration_item_ids.append(item.item_id)
                item.retryable = True
                item.status = VerificationStatus.FAILED
                item.decision_outcome = VerificationDecisionOutcome.REGENERATE_TARGET

        return RepairExecutionResult(
            repaired_result=repaired_result,
            repaired_item_results=repaired_item_results,
            repair_audit=audit,
        )

    def _repair_bullet(
        self,
        *,
        item: VerificationItemResult,
        bullet: GeneratedBullet | None,
        source_bullets: dict[str, BulletEntry],
    ) -> VerificationRepairRecord:
        if bullet is None:
            return VerificationRepairRecord(
                item_id=item.item_id,
                item_type=item.item_type,
                fallback_action=item.fallback_action,
                status=RepairExecutionStatus.FAILED,
                strategy="missing_generated_bullet",
                source_item_ids=item.issues[0].source_item_ids if item.issues else [],
                source_bullet_ids=item.issues[0].source_bullet_ids if item.issues else [],
                requires_regeneration=True,
                notes=["Generated bullet could not be located for repair."],
            )
        original_text = bullet.rewritten_text
        degraded_text, removed_fragments, strategy = _downgrade_or_strip_bullet(
            text=original_text,
            categories={issue.category for issue in item.issues},
        )
        if degraded_text is not None and degraded_text != original_text:
            bullet.rewritten_text = degraded_text
            return VerificationRepairRecord(
                item_id=item.item_id,
                item_type=item.item_type,
                fallback_action=item.fallback_action,
                status=RepairExecutionStatus.APPLIED,
                strategy=strategy,
                original_text=original_text,
                repaired_text=degraded_text,
                removed_fragments=removed_fragments,
                source_item_ids=item.issues[0].source_item_ids if item.issues else [],
                source_bullet_ids=item.issues[0].source_bullet_ids if item.issues else [],
                notes=["Applied deterministic phrase downgrade before falling back to source text."],
            )

        source_text = _first_source_bullet_text(bullet, source_bullets)
        if source_text is None:
            return VerificationRepairRecord(
                item_id=item.item_id,
                item_type=item.item_type,
                fallback_action=item.fallback_action,
                status=RepairExecutionStatus.FAILED,
                strategy="missing_source_bullet_fallback",
                original_text=original_text,
                source_item_ids=item.issues[0].source_item_ids if item.issues else [],
                source_bullet_ids=item.issues[0].source_bullet_ids if item.issues else list(bullet.source_bullet_ids),
                requires_regeneration=True,
                notes=["Safe fallback to a source bullet was requested but no source bullet text was available."],
            )
        bullet.rewritten_text = source_text
        return VerificationRepairRecord(
            item_id=item.item_id,
            item_type=item.item_type,
            fallback_action=item.fallback_action,
            status=RepairExecutionStatus.APPLIED,
            strategy="fallback_to_source_bullet",
            original_text=original_text,
            repaired_text=source_text,
            source_item_ids=item.issues[0].source_item_ids if item.issues else [],
            source_bullet_ids=item.issues[0].source_bullet_ids if item.issues else list(bullet.source_bullet_ids),
            notes=["Replaced unsupported rewrite with literal source-backed bullet text."],
        )

    def _repair_summary(
        self,
        *,
        item: VerificationItemResult,
        summary,
        source_context: SourceContext,
        selected_context: SelectedContentContext,
    ) -> VerificationRepairRecord:
        if summary is None:
            return VerificationRepairRecord(
                item_id=item.item_id,
                item_type=item.item_type,
                fallback_action=item.fallback_action,
                status=RepairExecutionStatus.FAILED,
                strategy="missing_generated_summary",
                requires_regeneration=True,
                notes=["Generated summary could not be located for repair."],
            )
        original_text = summary.text
        safe_summary = item.fallback_preview
        if not safe_summary:
            fallback_plan = build_summary_fallback_plan(
                summary_text=summary.text,
                claims=extract_summary_claims(summary.text),
                issues=item.issues,
                source_context=source_context,
                selected_context=selected_context,
            )
            safe_summary = fallback_plan.safe_summary_text
        summary.text = safe_summary
        return VerificationRepairRecord(
            item_id=item.item_id,
            item_type=item.item_type,
            fallback_action=item.fallback_action,
            status=RepairExecutionStatus.APPLIED,
            strategy="rebuild_summary_from_controlled_inputs",
            original_text=original_text,
            repaired_text=safe_summary,
            removed_fragments=_summary_removed_fragments(item),
            source_item_ids=item.issues[0].source_item_ids if item.issues else list(summary.source_item_ids),
            source_bullet_ids=item.issues[0].source_bullet_ids if item.issues else list(summary.source_bullet_ids),
            notes=[
                "Dropped unsupported summary fragments.",
                "Shortened summary to source-backed wording only.",
            ],
        )

    def _repair_skill(
        self,
        *,
        item: VerificationItemResult,
        repaired_result: Phase3GenerationResult,
        skill_indexes: dict[str, int],
        source_profile: MasterProfile,
    ) -> VerificationRepairRecord:
        index = skill_indexes.get(item.item_id)
        if index is None or index >= len(repaired_result.skills_to_highlight):
            return VerificationRepairRecord(
                item_id=item.item_id,
                item_type=item.item_type,
                fallback_action=item.fallback_action,
                status=RepairExecutionStatus.FAILED,
                strategy="missing_generated_skill_highlight",
                requires_regeneration=True,
                notes=["Generated skill highlight could not be located for repair."],
            )
        skill = repaired_result.skills_to_highlight[index]
        original_name = skill.skill_name
        replacement = _deterministic_skill_alias(original_name, source_profile)
        if replacement is not None:
            skill.skill_name = replacement
            return VerificationRepairRecord(
                item_id=item.item_id,
                item_type=item.item_type,
                fallback_action=item.fallback_action,
                status=RepairExecutionStatus.APPLIED,
                strategy="replace_with_supported_skill_alias",
                original_text=original_name,
                repaired_text=replacement,
                source_item_ids=list(skill.source_item_ids),
                notes=["Replaced unsupported skill wording with an exact supported skill alias."],
            )
        repaired_result.skills_to_highlight.pop(index)
        _reindex_skills(repaired_result, skill_indexes)
        return VerificationRepairRecord(
            item_id=item.item_id,
            item_type=item.item_type,
            fallback_action=item.fallback_action,
            status=RepairExecutionStatus.APPLIED,
            strategy="drop_unsupported_skill_highlight",
            original_text=original_name,
            source_item_ids=list(skill.source_item_ids),
            notes=["Removed unsupported highlighted skill because no deterministic supported mapping existed."],
        )


def _generated_bullets_by_id(result: Phase3GenerationResult) -> dict[str, GeneratedBullet]:
    bullets: dict[str, GeneratedBullet] = {}
    for experience in result.selected_experiences:
        for bullet in experience.generated_bullets:
            bullets[bullet.id] = bullet
    for project in result.selected_projects:
        for bullet in project.generated_bullets:
            bullets[bullet.id] = bullet
    return bullets


def _source_bullets_by_id(source_profile: MasterProfile) -> dict[str, BulletEntry]:
    bullets: dict[str, BulletEntry] = {}
    for experience in source_profile.experience:
        for bullet in experience.bullets:
            bullets[bullet.id] = bullet
    for project in source_profile.projects:
        for bullet in project.bullets:
            bullets[bullet.id] = bullet
    for education in source_profile.education:
        for bullet in education.bullets:
            bullets[bullet.id] = bullet
    for award in source_profile.awards:
        for bullet in award.bullets:
            bullets[bullet.id] = bullet
    return bullets


def _generated_skill_indexes(result: Phase3GenerationResult) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, skill in enumerate(result.skills_to_highlight):
        normalized = ".".join(skill.skill_name.lower().split())
        indexes[f"skill.{normalized}"] = index
    return indexes


def _reindex_skills(result: Phase3GenerationResult, indexes: dict[str, int]) -> None:
    indexes.clear()
    indexes.update(_generated_skill_indexes(result))


def _first_source_bullet_text(
    bullet: GeneratedBullet,
    source_bullets: dict[str, BulletEntry],
) -> str | None:
    for bullet_id in bullet.source_bullet_ids:
        source = source_bullets.get(bullet_id)
        if source is not None:
            return source.text
    return None


def _downgrade_or_strip_bullet(
    *,
    text: str,
    categories: set[IssueCategory],
) -> tuple[str | None, list[str], str]:
    updated = text
    removed_fragments: list[str] = []
    strategy = "strip_unsupported_phrase"
    for source, target in _VERB_DOWNGRADE_MAP:
        updated = re.sub(rf"\b{re.escape(source)}\b", target, updated, flags=re.IGNORECASE)
    for source, target in _PHRASE_DOWNGRADE_MAP:
        updated = re.sub(re.escape(source), target, updated, flags=re.IGNORECASE)
        updated = re.sub(re.escape(source.title()), target.capitalize(), updated)

    for category in categories:
        for phrase in _STRIP_PHRASES_BY_CATEGORY.get(category, ()):
            pattern = re.compile(rf"(?:,\s*)?\b{re.escape(phrase)}\b(?:\s*,)?", re.IGNORECASE)
            if pattern.search(updated):
                removed_fragments.append(phrase)
                updated = pattern.sub(" ", updated)

    updated = _clean_text(updated)
    if updated and updated != text:
        if removed_fragments:
            strategy = "strip_unsupported_phrase"
        else:
            strategy = "fallback_to_lighter_rewrite"
        return updated, sorted(set(removed_fragments)), strategy
    return None, [], strategy


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ,;")
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s*,", ", ", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\s+;", ";", cleaned)
    if cleaned and cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    if len(cleaned.split()) < 3:
        return ""
    return cleaned


def _deterministic_skill_alias(skill_name: str, source_profile: MasterProfile) -> str | None:
    supported = {entry.name.casefold(): entry.name for entry in source_profile.skills}
    key = skill_name.casefold()
    for alias in _SKILL_ALIAS_MAP.get(key, ()):
        if alias in supported:
            return supported[alias]
    return None


def _summary_removed_fragments(item: VerificationItemResult) -> list[NonEmptyStr]:
    fragments: list[str] = []
    for issue in item.issues:
        if ": " in issue.message:
            fragments.append(issue.message.split(": ", 1)[1].strip())
    deduped = sorted({fragment for fragment in fragments if fragment})
    return [fragment for fragment in deduped]
