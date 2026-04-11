"""Phase 6 orchestration contracts.

This package defines typed contracts only. Runtime orchestration, persistence,
LLM calls, rendering, and database writes belong in service/repository layers.
"""

from backend.app.orchestration.contracts import PIPELINE_STAGE_CONTRACTS, StageContract
from backend.app.orchestration.enums import (
    ArtifactKind,
    OrchestrationFailureType,
    PipelineStatus,
    StageName,
    StageStatus,
)
from backend.app.orchestration.pipeline_models import (
    PipelineInput,
    PipelineResult,
    StageResult,
)

__all__ = [
    "ArtifactKind",
    "OrchestrationFailureType",
    "PIPELINE_STAGE_CONTRACTS",
    "PipelineInput",
    "PipelineResult",
    "PipelineStatus",
    "StageContract",
    "StageName",
    "StageResult",
    "StageStatus",
]
