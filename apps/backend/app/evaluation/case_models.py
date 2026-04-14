"""Typed evaluation case definitions and observed outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from backend.app.evaluation.enums import EvaluationPackType
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel


class EvaluationCaseMetadata(StrictModel):
    """Stable metadata for one regression or red-team evaluation case."""

    case_id: StableId
    pack_type: EvaluationPackType
    scenario: NonEmptyStr
    description: NonEmptyStr
    tags: list[NonEmptyStr] = Field(default_factory=list)
    source_fixture: NonEmptyStr | None = None
    created_at: datetime | None = None


class EvaluationStageExpectation(StrictModel):
    """Expected outcome for one stage inside an evaluation case."""

    stage_name: StageName
    expected_status: StageStatus = StageStatus.SUCCEEDED
    required_artifact_kinds: list[ArtifactKind] = Field(default_factory=list)
    expected_warning_count: int | None = Field(default=None, ge=0)


class EvaluationExpectedOutputs(StrictModel):
    """Expected case-level outputs used by scorers and reports."""

    expected_pipeline_status: PipelineStatus = PipelineStatus.SUCCEEDED
    expected_stage_sequence: list[StageName] = Field(default_factory=list)
    stage_expectations: list[EvaluationStageExpectation] = Field(default_factory=list)
    required_artifact_kinds: list[ArtifactKind] = Field(default_factory=list)
    expected_output_snapshot: dict[str, Any] = Field(default_factory=dict)
    reviewer_guidance: list[NonEmptyStr] = Field(default_factory=list)
    bad_behavior_to_catch: NonEmptyStr | None = None
    acceptable_fallback_behavior: NonEmptyStr | None = None


class EvaluationCaseDefinition(StrictModel):
    """Full fixture payload loaded by the evaluation layer."""

    metadata: EvaluationCaseMetadata
    input_payload: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: EvaluationExpectedOutputs


class EvaluationStageActualOutput(StrictModel):
    """Observed result for one stage during a real evaluation run."""

    stage_name: StageName
    status: StageStatus
    attempt_count: int = Field(default=1, ge=1)
    artifact_refs: list[PipelineArtifactRef] = Field(default_factory=list)
    warning_messages: list[NonEmptyStr] = Field(default_factory=list)
    output_snapshot: dict[str, Any] = Field(default_factory=dict)


class EvaluationActualOutputs(StrictModel):
    """Observed outputs captured from a real pipeline execution."""

    run_id: StableId
    case_id: StableId
    pipeline_status: PipelineStatus
    stage_outputs: list[EvaluationStageActualOutput] = Field(default_factory=list)
    final_artifact_refs: list[PipelineArtifactRef] = Field(default_factory=list)
    final_output_snapshot: dict[str, Any] = Field(default_factory=dict)
