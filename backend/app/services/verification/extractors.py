"""Deterministic text extractors used by factual verification validators."""

from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.services.verification.normalization import (
    normalize_compact,
    normalize_phrase,
    phrase_in_text,
)
from backend.app.services.verification.rules import DeterministicRuleSet, EscalationRule

_CURRENCY_PATTERN = r"\$[\d,]+(?:\.\d+)?\s*(?:[KMBkmb])?"
_PERCENT_PATTERN = r"\b\d+(?:\.\d+)?\s?%"
_DURATION_PATTERN = r"\b\d+(?:\.\d+)?\s?(?:ms|milliseconds?|seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?|yrs?)\b"
_SCALE_PATTERN = r"\b\d+(?:\.\d+)?\s?(?:x|X)\b"
_COUNT_PATTERN = r"\b\d[\d,]*(?:\.\d+)?\s?(?:users?|customers?|requests?|services?|teams?|engineers?|people|APIs?|features?|projects?|systems?|workflows?)\b"
_YEAR_PATTERN = r"\b(?:19|20)\d{2}\b"
_BARE_NUMBER_PATTERN = r"\b\d[\d,]*(?:\.\d+)?\b"
_NUMERIC_PATTERN = re.compile(
    "|".join(
        [
            _CURRENCY_PATTERN,
            _PERCENT_PATTERN,
            _DURATION_PATTERN,
            _SCALE_PATTERN,
            _COUNT_PATTERN,
            _YEAR_PATTERN,
        ]
    ),
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ExtractedToken:
    """Extracted text token with character span and normalized comparison key."""

    text: str
    normalized: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class EscalationMatch:
    """Detected escalation from weaker source language to stronger generated language."""

    rule: EscalationRule
    generated_term: str
    source_term: str | None


def normalize_token(value: str) -> str:
    """Normalize extracted values for deterministic equality comparisons."""

    return normalize_compact(value)


def extract_numeric_tokens(text: str) -> list[ExtractedToken]:
    """Extract numeric factual claims from generated or source text.

    The extractor intentionally focuses on resume-risky numeric facts:
    percentages, currency, durations/timing, scale multipliers, counts with
    units, and years. Bare numbers are included only if they were not already
    part of a richer numeric token.
    """

    tokens = [
        ExtractedToken(
            text=match.group(0),
            normalized=normalize_token(match.group(0)),
            start=match.start(),
            end=match.end(),
        )
        for match in _NUMERIC_PATTERN.finditer(text)
    ]
    occupied = {(token.start, token.end) for token in tokens}
    spans = [(token.start, token.end) for token in tokens]
    for match in re.finditer(_BARE_NUMBER_PATTERN, text):
        if any(start <= match.start() and match.end() <= end for start, end in spans):
            continue
        span = (match.start(), match.end())
        if span in occupied:
            continue
        tokens.append(
            ExtractedToken(
                text=match.group(0),
                normalized=normalize_token(match.group(0)),
                start=match.start(),
                end=match.end(),
            )
        )
    return sorted(tokens, key=lambda token: token.start)


def extract_named_technologies(text: str, rules: DeterministicRuleSet) -> list[ExtractedToken]:
    """Extract configured technology names using case-insensitive word boundaries."""

    tokens: list[ExtractedToken] = []
    for technology in rules.technologies:
        pattern = re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(technology)}(?![A-Za-z0-9+#])", re.IGNORECASE)
        for match in pattern.finditer(text):
            tokens.append(
                ExtractedToken(
                    text=match.group(0),
                    normalized=technology.lower(),
                    start=match.start(),
                    end=match.end(),
                )
            )
    return sorted(tokens, key=lambda token: (token.start, token.normalized))


def extract_configured_keywords(text: str, keywords: list[str]) -> list[ExtractedToken]:
    """Extract caller-provided job keywords from generated text."""

    return extract_configured_phrases(text, keywords)


def extract_configured_phrases(text: str, phrases: list[str] | tuple[str, ...]) -> list[ExtractedToken]:
    """Extract caller-provided phrases from generated text using normalized boundaries."""

    tokens: list[ExtractedToken] = []
    normalized_text = normalize_phrase(text)
    for phrase in sorted(set(phrases), key=len, reverse=True):
        if not phrase.strip():
            continue
        normalized_phrase = normalize_phrase(phrase)
        pattern = re.compile(
            rf"(?<![a-z0-9+#]){re.escape(normalized_phrase)}(?![a-z0-9+#])",
            re.IGNORECASE,
        )
        for match in pattern.finditer(normalized_text):
            tokens.append(
                ExtractedToken(
                    text=phrase,
                    normalized=normalized_phrase,
                    start=match.start(),
                    end=match.end(),
                )
            )
    return sorted(tokens, key=lambda token: (token.start, token.normalized))


def detect_escalation_phrases(
    *,
    generated_text: str,
    source_text: str,
    rules: DeterministicRuleSet,
) -> list[EscalationMatch]:
    """Detect configured source-to-generated role inflation patterns."""

    generated_lower = generated_text.lower()
    source_lower = source_text.lower()
    matches: list[EscalationMatch] = []
    for rule in rules.escalation_rules:
        generated_term = next(
            (term for term in rule.escalated_terms if _contains_phrase(generated_lower, term)),
            None,
        )
        if generated_term is None or _contains_phrase(source_lower, generated_term):
            continue
        source_term = next(
            (term for term in rule.source_terms if _contains_phrase(source_lower, term)),
            None,
        )
        if source_term is not None:
            matches.append(
                EscalationMatch(
                    rule=rule,
                    generated_term=generated_term,
                    source_term=source_term,
                )
            )
    return matches


def extract_unsupported_leadership_terms(
    *,
    generated_text: str,
    source_text: str,
    rules: DeterministicRuleSet,
) -> list[str]:
    """Return leadership/seniority terms present in generated text but absent from sources."""

    generated_lower = generated_text.lower()
    source_lower = source_text.lower()
    return [
        term
        for term in rules.leadership_terms
        if _contains_phrase(generated_lower, term) and not _contains_phrase(source_lower, term)
    ]


def _contains_phrase(text: str, phrase: str) -> bool:
    """Check phrase containment with alphanumeric boundaries."""

    return phrase_in_text(text, phrase)
