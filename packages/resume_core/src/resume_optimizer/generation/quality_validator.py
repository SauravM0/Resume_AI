"""Deterministic writing-quality validation for Phase 5 generation outputs."""

from __future__ import annotations

from collections import Counter
import re

from .contracts import (
    AssembledExperienceSection,
    AssembledProjectSection,
    AssembledSkillSection,
    AssembledSummary,
    GenerationQualitySignals,
    QualityDimension,
    QualitySignal,
    QualitySignalSeverity,
    SectionAssemblyOutput,
    SkillPresentationOutput,
    SummaryGenerationOutput,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+#/%-]*")
_WEAK_FILLER_PHRASES = {
    "results-driven",
    "dynamic professional",
    "highly motivated",
    "passionate",
    "proven track record",
    "cutting-edge",
    "strategic thinker",
}
_WEAK_SUMMARY_TERMS = {
    "experienced professional",
    "worked on",
    "responsible for",
    "various",
    "multiple",
}
_BROAD_CLAIM_TERMS = {
    "end-to-end",
    "world-class",
    "best-in-class",
    "global",
    "cross-functional",
    "strategic",
}
_UNNATURAL_BULLET_PATTERNS = (
    re.compile(r"\b(and|with|for)\s+\1\b", re.IGNORECASE),
    re.compile(r"\b[a-z]+(?:/[a-z]+){2,}\b", re.IGNORECASE),
)


def merge_quality_signals(*signals: GenerationQualitySignals) -> GenerationQualitySignals:
    """Merge multiple deterministic quality reports into one aggregated result."""

    hard_failures: list[QualitySignal] = []
    warnings: list[QualitySignal] = []
    blocked_section_ids: list[str] = []
    dimension_scores: dict[QualityDimension, float] = {}
    provenance_scores: list[float] = []
    style_scores: list[float] = []

    for signal in signals:
        if signal is None:
            continue
        hard_failures.extend(signal.hard_failures)
        warnings.extend(signal.warnings)
        blocked_section_ids.extend(signal.blocked_section_ids)
        for dimension, score in signal.dimension_scores.items():
            dimension_scores[dimension] = round(
                min(dimension_scores.get(dimension, 1.0), float(score)),
                4,
            )
        if signal.provenance_coverage_score is not None:
            provenance_scores.append(float(signal.provenance_coverage_score))
        if signal.style_alignment_score is not None:
            style_scores.append(float(signal.style_alignment_score))

    return GenerationQualitySignals(
        hard_failures=hard_failures,
        warnings=warnings,
        blocked_section_ids=_stable_unique(blocked_section_ids),
        dimension_scores=dimension_scores,
        passed=not hard_failures,
        provenance_coverage_score=round(sum(provenance_scores) / len(provenance_scores), 4)
        if provenance_scores
        else None,
        style_alignment_score=round(sum(style_scores) / len(style_scores), 4) if style_scores else None,
    )


def validate_summary_quality(summary: SummaryGenerationOutput) -> GenerationQualitySignals:
    """Validate summary writing quality and generation hygiene."""

    text = summary.summary_text.strip()
    tokens = _tokenize(text)
    hard_failures: list[QualitySignal] = []
    warnings: list[QualitySignal] = []
    scores = {
        QualityDimension.GENERIC_FILLER: 1.0,
        QualityDimension.KEYWORD_STUFFING: 1.0,
        QualityDimension.SUMMARY_STRENGTH: 1.0,
        QualityDimension.SUMMARY_DENSITY: 1.0,
        QualityDimension.CLAIM_BOUNDEDNESS: 1.0,
    }

    filler = sorted(phrase for phrase in _WEAK_FILLER_PHRASES if phrase in text.casefold())
    if filler:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.summary.filler.{summary.section_id}",
                message="summary contains generic filler language",
                quality_dimension=QualityDimension.GENERIC_FILLER,
                section_id=summary.section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="fallback_to_bounded_summary",
            )
        )
        scores[QualityDimension.GENERIC_FILLER] = 0.35

    repeated_tokens = _repeated_content_tokens(tokens)
    if repeated_tokens:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.summary.keyword_stuffing.{summary.section_id}",
                message="summary repeats role or keyword terms too often: " + ", ".join(repeated_tokens[:3]),
                quality_dimension=QualityDimension.KEYWORD_STUFFING,
                section_id=summary.section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="trim_repeated_terms",
            )
        )
        scores[QualityDimension.KEYWORD_STUFFING] = 0.55

    if len(tokens) < 7:
        hard_failures.append(
            _signal(
                signal_id=f"quality.phase5.summary.thin.{summary.section_id}",
                message="summary is too thin to read as a professional summary",
                quality_dimension=QualityDimension.SUMMARY_DENSITY,
                section_id=summary.section_id,
                severity=QualitySignalSeverity.ERROR,
                suggested_fallback_action="fallback_to_bounded_summary",
            )
        )
        scores[QualityDimension.SUMMARY_DENSITY] = 0.2

    weak_terms = sorted(term for term in _WEAK_SUMMARY_TERMS if term in text.casefold())
    if weak_terms:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.summary.weak.{summary.section_id}",
                message="summary uses weak or generic professional language",
                quality_dimension=QualityDimension.SUMMARY_STRENGTH,
                section_id=summary.section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="rewrite_summary_with_stronger_supported_themes",
            )
        )
        scores[QualityDimension.SUMMARY_STRENGTH] = 0.45

    broad_terms = sorted(term for term in _BROAD_CLAIM_TERMS if term in text.casefold())
    if broad_terms:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.summary.broad.{summary.section_id}",
                message="summary includes suspiciously broad claim language: " + ", ".join(broad_terms[:3]),
                quality_dimension=QualityDimension.CLAIM_BOUNDEDNESS,
                section_id=summary.section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="prefer_more_bounded_summary_fallback",
            )
        )
        scores[QualityDimension.CLAIM_BOUNDEDNESS] = 0.5

    return GenerationQualitySignals(
        hard_failures=hard_failures,
        warnings=warnings,
        dimension_scores=scores,
        passed=not hard_failures,
        provenance_coverage_score=summary.quality_signals.provenance_coverage_score,
        style_alignment_score=summary.quality_signals.style_alignment_score,
    )


