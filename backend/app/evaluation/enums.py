"""Stable enum values for the Phase 7 evaluation layer."""

from __future__ import annotations

from enum import StrEnum


class EvaluationPackType(StrEnum):
    """Supported regression pack groupings for evaluation fixtures."""

    JD_PARSE = "jd_parse"
    SELECTION = "selection"
    END_TO_END = "end_to_end"
    RED_TEAM = "red_team"


class EvaluationRunStatus(StrEnum):
    """Lifecycle state for one evaluation case run."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class ScoringOutcome(StrEnum):
    """Top-level result emitted by a scorer."""

    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"
