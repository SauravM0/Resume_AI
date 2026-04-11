"""Adapter for Phase 2 evidence ranking and selection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.pipeline_models import RankSelectEvidenceInput, RankSelectEvidenceOutput
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.ranking_service import Phase2RankingArtifacts, build_phase2_ranking_artifacts


class RankerAdapter:
    """Wrap deterministic Phase 2 ranking service."""

    stage_name = StageName.RANK_SELECT_EVIDENCE

    def __init__(
        self,
        *,
        ranking_func: Callable[..., Phase2RankingArtifacts] = build_phase2_ranking_artifacts,
    ) -> None:
        self._ranking_func = ranking_func

    def execute(
        self,
        stage_input: RankSelectEvidenceInput,
        context: StageExecutionContext,
    ) -> RankSelectEvidenceOutput:
        """Rank source profile evidence against normalized job analysis."""

        try:
            artifacts = self._ranking_func(
                stage_input.job_analysis,
                stage_input.source_profile,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"ranking and selection failed: {exc}",
                failure_type=OrchestrationFailureType.RANKING_SELECTION,
                stage_name=self.stage_name,
            ) from exc
        return RankSelectEvidenceOutput(
            ranking_response=artifacts.ranking_response,
            selection_result=artifacts.selection_result,
        )

    def extract_artifacts(
        self,
        stage_output: RankSelectEvidenceOutput,
        context: StageExecutionContext,
    ) -> list[PipelineArtifactRef]:
        return []
