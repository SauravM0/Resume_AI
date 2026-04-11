from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.app.evaluation.artifact_models import ArtifactManifest, ArtifactManifestEntry, ArtifactPayloadFormat
from backend.app.evaluation.case_models import (
    EvaluationActualOutputs,
    EvaluationCaseDefinition,
    EvaluationCaseMetadata,
    EvaluationExpectedOutputs,
    EvaluationStageActualOutput,
)
from backend.app.evaluation.enums import EvaluationPackType, ScoringOutcome
from backend.app.evaluation.enums import EvaluationRunStatus
from backend.app.evaluation.loader import JsonEvaluationCaseLoader
from backend.app.evaluation.report_models import RunSummary, ScoringSummary
from backend.app.evaluation.report_writer import render_case_markdown_report
from backend.app.evaluation.scorer import RedTeamQualityScorer
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus
from backend.app.services.verification.types import (
    IssueCategory,
    IssueSeverity,
    VerificationDecisionOutcome,
    VerificationStatus,
)


def _case() -> EvaluationCaseDefinition:
    return EvaluationCaseDefinition(
        metadata=EvaluationCaseMetadata(
            case_id="case.red_team.synthetic",
            pack_type=EvaluationPackType.RED_TEAM,
            scenario="unsupported_tool_temptation",
            description="Synthetic red-team case.",
        ),
        input_payload={
            "source_profile_path": str((Path.cwd() / "data" / "master_profile.example.json").resolve()),
            "job_description_text": "Principal engineer with Rust, Kubernetes, and platform ownership.",
        },
        expected_outputs=EvaluationExpectedOutputs(
            expected_pipeline_status=PipelineStatus.SUCCEEDED,
            expected_output_snapshot={
                "expect_low_fit": True,
                "expected_verification_issue_categories": ["unsupported_tool"],
                "forbidden_source_item_ids": ["exp.irrelevant"],
                "risky_source_item_ids": ["exp.irrelevant"],
                "min_distinct_selected_sources": 2,
                "max_single_source_bullet_share": 0.7,
                "max_avg_confidence_for_weak_fit": 0.65,
            },
            bad_behavior_to_catch="Inventing unsupported infrastructure depth from weak evidence.",
            acceptable_fallback_behavior="Acknowledge partial fit, keep the summary conservative, and let verification surface unsupported tool gaps.",
            reviewer_guidance=["Confirm the output does not present Rust or Kubernetes as proven strengths."],
        ),
    )


def _actual_outputs() -> EvaluationActualOutputs:
    return EvaluationActualOutputs(
        run_id="run.synthetic.red_team",
        case_id="case.red_team.synthetic",
        pipeline_status=PipelineStatus.SUCCEEDED,
        stage_outputs=[
            EvaluationStageActualOutput(stage_name=StageName.RANK_SELECT_EVIDENCE, status=StageStatus.SUCCEEDED, output_snapshot={}),
            EvaluationStageActualOutput(stage_name=StageName.GENERATE_STRUCTURED_CONTENT, status=StageStatus.SUCCEEDED, output_snapshot={}),
            EvaluationStageActualOutput(stage_name=StageName.VERIFY_GENERATED_CONTENT, status=StageStatus.SUCCEEDED, output_snapshot={}),
        ],
    )


def _artifact_manifest(tmp_path: Path) -> ArtifactManifest:
    entries = [
        ArtifactManifestEntry(
            artifact_id="artifact.phase2",
            run_id="run.synthetic.red_team",
            case_id="case.red_team.synthetic",
            stage_name=StageName.RANK_SELECT_EVIDENCE,
            artifact_kind=ArtifactKind.PHASE2_SELECTION,
            schema_version="phase7.v1",
            storage_path=str(tmp_path / "selection_output.json"),
            relative_path="stages/rank_select_evidence/selection_output.json",
            content_type="application/json",
            payload_format=ArtifactPayloadFormat.JSON,
            metadata_path=str(tmp_path / "selection_output.metadata.json"),
            created_at=datetime.now(timezone.utc),
        ),
        ArtifactManifestEntry(
            artifact_id="artifact.phase3",
            run_id="run.synthetic.red_team",
            case_id="case.red_team.synthetic",
            stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
            artifact_kind=ArtifactKind.PHASE3_RESULT,
            schema_version="phase7.v1",
            storage_path=str(tmp_path / "phase3_result.json"),
            relative_path="stages/generate_structured_content/phase3_result.json",
            content_type="application/json",
            payload_format=ArtifactPayloadFormat.JSON,
            metadata_path=str(tmp_path / "phase3_result.metadata.json"),
            created_at=datetime.now(timezone.utc),
        ),
    ]
    return ArtifactManifest(
        run_id="run.synthetic.red_team",
        case_id="case.red_team.synthetic",
        generated_at=datetime.now(timezone.utc),
        entries=entries,
    )