def validate_bullet_outputs_quality(
    section_id: str,
    bullet_outputs: list,
) -> GenerationQualitySignals:
    """Validate rewritten bullet quality for repetition, stuffing, and phrasing."""

    hard_failures: list[QualitySignal] = []
    warnings: list[QualitySignal] = []
    scores = {
        QualityDimension.REPETITION: 1.0,
        QualityDimension.KEYWORD_STUFFING: 1.0,
        QualityDimension.BULLET_NATURALNESS: 1.0,
        QualityDimension.BULLET_LENGTH: 1.0,
    }
    texts = [output.rewritten_text for output in bullet_outputs]
    if _has_duplicate_lines(texts):
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.bullets.repetition.{section_id}",
                message="rewritten bullets repeat the same sentence pattern or content",
                quality_dimension=QualityDimension.REPETITION,
                section_id=section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="prefer_source_or_more_varied_rewrites",
            )
        )
        scores[QualityDimension.REPETITION] = 0.4

    for output in bullet_outputs:
        tokens = _tokenize(output.rewritten_text)
        if len(tokens) > 30:
            hard_failures.append(
                _signal(
                    signal_id=f"quality.phase5.bullets.length.{output.source_bullet_id}",
                    message="rewritten bullet is overlong for resume use",
                    quality_dimension=QualityDimension.BULLET_LENGTH,
                    section_id=output.section_id,
                    source_item_id=output.source_item_id,
                    source_bullet_ids=[output.source_bullet_id],
                    severity=QualitySignalSeverity.ERROR,
                    suggested_fallback_action="fallback_to_source_or_trim",
                )
            )
            scores[QualityDimension.BULLET_LENGTH] = 0.2

        repeated_terms = _repeated_content_tokens(tokens)
        if repeated_terms:
            warnings.append(
                _signal(
                    signal_id=f"quality.phase5.bullets.keyword_stuffing.{output.source_bullet_id}",
                    message="rewritten bullet appears keyword-stuffed: " + ", ".join(repeated_terms[:3]),
                    quality_dimension=QualityDimension.KEYWORD_STUFFING,
                    section_id=output.section_id,
                    source_item_id=output.source_item_id,
                    source_bullet_ids=[output.source_bullet_id],
                    severity=QualitySignalSeverity.WARNING,
                    suggested_fallback_action="trim_repeated_terms",
                )
            )
            scores[QualityDimension.KEYWORD_STUFFING] = min(scores[QualityDimension.KEYWORD_STUFFING], 0.45)

        if any(pattern.search(output.rewritten_text) for pattern in _UNNATURAL_BULLET_PATTERNS):
            warnings.append(
                _signal(
                    signal_id=f"quality.phase5.bullets.naturalness.{output.source_bullet_id}",
                    message="rewritten bullet phrasing looks unnatural or mechanically stitched",
                    quality_dimension=QualityDimension.BULLET_NATURALNESS,
                    section_id=output.section_id,
                    source_item_id=output.source_item_id,
                    source_bullet_ids=[output.source_bullet_id],
                    severity=QualitySignalSeverity.WARNING,
                    suggested_fallback_action="prefer_simpler_rewrite_or_source_text",
                )
            )
            scores[QualityDimension.BULLET_NATURALNESS] = min(scores[QualityDimension.BULLET_NATURALNESS], 0.5)

    return GenerationQualitySignals(
        hard_failures=hard_failures,
        warnings=warnings,
        dimension_scores=scores,
        passed=not hard_failures,
    )


