from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.app.evaluation import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactPayloadFormat,
    DEFAULT_EVALUATION_FIXTURE_ROOT,
    DEFAULT_EVALUATION_OUTPUT_ROOT,
    END_TO_END_FIXTURE_DIR,
    EvaluationActualOutputs,
    EvaluationCaseDefinition,
    EvaluationCaseMetadata,
    EvaluationExpectedOutputs,
    EvaluationPackType,
    EvaluationRunStatus,
    EvaluationStageActualOutput,
    EvaluationStageExpectation,
    JD_PARSE_FIXTURE_DIR,
    RED_TEAM_FIXTURE_DIR,
    RunSummary,
    ScoringMetric,
    ScoringOutcome,
    ScoringSummary,
    SELECTION_FIXTURE_DIR,
)
from backend.app.orchestration.enums import (
    ArtifactKind,
    ArtifactStorageBackend,
    PipelineStatus,
    StageName,
    StageStatus,
)
from backend.app.orchestration.types import PipelineArtifactRef


def test_phase7_paths_match_reserved_repo_directories() -> None:
    assert DEFAULT_EVALUATION_FIXTURE_ROOT == Path("fixtures/evaluation").resolve()
    assert JD_PARSE_FIXTURE_DIR == Path("fixtures/evaluation/jd_parse").resolve()
    assert SELECTION_FIXTURE_DIR == Path("fixtures/evaluation/selection").resolve()
    assert END_TO_END_FIXTURE_DIR == Path("fixtures/evaluation/end_to_end").resolve()
    assert RED_TEAM_FIXTURE_DIR == Path("fixtures/evaluation/red_team").resolve()
    assert DEFAULT_EVALUATION_OUTPUT_ROOT == Path("outputs/evaluation_runs").resolve()


def test_phase7_models_capture_case_artifacts_and_scoring() -> None:
    artifact_ref = PipelineArtifactRef(
        artifact_id="artifact.phase7.result",
        kind=ArtifactKind.PHASE3_RESULT,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        storage_backend=ArtifactStorageBackend.LOCAL_FILE,
        schema_version="phase7.v1",
        uri="outputs/evaluation_runs/run-123/phase3_result.json",
        content_type="application/json",
    )
    case = EvaluationCaseDefinition(
        metadata=EvaluationCaseMetadata(
            case_id="case.end_to_end.backend",
            pack_type=EvaluationPackType.END_TO_END,
            scenario="backend_resume_generation",
            description="Exercises the real end-to-end pipeline for a backend profile.",
            tags=["golden", "ci"],
        ),
        input_payload={"job_description_text": "Build reliable Python services."},
        expected_outputs=EvaluationExpectedOutputs(
            expected_pipeline_status=PipelineStatus.SUCCEEDED,
            expected_stage_sequence=[
                StageName.PARSE_JOB_DESCRIPTION,
                StageName.RANK_SELECT_EVIDENCE,
                StageName.GENERATE_STRUCTURED_CONTENT,
            ],
            stage_expectations=[
                EvaluationStageExpectation(
                    stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
                    expected_status=StageStatus.SUCCEEDED,
                    required_artifact_kinds=[ArtifactKind.PHASE3_RESULT],
                )
            ],
            required_artifact_kinds=[ArtifactKind.PHASE3_RESULT],
            expected_output_snapshot={"headline_present": True},
        ),
    )
    actual = EvaluationActualOutputs(
        run_id="run.phase7.123",
        case_id=case.metadata.case_id,
        pipeline_status=PipelineStatus.SUCCEEDED,
        stage_outputs=[
            EvaluationStageActualOutput(
                stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
                status=StageStatus.SUCCEEDED,
                artifact_refs=[artifact_ref],
                output_snapshot={"headline_present": True},
            )
        ],
        final_artifact_refs=[artifact_ref],
    )
    manifest = ArtifactManifest(
        run_id=actual.run_id,
        case_id=actual.case_id,
        generated_at=datetime.now(timezone.utc),
        entries=[
            ArtifactManifestEntry(
                artifact_id="artifact.manifest.phase3",
                run_id=actual.run_id,
                case_id=actual.case_id,
                stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
                artifact_kind=ArtifactKind.PHASE3_RESULT,
                schema_version="phase7.v1",
                storage_path="outputs/evaluation_runs/run-123/phase3_result.json",
                relative_path="stages/generate_structured_content/phase3_result.json",
                content_type="application/json",
                payload_format=ArtifactPayloadFormat.JSON,
                metadata_path="outputs/evaluation_runs/run-123/stages/generate_structured_content/phase3_result.json.metadata.json",
                created_at=datetime.now(timezone.utc),
            )
        ],
    )
    scoring = ScoringSummary(
        run_id=actual.run_id,
        case_id=actual.case_id,
        scorer_name="baseline_expectation_scorer",
        outcome=ScoringOutcome.PASS,
        overall_score=1.0,
        metrics=[ScoringMetric(metric_name="stage_status_match", score=1.0, passed=True)],
    )
    summary = RunSummary(
        run_id=actual.run_id,
        case_id=actual.case_id,
        pack_type=case.metadata.pack_type,
        status=EvaluationRunStatus.PASSED,
        pipeline_status=actual.pipeline_status,
        artifact_manifest_path="outputs/evaluation_runs/run-123/manifest.json",
        summary_path="outputs/evaluation_runs/run-123/summary.md",
        report_path="outputs/evaluation_runs/run-123/report.json",
    )

    assert case.metadata.pack_type == EvaluationPackType.END_TO_END
    assert actual.stage_outputs[0].artifact_refs[0].kind == ArtifactKind.PHASE3_RESULT
    assert manifest.entries[0].stage_name == StageName.GENERATE_STRUCTURED_CONTENT
    assert scoring.overall_score == 1.0
    assert summary.status == EvaluationRunStatus.PASSED
