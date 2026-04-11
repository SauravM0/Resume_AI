"""Deterministic normalization helpers for Phase 1 job analysis."""

from __future__ import annotations

import re

from .job_models import (
    NormalizedJobAnalysis,
    NormalizedSkillRequirement,
    ParsedJobAnalysisResponse,
    SkillPriority,
)
from .normalization import normalize_action_verbs as normalize_action_verb_terms
from .normalization import normalize_skill_list
from .normalizers import (
    _fold_key,
    _normalize_text,
    _normalize_unique,
    normalize_domain_tag,
    normalize_role_type,
    normalize_seniority,
    normalize_skill_name,
)

YEARS_EXPERIENCE_PATTERN = re.compile(
    r"\b(\d{1,2})\+?\s+years?(?:\s+of)?(?:\s+[a-zA-Z][a-zA-Z-]*){0,4}\s+experience\b",
    flags=re.IGNORECASE,
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
MUST_HAVE_MARKERS: tuple[str, ...] = (
    "must have",
    "required",
    "requirements",
    "minimum qualifications",
    "you will need",
)
NICE_TO_HAVE_MARKERS: tuple[str, ...] = (
    "nice to have",
    "preferred",
    "preferred qualifications",
    "bonus",
    "plus",
)

def normalize_job_analysis(
    raw_analysis: ParsedJobAnalysisResponse,
    raw_job_description_text: str,
) -> NormalizedJobAnalysis:
    """Return the canonical Phase 1 job analysis object."""

    normalized_technical_skills = _normalize_unique(
        raw_analysis.technical_skills,
        normalize_skill_name,
    )
    detected_technical_skills = detect_technical_keywords(raw_job_description_text)
    merged_technical_skills = _merge_preserving_order(
        normalized_technical_skills,
        detected_technical_skills,
    )

    normalized_must_haves = _normalize_unique(
        raw_analysis.must_have_requirements,
        _normalize_text,
    )
    normalized_nice_to_haves = _normalize_unique(
        raw_analysis.nice_to_have_requirements,
        _normalize_text,
    )

    deterministic_must_haves, deterministic_nice_to_haves = extract_requirement_markers(
        raw_job_description_text
    )

    merged_must_haves = _merge_preserving_order(
        normalized_must_haves,
        deterministic_must_haves,
    )
    merged_nice_to_haves = _merge_preserving_order(
        normalized_nice_to_haves,
        deterministic_nice_to_haves,
    )

    prioritized_skills = [
        NormalizedSkillRequirement(
            skill_name=skill,
            priority=(
                SkillPriority.CORE
                if _skill_is_required(skill, merged_must_haves)
                else SkillPriority.NICE_TO_HAVE
                if _skill_is_preferred(skill, merged_nice_to_haves)
                else SkillPriority.IMPORTANT
            ),
        )
        for skill in merged_technical_skills
    ]

    return NormalizedJobAnalysis(
        role_type=normalize_role_type(raw_analysis.role_type),
        seniority_level=normalize_seniority(raw_analysis.seniority_level),
        industry_domain=_normalize_optional_domain(raw_analysis.industry_domain),
        technical_skills=merged_technical_skills,
        soft_skills=_normalize_unique(raw_analysis.soft_skills, _normalize_text),
        key_action_verbs=_normalize_action_verbs(raw_analysis.key_action_verbs),
        must_have_requirements=merged_must_haves,
        nice_to_have_requirements=merged_nice_to_haves,
        company_culture_signals=_normalize_unique(
            raw_analysis.company_culture_signals,
            _normalize_text,
        ),
        years_experience_required=extract_years_experience_requirement(
            raw_job_description_text
        ),
        prioritized_skills=prioritized_skills,
    )


def extract_years_experience_requirement(raw_job_description_text: str) -> int | None:
    """Extract the minimum explicit years-of-experience requirement when obvious."""

    matches = YEARS_EXPERIENCE_PATTERN.findall(raw_job_description_text)
    if not matches:
        return None
    return min(int(value) for value in matches)


def extract_requirement_markers(raw_job_description_text: str) -> tuple[list[str], list[str]]:
    """Extract obvious must-have and preferred requirement lines conservatively."""

    must_haves: list[str] = []
    nice_to_haves: list[str] = []

    for chunk in SENTENCE_SPLIT_PATTERN.split(raw_job_description_text):
        cleaned = _normalize_text(chunk)
        if not cleaned:
            continue

        lowered = cleaned.casefold()
        if any(marker in lowered for marker in MUST_HAVE_MARKERS):
            must_haves.append(cleaned)
            continue

        if any(marker in lowered for marker in NICE_TO_HAVE_MARKERS):
            nice_to_haves.append(cleaned)

    return (
        _normalize_unique(must_haves, _normalize_text),
        _normalize_unique(nice_to_haves, _normalize_text),
    )


def detect_technical_keywords(raw_job_description_text: str) -> list[str]:
    """Detect a small set of obvious technical keywords directly from the JD."""

    candidates = re.findall(r"[A-Za-z0-9.+#/-]+", raw_job_description_text)
    return [term.canonical for term in normalize_skill_list(candidates)]


def _normalize_action_verbs(values: list[str]) -> list[str]:
    return [term.canonical for term in normalize_action_verb_terms(values)]


def _merge_preserving_order(primary: list[str], secondary: list[str]) -> list[str]:
    merged = list(primary)
    seen = {_fold_key(value) for value in primary}

    for value in secondary:
        key = _fold_key(value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)

    return merged


def _normalize_optional_domain(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = normalize_domain_tag(value)
    return cleaned or None


def _skill_is_required(
    skill_name: str,
    must_have_requirements: list[str],
) -> bool:
    skill_key = _fold_key(skill_name)
    return any(skill_key in _fold_key(requirement) for requirement in must_have_requirements)


def _skill_is_preferred(
    skill_name: str,
    nice_to_have_requirements: list[str],
) -> bool:
    skill_key = _fold_key(skill_name)
    return any(
        skill_key in _fold_key(requirement) for requirement in nice_to_have_requirements
    )