def validate_skill_presentation_quality(skills: SkillPresentationOutput) -> GenerationQualitySignals:
    """Validate compactness and hygiene of rendered skills output."""

    warnings: list[QualitySignal] = []
    hard_failures: list[QualitySignal] = []
    scores = {
        QualityDimension.SKILLS_COMPACTNESS: 1.0,
        QualityDimension.KEYWORD_STUFFING: 1.0,
    }

    total_skills = sum(len(group.skill_names) for group in skills.grouped_skills)
    if total_skills > 12 or len(skills.rendered_skill_lines) > 3:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.skills.compactness.{skills.section_id}",
                message="skills section is overstuffed for a recruiter-readable resume",
                quality_dimension=QualityDimension.SKILLS_COMPACTNESS,
                section_id=skills.section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="reduce_groups_or_trim_skill_list",
            )
        )
        scores[QualityDimension.SKILLS_COMPACTNESS] = 0.35

    duplicate_skills = _duplicate_terms(
        [skill for group in skills.grouped_skills for skill in group.skill_names]
    )
    if duplicate_skills:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.skills.duplicates.{skills.section_id}",
                message="skills section repeats overlapping terms: " + ", ".join(duplicate_skills[:3]),
                quality_dimension=QualityDimension.KEYWORD_STUFFING,
                section_id=skills.section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="deduplicate_skill_rendering",
            )
        )
        scores[QualityDimension.KEYWORD_STUFFING] = 0.5

    return GenerationQualitySignals(
        hard_failures=hard_failures,
        warnings=warnings,
        dimension_scores=scores,
        passed=not hard_failures,
        provenance_coverage_score=skills.quality_signals.provenance_coverage_score,
        style_alignment_score=skills.quality_signals.style_alignment_score,
    )


