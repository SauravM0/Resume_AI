"""Shared normalization helpers for deterministic verification checks."""

from __future__ import annotations

import re

_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9+#]+")


def normalize_text(value: str) -> str:
    """Normalize free text into a lowercase single-space form."""

    return " ".join(value.casefold().split())


def normalize_phrase(value: str) -> str:
    """Normalize phrases for loose token comparison."""

    normalized = _NON_ALNUM_PATTERN.sub(" ", value.casefold())
    return " ".join(normalized.split())


def normalize_compact(value: str) -> str:
    """Normalize values for strict compact equality checks."""

    return re.sub(r"\s+", "", value.casefold().replace(",", ""))


def phrase_in_text(text: str, phrase: str) -> bool:
    """Return true when a normalized phrase appears with token boundaries."""

    normalized_text = normalize_phrase(text)
    normalized_phrase = normalize_phrase(phrase)
    if not normalized_phrase:
        return False
    return re.search(
        rf"(?<![a-z0-9+#]){re.escape(normalized_phrase)}(?![a-z0-9+#])",
        normalized_text,
    ) is not None