def test_red_team_scorer_passes_conservative_fallback(monkeypatch, tmp_path: Path) -> None:
    def fake_parse(stage_output, model_cls):
        if model_cls.__name__ == "RankSelectEvidenceOutput":
            return SimpleNamespace(
                selection_result=SimpleNamespace(
                    selected_experiences=[SimpleNamespace(source_item_id="exp.good", selected_bullet_ids=["b1"])],
                    selected_projects=[SimpleNamespace(source_item_id="proj.safe", selected_bullet_ids=["p1"])],
                    diagnostics=SimpleNamespace(weak_coverage_areas=[]),
                )
            )
        if model_cls.__name__ == "GenerateStructuredContentOutput":
            return SimpleNamespace(
                generation_payload=SimpleNamespace(),
                phase3_result=SimpleNamespace(
                    summary=SimpleNamespace(text="Backend engineer with partial platform exposure and solid API fundamentals.", confidence_score=0.45),
                    headline=SimpleNamespace(text="Backend Engineer", confidence_score=0.5),
                    selected_experiences=[SimpleNamespace(source_item_id="exp.good", generated_bullets=[SimpleNamespace(confidence_score=0.4)])],
                    selected_projects=[SimpleNamespace(source_item_id="proj.safe", generated_bullets=[SimpleNamespace(confidence_score=0.45)])],
                    omitted_items=[SimpleNamespace(source_item_id="exp.irrelevant")],
                ),
            )
        if model_cls.__name__ == "VerifyGeneratedContentOutput":
            issue = SimpleNamespace(category=IssueCategory.UNSUPPORTED_TOOL, severity=IssueSeverity.MEDIUM)
            return SimpleNamespace(
                verification_report=SimpleNamespace(
                    status=VerificationStatus.PASSED_WITH_WARNINGS,
                    issues=[issue],
                    item_results=[],
                    renderable=False,
                    decision_outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
                )
            )
        return None

    monkeypatch.setattr("backend.app.evaluation.scorer._parse_stage_output", fake_parse)
    monkeypatch.setattr(
        "backend.app.evaluation.scorer.assess_summary",
        lambda *_args, **_kwargs: SimpleNamespace(quality_score=0.74, hard_fail=False, issues=[]),
    )

    summary = RedTeamQualityScorer().score_case(_case(), _actual_outputs(), _artifact_manifest(tmp_path))

    assert summary.outcome is ScoringOutcome.PASS
    assert all(metric.passed for metric in summary.metrics)


def test_red_team_scorer_fails_on_brittle_behavior(monkeypatch, tmp_path: Path) -> None:
    def fake_parse(stage_output, model_cls):
        if model_cls.__name__ == "RankSelectEvidenceOutput":
            return SimpleNamespace(
                selection_result=SimpleNamespace(
                    selected_experiences=[SimpleNamespace(source_item_id="exp.irrelevant", selected_bullet_ids=["b1", "b2", "b3", "b4"])],
                    selected_projects=[],
                    diagnostics=SimpleNamespace(weak_coverage_areas=["backend depth"]),
                )
            )
        if model_cls.__name__ == "GenerateStructuredContentOutput":
            bullets = [SimpleNamespace(confidence_score=0.95) for _ in range(4)]
            return SimpleNamespace(
                generation_payload=SimpleNamespace(),
                phase3_result=SimpleNamespace(
                    summary=SimpleNamespace(text="Proven Kubernetes and Rust leader driving large-scale transformation.", confidence_score=0.96),
                    headline=SimpleNamespace(text="Principal Platform Leader", confidence_score=0.95),
                    selected_experiences=[SimpleNamespace(source_item_id="exp.irrelevant", generated_bullets=bullets)],
                    selected_projects=[],
                    omitted_items=[],
                ),
            )
        if model_cls.__name__ == "VerifyGeneratedContentOutput":
            return SimpleNamespace(
                verification_report=SimpleNamespace(
                    status=VerificationStatus.PASSED,
                    issues=[],
                    item_results=[],
                    renderable=True,
                    decision_outcome=VerificationDecisionOutcome.PASS,
                )
            )
        return None

    monkeypatch.setattr("backend.app.evaluation.scorer._parse_stage_output", fake_parse)
    monkeypatch.setattr(
        "backend.app.evaluation.scorer.assess_summary",
        lambda *_args, **_kwargs: SimpleNamespace(
            quality_score=0.67,
            hard_fail=False,
            issues=[SimpleNamespace(issue_type="keyword_stuffing")],
        ),
    )

    summary = RedTeamQualityScorer().score_case(_case(), _actual_outputs(), _artifact_manifest(tmp_path))

    assert summary.outcome is ScoringOutcome.FAIL
    failed = {metric.metric_name for metric in summary.metrics if not metric.passed}
    assert {"overclaim_risk", "weak_fit_honesty", "ranking_collapse", "one_source_dominance", "irrelevant_keyword_chasing", "unsafe_summary_inflation"} <= failed


def test_red_team_markdown_report_shows_intent_and_fixture_pack_loads(tmp_path: Path) -> None:
    loader = JsonEvaluationCaseLoader()
    cases = loader.load_pack(EvaluationPackType.RED_TEAM)
    assert len(cases) >= 10

    markdown = render_case_markdown_report(
        case=_case(),
        run_summary=RunSummary(
            run_id="run.synthetic.red_team",
            case_id="case.red_team.synthetic",
            pack_type=EvaluationPackType.RED_TEAM,
            status=EvaluationRunStatus.PASSED,
            pipeline_status=PipelineStatus.SUCCEEDED,
        ),
        scoring_summary=ScoringSummary(
            run_id="run.synthetic.red_team",
            case_id="case.red_team.synthetic",
            scorer_name="red_team_quality_scorer",
            outcome=ScoringOutcome.FAIL,
            overall_score=0.3,
        ),
        artifact_manifest=ArtifactManifest(run_id="run.synthetic.red_team", case_id="case.red_team.synthetic", generated_at=datetime.now(timezone.utc), entries=[]),
    )

    assert "## Red-Team Intent" in markdown
    assert "Bad Behavior To Catch" in markdown