def validate_section_assembly_quality(assembly: SectionAssemblyOutput) -> GenerationQualitySignals:
    """Validate assembled section balance and final writing hygiene."""

    warnings: list[QualitySignal] = []
    hard_failures: list[QualitySignal] = []
    scores = {
        QualityDimension.SECTION_BALANCE: 1.0,
        QualityDimension.BULLET_LENGTH: 1.0,
        QualityDimension.SUMMARY_DENSITY: 1.0,
        QualityDimension.SKILLS_COMPACTNESS: 1.0,
    }

    exp_bullets = _count_section_bullets(assembly.assembled_experience_sections)
    proj_bullets = _count_section_bullets(assembly.assembled_project_sections)
    if exp_bullets >= 6 and proj_bullets == 0 and assembly.assembled_project_sections:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.assembly.imbalance.{assembly.context_id}",
                message="assembled sections are heavily imbalanced toward experience content",
                quality_dimension=QualityDimension.SECTION_BALANCE,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="rebalance_sections_or_accept_planner_tradeoff",
            )
        )
        scores[QualityDimension.SECTION_BALANCE] = 0.55

    if assembly.assembled_summary is not None and len(_tokenize(assembly.assembled_summary.text)) < 7:
        warnings.append(
            _signal(
                signal_id=f"quality.phase5.assembly.summary_thin.{assembly.assembled_summary.section_id}",
                message="assembled summary is very thin",
                quality_dimension=QualityDimension.SUMMARY_DENSITY,
                section_id=assembly.assembled_summary.section_id,
                severity=QualitySignalSeverity.WARNING,
                suggested_fallback_action="prefer_bounded_summary_fallback",
            )
        )
        scores[QualityDimension.SUMMARY_DENSITY] = 0.4

    if assembly.assembled_skill_section is not None:
        total_skill_names = sum(len(group.skill_names) for group in assembly.assembled_skill_section.grouped_skills)
        if total_skill_names > 12:
            warnings.append(
                _signal(
                    signal_id=f"quality.phase5.assembly.skills_overstuffed.{assembly.assembled_skill_section.section_id}",
                    message="assembled skills section is too dense",
                    quality_dimension=QualityDimension.SKILLS_COMPACTNESS,
                    section_id=assembly.assembled_skill_section.section_id,
                    severity=QualitySignalSeverity.WARNING,
                    suggested_fallback_action="trim_skill_section",
                )
            )
            scores[QualityDimension.SKILLS_COMPACTNESS] = 0.35

    for bullet in _iter_assembled_bullets(assembly):
        if len(_tokenize(bullet.text)) > 30:
            hard_failures.append(
                _signal(
                    signal_id=f"quality.phase5.assembly.bullet_length.{bullet.source_bullet_id}",
                    message="assembled bullet remains overlong",
                    quality_dimension=QualityDimension.BULLET_LENGTH,
                    source_bullet_ids=[bullet.source_bullet_id],
                    severity=QualitySignalSeverity.ERROR,
                    suggested_fallback_action="trim_or_fallback_to_source",
                )
            )
            scores[QualityDimension.BULLET_LENGTH] = 0.2

    return GenerationQualitySignals(
        hard_failures=hard_failures,
        warnings=warnings,
        dimension_scores=scores,
        passed=not hard_failures,
    )


def validate_generation_quality(
    *,
    summary_output: SummaryGenerationOutput | None = None,
    bullet_outputs_by_section: dict[str, list] | None = None,
    skill_output: SkillPresentationOutput | None = None,
    assembly_output: SectionAssemblyOutput | None = None,
) -> GenerationQualitySignals:
    """Run deterministic QA across all bounded Phase 5 generation artifacts."""

    reports: list[GenerationQualitySignals] = []
    if summary_output is not None:
        reports.append(validate_summary_quality(summary_output))
    if bullet_outputs_by_section is not None:
        for section_id, outputs in bullet_outputs_by_section.items():
            reports.append(validate_bullet_outputs_quality(section_id, outputs))
    if skill_output is not None:
        reports.append(validate_skill_presentation_quality(skill_output))
    if assembly_output is not None:
        reports.append(validate_section_assembly_quality(assembly_output))
    return merge_quality_signals(*reports)


def _signal(
    *,
    signal_id: str,
    message: str,
    quality_dimension: QualityDimension,
    severity: QualitySignalSeverity,
    suggested_fallback_action: str,
    section_id: str | None = None,
    source_item_id: str | None = None,
    source_bullet_ids: list[str] | None = None,
) -> QualitySignal:
    return QualitySignal(
        signal_id=signal_id,
        severity=severity,
        message=message,
        quality_dimension=quality_dimension,
        suggested_fallback_action=suggested_fallback_action,
        section_id=section_id,
        source_item_id=source_item_id,
        source_bullet_ids=list(source_bullet_ids or []),
    )


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.casefold())


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _repeated_content_tokens(tokens: list[str]) -> list[str]:
    counts = Counter(token for token in tokens if len(token) > 3)
    return sorted(token for token, count in counts.items() if count >= 3)


def _duplicate_terms(values: list[str]) -> list[str]:
    counts = Counter(value.casefold() for value in values)
    return sorted(term for term, count in counts.items() if count > 1)


def _has_duplicate_lines(lines: list[str]) -> bool:
    normalized = [_normalize_line(line) for line in lines]
    return len(normalized) != len(set(normalized))


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _count_section_bullets(sections: list[AssembledExperienceSection] | list[AssembledProjectSection]) -> int:
    return sum(len(item.bullets) for section in sections for item in section.items)


def _iter_assembled_bullets(assembly: SectionAssemblyOutput):
    for section in assembly.assembled_experience_sections:
        for item in section.items:
            yield from item.bullets
    for section in assembly.assembled_project_sections:
        for item in section.items:
            yield from item.bullets
