"""Typed scoring and summary models for Phase 7 evaluation output."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from backend.app.evaluation.enums import EvaluationPackType, EvaluationRunStatus, ScoringOutcome
from backend.app.orchestration.enums import PipelineStatus
from resume_optimizer.models import NonEmptyStr, ScoreValue, StableId, StrictModel


class ScoringMetric(StrictModel):
    """One named metric emitted by a scorer."""

    metric_name: NonEmptyStr
    score: ScoreValue
    passed: bool
    details: NonEmptyStr | None = None


class ReviewerSignal(StrictModel):
    """Reviewer-visible quality or risk signal emitted alongside structured metrics."""

    signal_name: NonEmptyStr
    triggered: bool
    severity: NonEmptyStr = "info"
    details: NonEmptyStr | None = None


class ScoringSummary(StrictModel):
    """Scorer output for one case run."""

    run_id: StableId
    case_id: StableId
    scorer_name: NonEmptyStr
    outcome: ScoringOutcome
    overall_score: ScoreValue
    metrics: list[ScoringMetric] = Field(default_factory=list)
    findings: list[NonEmptyStr] = Field(default_factory=list)
    reviewer_signals: list[ReviewerSignal] = Field(default_factory=list)
    reviewer_comments: list[NonEmptyStr] = Field(default_factory=list)
    artifact_paths: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)


class RunSummary(StrictModel):
    """Case-level execution summary suitable for CI logs and reports."""

    run_id: StableId
    case_id: StableId
    pack_type: EvaluationPackType
    status: EvaluationRunStatus
    pipeline_status: PipelineStatus | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    artifact_manifest_path: NonEmptyStr | None = None
    summary_path: NonEmptyStr | None = None
    report_path: NonEmptyStr | None = None
