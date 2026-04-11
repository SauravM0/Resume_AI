"""Canonicalization helpers for deterministic Phase 1 extraction."""

from __future__ import annotations

import re

from .normalization import (
    infer_action_verbs_from_text,
    infer_cloud_services_from_text,
    infer_delivery_scope_phrases_from_text,
    infer_domains_from_text,
    infer_frameworks_from_text,
    infer_leadership_phrases_from_text,
    infer_programming_languages_from_text,
    infer_tool_platforms_from_text,
)
from .normalizers import normalize_tool_name

_WHITESPACE_RE = re.compile(r"\s+")
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•\u2022]+|\d+[.)])\s*")
_HEADING_SUFFIX_RE = re.compile(r"\s*[:\-]\s*$")
_STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "have",
    "into",
    "job",
    "our",
    "that",
    "the",
    "this",
    "will",
    "with",
    "you",
    "your",
}


def normalize_job_line(value: str) -> str:
    """Normalize one raw JD line while preserving semantic content."""

    cleaned = value.replace("\r", " ").replace("\t", " ")
    cleaned = _BULLET_PREFIX_RE.sub("", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def canonicalize_heading(value: str) -> str:
    """Normalize a heading line for deterministic section matching."""

    return _HEADING_SUFFIX_RE.sub("", normalize_job_line(value)).casefold()


def canonicalize_requirement_text(value: str) -> str:
    """Normalize requirement lines for deduplication and explainability."""

    return normalize_job_line(value)


def canonicalize_tool_platform(value: str) -> str:
    """Return canonical tool/platform form using existing source-data helpers."""

    return normalize_tool_name(value)


def canonicalize_action_verb(value: str) -> str:
    """Return a canonical action verb using the existing action taxonomy."""

    terms = infer_action_verbs_from_text([value])
    return terms[0].canonical if terms else normalize_job_line(value).casefold()


def canonicalize_work_model_signal(value: str) -> str:
    """Normalize common work-model phrasing to stable downstream labels."""

    lowered = normalize_job_line(value).casefold()
    if "hybrid" in lowered:
        return "hybrid"
    if "remote" in lowered or "work from home" in lowered:
        return "remote"
    if "on-site" in lowered or "onsite" in lowered or "in office" in lowered:
        return "onsite"
    return lowered


def extract_explicit_domain_terms(value: str) -> list[str]:
    """Infer canonical domain terms from explicit JD text."""

    return [term.canonical for term in infer_domains_from_text([value])]


def extract_leadership_terms(value: str) -> list[str]:
    """Infer canonical leadership terms from explicit JD text."""

    return [term.canonical for term in infer_leadership_phrases_from_text([value])]


def extract_scope_terms(value: str) -> list[str]:
    """Infer canonical delivery-scope phrases from explicit JD text."""

    return [term.canonical for term in infer_delivery_scope_phrases_from_text([value])]


def extract_tool_platform_terms(value: str) -> list[str]:
    """Infer canonical tool/platform and closely related technical terms."""

    combined = [
        *infer_tool_platforms_from_text([value]),
        *infer_cloud_services_from_text([value]),
        *infer_frameworks_from_text([value]),
        *infer_programming_languages_from_text([value]),
    ]
    result: list[str] = []
    seen: set[str] = set()
    for term in combined:
        key = term.canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(term.canonical)
    return result


def keyword_candidate_tokens(value: str) -> list[str]:
    """Return normalized keyword candidates suitable for repetition counting."""

    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{2,}", value)
    result: list[str] = []
    for token in tokens:
        lowered = token.casefold()
        if lowered in _STOPWORDS:
            continue
        result.append(lowered)
    return result
