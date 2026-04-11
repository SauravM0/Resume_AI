"""Abstract contracts for the Phase 7 evaluation foundation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.app.evaluation.artifact_models import (
    ArtifactManifest,
    ArtifactManifestEntry,
)
from backend.app.evaluation.case_models import (
    EvaluationActualOutputs,
    EvaluationCaseDefinition,
)
from backend.app.evaluation.enums import EvaluationPackType
from backend.app.evaluation.report_models import RunSummary, ScoringSummary
from backend.app.evaluation.runtime_models import EvaluationRunManifest
from backend.app.orchestration.enums import StageName
from resume_optimizer.models import StableId


class ArtifactStore(Protocol):
    """Persist evaluation-stage artifacts and expose a run manifest."""

    def persist_stage_artifact(
        self,
        *,
        run_id: StableId,
        case_id: StableId,
        stage_name: StageName,
        artifact_name: str,
        payload: bytes | str | dict[str, object] | list[object],
        content_type: str,
        schema_version: str = "phase7.eval.artifact.v1",
    ) -> ArtifactManifestEntry:
        """Persist one stage artifact and return the manifest entry."""

    def build_manifest(self, *, run_id: StableId, case_id: StableId) -> ArtifactManifest:
        """Return the artifact manifest for a completed evaluation run."""

    def write_manifest(self, manifest: ArtifactManifest) -> Path:
        """Write the machine-readable run manifest document."""

    def write_summary(self, run_manifest: EvaluationRunManifest, artifact_manifest: ArtifactManifest) -> Path:
        """Write the human-readable markdown summary for one run."""


class RealPipelineRunner(Protocol):
    """Run one evaluation case through the real orchestration stack."""

    def run_case(
        self,
        case: EvaluationCaseDefinition,
        *,
        artifact_store: ArtifactStore,
    ) -> EvaluationActualOutputs:
        """Execute the actual pipeline implementation for one case."""


class EvaluationCaseLoader(Protocol):
    """Load evaluation case definitions from repository fixtures."""

    def load_case(self, path: Path) -> EvaluationCaseDefinition:
        """Load one evaluation case definition from disk."""

    def load_pack(
        self,
        pack_type: EvaluationPackType,
        *,
        fixture_root: Path | None = None,
    ) -> list[EvaluationCaseDefinition]:
        """Load every case in one evaluation pack."""


class EvaluationScorer(Protocol):
    """Score observed outputs against a case definition."""

    def score_case(
        self,
        case: EvaluationCaseDefinition,
        actual_outputs: EvaluationActualOutputs,
        artifact_manifest: ArtifactManifest,
    ) -> ScoringSummary:
        """Return scorer output for one completed case run."""


class EvaluationReportWriter(Protocol):
    """Write case-level evaluation reports to durable storage."""

    def write_case_report(
        self,
        *,
        case: EvaluationCaseDefinition,
        run_summary: RunSummary,
        scoring_summary: ScoringSummary,
        artifact_manifest: ArtifactManifest,
        output_root: Path,
    ) -> Path:
        """Write a durable report artifact and return its path."""
