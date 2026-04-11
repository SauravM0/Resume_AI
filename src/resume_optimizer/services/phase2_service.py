"""Phase 2 orchestration service for backend integration and optional persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import logging
from typing import Protocol

from ..config import DEFAULT_SETTINGS, Settings
from ..evidence_models import CandidateEvidenceCoverageMap, CandidateEvidenceGraph
from ..job_models import NormalizedJobAnalysis
from ..loaders import load_and_normalize_master_profile
from ..models import MasterProfile
from ..phase2_artifacts import phase2_artifact_diagnostics_payload
from ..phase2_models import Phase2SelectionResult, Phase2SelectionResultRecord, Phase2Status
from ..ranking_models import RankingResponse
from ..ranking_service import Phase2RankingArtifacts, build_phase2_ranking_artifacts

logger = logging.getLogger(__name__)


class Phase2PersistenceRepository(Protocol):
    """Persistence protocol for writing Phase 2 artifacts to a backing store later."""

    def save_run(self, record: Phase2SelectionResultRecord) -> str | None:
        """Persist one Phase 2 run and return the stored run id when available."""


class NoOpPhase2PersistenceRepository:
    """Safe default repository used when database persistence is disabled."""

    def save_run(self, record: Phase2SelectionResultRecord) -> str | None:
        return None


@dataclass(frozen=True, slots=True)
class Phase2ServiceResult:
    """Service result containing public response plus internal Phase 2 artifacts."""

    ranking_response: RankingResponse
    phase2_result: Phase2SelectionResult
    evidence_graph: CandidateEvidenceGraph
    coverage_map: CandidateEvidenceCoverageMap
    persistence_attempted: bool = False
    persistence_succeeded: bool = False
    persisted_run_id: str | None = None


@dataclass(slots=True)
class Phase2Service:
    """Orchestrate Phase 2 execution, optional persistence, and safe logging."""

    settings: Settings = field(default_factory=lambda: DEFAULT_SETTINGS)
    persistence_repository: Phase2PersistenceRepository = field(
        default_factory=NoOpPhase2PersistenceRepository
    )

    def run_for_default_profile(
        self,
        job_analysis: NormalizedJobAnalysis,
        *,
        today: date | None = None,
    ) -> Phase2ServiceResult:
        """Load the configured default profile and execute the Phase 2 pipeline."""

        source_profile = load_and_normalize_master_profile(self.settings.default_profile_path)
        return self.run(job_analysis, source_profile=source_profile, today=today)

    def run(
        self,
        job_analysis: NormalizedJobAnalysis,
        *,
        source_profile: MasterProfile,
        today: date | None = None,
    ) -> Phase2ServiceResult:
        """Run the integrated Phase 2 pipeline and optionally persist the result."""

        artifacts = build_phase2_ranking_artifacts(
            job_analysis,
            source_profile,
            today=today,
        )
        phase2_result = artifacts.selection_result
        persisted_run_id: str | None = None
        persistence_attempted = self.settings.phase2_persistence_enabled
        persistence_succeeded = False

        if persistence_attempted:
            persistence_record = Phase2SelectionResultRecord(
                profile_id=source_profile.id,
                job_analysis=job_analysis.model_dump(),
                result=phase2_result,
            )
            try:
                persisted_run_id = self.persistence_repository.save_run(persistence_record)
                persistence_succeeded = True
            except Exception as exc:
                logger.warning(
                    "phase2 persistence failed",
                    extra={
                        "profile_id": source_profile.id,
                        "error_type": type(exc).__name__,
                    },
                )
                phase2_result = _with_persistence_warning(phase2_result)

        if self.settings.phase2_safe_logging_enabled:
            self._log_run_summary(artifacts, phase2_result, source_profile.id, persisted_run_id)

        return Phase2ServiceResult(
            ranking_response=artifacts.ranking_response,
            phase2_result=phase2_result,
            evidence_graph=artifacts.evidence_graph,
            coverage_map=artifacts.coverage_map,
            persistence_attempted=persistence_attempted,
            persistence_succeeded=persistence_succeeded,
            persisted_run_id=persisted_run_id,
        )

    def _log_run_summary(
        self,
        artifacts: Phase2RankingArtifacts,
        phase2_result: Phase2SelectionResult,
        profile_id: str,
        persisted_run_id: str | None,
    ) -> None:
        """Emit API-safe structured logs for development inspection."""

        logger.info(
            "phase2 run completed",
            extra={
                "profile_id": profile_id,
                "candidate_evidence_count": phase2_result.diagnostics.candidate_evidence_count,
                "scored_evidence_count": phase2_result.diagnostics.scored_evidence_count,
                "selected_experience_count": phase2_result.diagnostics.selected_experience_count,
                "selected_project_count": phase2_result.diagnostics.selected_project_count,
                "selected_skill_count": phase2_result.diagnostics.selected_skill_count,
                "warning_count": len(phase2_result.diagnostics.warnings),
                "headline_suggestion": artifacts.ranking_response.headline_suggestion,
                "persisted_run_id": persisted_run_id,
                **phase2_artifact_diagnostics_payload(artifacts.candidate_artifacts),
            },
        )


def _with_persistence_warning(result: Phase2SelectionResult) -> Phase2SelectionResult:
    """Return a partial-success result when optional persistence fails."""

    warning = "Phase 2 persistence failed; returning in-memory artifacts only."
    diagnostics = result.diagnostics.model_copy(
        update={
            "status": Phase2Status.PARTIAL,
            "warnings": [*result.diagnostics.warnings, warning],
        }
    )
    return result.model_copy(update={"diagnostics": diagnostics})


DEFAULT_PHASE2_SERVICE = Phase2Service()
