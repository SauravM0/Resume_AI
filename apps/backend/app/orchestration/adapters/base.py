"""Base adapter contracts for Phase 6 stage integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from backend.app.orchestration.enums import StageName
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.orchestration.types import PipelineArtifactRef

StageInputT = TypeVar("StageInputT")
StageOutputT = TypeVar("StageOutputT")


@dataclass(slots=True)
class StageExecutionContext:
    """Context available to all stage adapters without coupling to route code."""

    run_id: str
    stage_name: StageName
    recorder: PipelineRunRecorder | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class StageAdapter(Protocol, Generic[StageInputT, StageOutputT]):
    """Standard interface implemented by all Phase 1-5 stage adapters."""

    stage_name: StageName

    def execute(self, stage_input: StageInputT, context: StageExecutionContext) -> StageOutputT:
        """Execute the wrapped stage and return normalized stage output."""

    def extract_artifacts(
        self,
        stage_output: StageOutputT,
        context: StageExecutionContext,
    ) -> list[PipelineArtifactRef]:
        """Return stage artifacts when the adapter can expose them."""
