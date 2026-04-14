"""Normalization and grounding helpers for Phase 1 merge logic."""

from __future__ import annotations

import json
from typing import Any

from .phase1_deterministic_models import DeterministicJobDescriptionExtraction


def fold_key(value: str) -> str:
    """Normalize comparable text for deterministic merge decisions."""

    return " ".join(value.casefold().split())


def clamp_score(value: Any) -> float:
    """Clamp arbitrary numeric input into the shared confidence-score range."""

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.5
    return max(0.0, min(parsed, 1.0))


def coerce_string_list(value: Any) -> list[str]:
    """Normalize free-form model values into a clean string list."""

    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    text = str(value).strip()
    return [text] if text else []


def stable_unique(values: list[Any]) -> list[Any]:
    """Deduplicate values while preserving first-seen order."""

    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            marker = json.dumps(value, sort_keys=True)
        else:
            marker = fold_key(str(value))
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def repeated_signal_count(
    value: str,
    deterministic: DeterministicJobDescriptionExtraction,
) -> int:
    """Count how often a merged value is echoed across deterministic signals."""

    folded_value = fold_key(value)
    if not folded_value:
        return 0

    line_hits = sum(
        1 for line in deterministic.normalized_lines if folded_value in fold_key(line)
    )
    keyword_hits = sum(
        item.count
        for item in deterministic.repeated_keyword_findings
        if folded_value == fold_key(item.keyword)
    )
    comparable_hits = sum(
        1
        for candidate in _comparable_values(deterministic)
        if folded_value == fold_key(candidate)
    )
    return line_hits + keyword_hits + comparable_hits


def is_grounded_explicit_value(
    value: str,
    deterministic: DeterministicJobDescriptionExtraction,
) -> bool:
    """Return whether a value is explicitly anchored in deterministic evidence."""

    folded_value = fold_key(value)
    if not folded_value:
        return False
    raw_text = fold_key(deterministic.raw_job_text)
    if folded_value in raw_text:
        return True
    value_tokens = set(folded_value.split())
    if value_tokens and value_tokens.issubset(set(raw_text.split())):
        return True
    return any(folded_value == fold_key(candidate) for candidate in _comparable_values(deterministic))


def filter_grounded_explicit_values(
    values: list[str],
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[str]:
    """Keep only values explicitly grounded in the JD text or deterministic artifact."""

    return [value for value in values if is_grounded_explicit_value(value, deterministic)]


def filter_grounded_behavior_values(
    values: list[str],
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[str]:
    """Keep behavioral signals that are text-grounded or supported by leadership findings."""

    grounded: list[str] = []
    for value in values:
        if is_grounded_explicit_value(value, deterministic):
            grounded.append(value)
            continue
        if any(
            fold_key(value) in fold_key(item.canonical_value)
            for item in deterministic.leadership_findings
        ):
            grounded.append(value)
    return stable_unique(grounded)


def comparable_scalar_match(left: str | None, right: str | None) -> bool:
    """Compare scalar strings using folded equality."""

    if not left or not right:
        return False
    return fold_key(left) == fold_key(right)


def _comparable_values(
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[str]:
    return [
        *(item.canonical_value for item in deterministic.title_candidates),
        *(item.canonical_value for item in deterministic.company_name_candidates),
        *(item.canonical_value for item in deterministic.tool_platform_findings),
        *(item.canonical_value for item in deterministic.domain_findings),
        *(item.canonical_value for item in deterministic.action_verb_findings),
        *(item.keyword for item in deterministic.repeated_keyword_findings),
        *(item.canonical_value for item in deterministic.work_model_findings),
        *(item.canonical_value for item in deterministic.leadership_findings),
        *(item.canonical_value for item in deterministic.scope_indicator_findings),
        *(item.canonical_value for item in deterministic.education_requirement_findings),
        *(item.canonical_text for item in deterministic.requirement_markers),
    ]
