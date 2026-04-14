"""Runtime models for real evaluation execution and manifests."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from backend.app.evaluation.enums import EvaluationRunStatus
from backend.app.orchestration.enums import PipelineStatus, StageName, StageStatus
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel


class EvaluationExecutionMode(str):
    """Deprecated compatibility alias for older stringly-typed callers."""


class EvaluationDependencyStatus(StrictModel):
    """One runtime dependency check for a real evaluation run."""

    dependency_name: NonEmptyStr
    available: bool
    message: NonEmptyStr


class EvaluationRunnerConfig(StrictModel):
    """Explicit execution flags for the real evaluation harness."""

    use_live_llm: bool = True
    enable_render: bool = True
    persist_artifacts: bool = True
    fail_fast: bool = True
    stop_after: NonEmptyStr = "full"


class EvaluationStageRunRecord(StrictModel):
    """Runner-owned stage record used in run manifests and shell output."""

    stage_name: StageName
    status: StageStatus
    executed: bool
    skipped: bool = False
    artifact_count: int = Field(default=0, ge=0)
    message: NonEmptyStr


class EvaluationRunManifest(StrictModel):
    """Structured manifest for one real or dry-run evaluation execution."""

    run_id: StableId
    case_id: StableId
    execution_mode: NonEmptyStr
    run_status: EvaluationRunStatus
    pipeline_status: PipelineStatus | None = None
    config: EvaluationRunnerConfig
    started_at: datetime
    finished_at: datetime | None = None
    stage_records: list[EvaluationStageRunRecord] = Field(default_factory=list)
    dependency_checks: list[EvaluationDependencyStatus] = Field(default_factory=list)
    missing_dependencies: list[EvaluationDependencyStatus] = Field(default_factory=list)
    final_message: NonEmptyStr
    artifact_manifest_path: NonEmptyStr | None = None
    summary_path: NonEmptyStr | None = None
    report_path: NonEmptyStr | None = None
