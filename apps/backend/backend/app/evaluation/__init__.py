"""Phase 7 evaluation contracts, models, and repository paths."""

from backend.app.evaluation.artifact_models import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactPayloadFormat,
    LoadedArtifactDocument,
    PersistedArtifactMetadata,
)
from backend.app.evaluation.case_models import (
    EvaluationActualOutputs,
    EvaluationCaseDefinition,
    EvaluationCaseMetadata,
    EvaluationExpectedOutputs,
    EvaluationStageActualOutput,
    EvaluationStageExpectation,
)
from backend.app.evaluation.contracts import (
    ArtifactStore,
    EvaluationCaseLoader,
    EvaluationReportWriter,
    EvaluationScorer,
    RealPipelineRunner,
)
from backend.app.evaluation.enums import EvaluationPackType, EvaluationRunStatus, ScoringOutcome
from backend.app.evaluation.loader import JsonEvaluationCaseLoader
from backend.app.evaluation.paths import (
    DEFAULT_EVALUATION_FIXTURE_ROOT,
    DEFAULT_EVALUATION_OUTPUT_ROOT,
    END_TO_END_FIXTURE_DIR,
    JD_PARSE_FIXTURE_DIR,
    RED_TEAM_FIXTURE_DIR,
    SELECTION_FIXTURE_DIR,
)
from backend.app.evaluation.run_loader import LoadedEvaluationRun, load_saved_evaluation_run, render_loaded_run_summary
from backend.app.evaluation.scorer import BasicExpectationScorer, EndToEndQualityScorer, RedTeamQualityScorer
from backend.app.evaluation.report_writer import (
    JsonEvaluationReportWriter,
    MarkdownJsonEvaluationReportWriter,
    build_aggregate_json_report,
    render_aggregate_markdown_report,
    render_case_markdown_report,
    render_case_metrics_csv,
    render_compact_terminal_summary,
)
from backend.app.evaluation.report_models import ReviewerSignal, RunSummary, ScoringMetric, ScoringSummary
from backend.app.evaluation.runner import OrchestratedRealPipelineRunner, RealPipelineRunResult
from backend.app.evaluation.runtime_models import (
    EvaluationDependencyStatus,
    EvaluationRunManifest,
    EvaluationRunnerConfig,
    EvaluationStageRunRecord,
)
from backend.app.evaluation.storage import LocalFileArtifactStore

__all__ = [
    "ArtifactManifest",
    "ArtifactManifestEntry",
    "ArtifactPayloadFormat",
    "ArtifactStore",
    "BasicExpectationScorer",
    "build_aggregate_json_report",
    "DEFAULT_EVALUATION_FIXTURE_ROOT",
    "DEFAULT_EVALUATION_OUTPUT_ROOT",
    "END_TO_END_FIXTURE_DIR",
    "EndToEndQualityScorer",
    "EvaluationDependencyStatus",
    "EvaluationActualOutputs",
    "EvaluationCaseDefinition",
    "EvaluationCaseLoader",
    "EvaluationCaseMetadata",
    "EvaluationExpectedOutputs",
    "EvaluationPackType",
    "EvaluationRunManifest",
    "EvaluationReportWriter",
    "EvaluationRunStatus",
    "EvaluationRunnerConfig",
    "EvaluationScorer",
    "EvaluationStageRunRecord",
    "EvaluationStageActualOutput",
    "EvaluationStageExpectation",
    "JD_PARSE_FIXTURE_DIR",
    "JsonEvaluationCaseLoader",
    "JsonEvaluationReportWriter",
    "MarkdownJsonEvaluationReportWriter",
    "LoadedArtifactDocument",
    "LoadedEvaluationRun",
    "LocalFileArtifactStore",
    "OrchestratedRealPipelineRunner",
    "RED_TEAM_FIXTURE_DIR",
    "RedTeamQualityScorer",
    "RealPipelineRunner",
    "RealPipelineRunResult",
    "RunSummary",
    "ReviewerSignal",
    "PersistedArtifactMetadata",
    "ScoringMetric",
    "ScoringOutcome",
    "ScoringSummary",
    "SELECTION_FIXTURE_DIR",
    "load_saved_evaluation_run",
    "render_aggregate_markdown_report",
    "render_case_markdown_report",
    "render_case_metrics_csv",
    "render_compact_terminal_summary",
    "render_loaded_run_summary",
]
