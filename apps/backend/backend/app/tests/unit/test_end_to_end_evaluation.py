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
from backend.app.evaluation.enums import EvaluationPackType, EvaluationRunStatus, ScoringOutcome
from backend.app.evaluation.report_models import ReviewerSignal, RunSummary, ScoringMetric, ScoringSummary
from backend.app.evaluation.report_writer import (
    MarkdownJsonEvaluationReportWriter,
    build_aggregate_json_report,
    render_case_markdown_report,
    render_compact_terminal_summary,
)
from backend.app.evaluation.scorer import EndToEndQualityScorer
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus
from backend.app.services.verification.types import (
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    VerificationDecisionOutcome,
    VerificationStatus,
)


def _case() -> EvaluationCaseDefinition:
    return EvaluationCaseDefinition(
        metadata=EvaluationCaseMetadata(
            case_id="case.end_to_end.synthetic",
            pack_type=EvaluationPackType.END_TO_END,
            scenario="synthetic_backend_case",
            description="Synthetic end-to-end scoring case.",
        ),
        input_payload={
            "source_profile_path": str((Path.cwd() / "data" / "master_profile.example.json").resolve()),
            "job_description_text": "Build Python APIs on AWS.",
        },
        expected_outputs=EvaluationExpectedOutputs(
            expected_pipeline_status=PipelineStatus.SUCCEEDED,
            expected_output_snapshot={
                "require_summary": True,
                "required_sections": ["summary", "experience", "skills"],
                "expected_selected_source_ids": ["exp.good"],
                "expected_omitted_source_ids": ["exp.old"],
                "min_fit_confidence": 0.6,
                "require_render_success": False,
            },
            reviewer_guidance=["Review whether the summary sounds generic."],
        ),
    )


def _actual_outputs() -> EvaluationActualOutputs:
    return EvaluationActualOutputs(
        run_id="run.synthetic.end_to_end",
        case_id="case.end_to_end.synthetic",
        pipeline_status=PipelineStatus.SUCCEEDED,
        stage_outputs=[
            EvaluationStageActualOutput(
                stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
                status=StageStatus.SUCCEEDED,
                output_snapshot={},
            ),
            EvaluationStageActualOutput(
                stage_name=StageName.VERIFY_GENERATED_CONTENT,
                status=StageStatus.SUCCEEDED,
                output_snapshot={},
            ),
        ],
    )


def _artifact_manifest(tmp_path: Path) -> ArtifactManifest:
    entry = ArtifactManifestEntry(
        artifact_id="artifact.phase3",
        run_id="run.synthetic.end_to_end",
        case_id="case.end_to_end.synthetic",
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        artifact_kind=ArtifactKind.PHASE3_RESULT,
        schema_version="phase7.v1",
        storage_path=str(tmp_path / "phase3_result.json"),
        relative_path="stages/generate_structured_content/phase3_result.json",
        content_type="application/json",
        payload_format=ArtifactPayloadFormat.JSON,
        metadata_path=str(tmp_path / "phase3_result.metadata.json"),
        created_at=datetime.now(timezone.utc),
    )
    return ArtifactManifest(
        run_id="run.synthetic.end_to_end",
        case_id="case.end_to_end.synthetic",
        generated_at=datetime.now(timezone.utc),
        entries=[entry],
    )


def test_end_to_end_scorer_marks_review_for_weak_summary(monkeypatch, tmp_path: Path) -> None:
    def fake_parse(stage_output, model_cls):
        if model_cls.__name__ == "GenerateStructuredContentOutput":
            phase3_result = SimpleNamespace(
                summary=SimpleNamespace(text="Results-driven dynamic professional with proven track record.", confidence_score=0.45),
                headline=SimpleNamespace(text="Backend Engineer", confidence_score=0.8),
                selected_experiences=[SimpleNamespace(source_item_id="exp.good", generated_bullets=[SimpleNamespace(confidence_score=0.45)])],
                selected_projects=[SimpleNamespace(source_item_id="proj.side", generated_bullets=[SimpleNamespace(confidence_score=0.4), SimpleNamespace(confidence_score=0.4), SimpleNamespace(confidence_score=0.4)])],
                skills_to_highlight=[SimpleNamespace(skill_name="Python")],
                omitted_items=[SimpleNamespace(source_item_id="exp.old")],
                warnings=[],
            )
            return SimpleNamespace(generation_payload=SimpleNamespace(), phase3_result=phase3_result)
        if model_cls.__name__ == "VerifyGeneratedContentOutput":
            report = SimpleNamespace(
                status=VerificationStatus.PASSED_WITH_WARNINGS,
                issues=[],
                item_results=[],
                renderable=True,
                decision_outcome=VerificationDecisionOutcome.PASS_WITH_WARNINGS,
            )
            phase3_result = SimpleNamespace(
                headline=SimpleNamespace(text="Backend Engineer"),
                summary=SimpleNamespace(text="Results-driven dynamic professional with proven track record."),
                selected_experiences=[SimpleNamespace(source_item_id="exp.good", generated_bullets=[SimpleNamespace(confidence_score=0.45)])],
                selected_projects=[SimpleNamespace(source_item_id="proj.side", generated_bullets=[SimpleNamespace(confidence_score=0.4), SimpleNamespace(confidence_score=0.4), SimpleNamespace(confidence_score=0.4)])],
                skills_to_highlight=[SimpleNamespace(skill_name="Python")],
            )
            return SimpleNamespace(verification_report=report, rendering_output=SimpleNamespace(verified_result=phase3_result))
        return None

    fake_assessment = SimpleNamespace(
        quality_score=0.4,
        hard_fail=False,
        issues=[SimpleNamespace(issue_type="filler_language"), SimpleNamespace(issue_type="weak_alignment")],
    )
    monkeypatch.setattr("backend.app.evaluation.scorer._parse_stage_output", fake_parse)
    monkeypatch.setattr("backend.app.evaluation.scorer.assess_summary", lambda *_args, **_kwargs: fake_assessment)
    monkeypatch.setattr(
        "backend.app.evaluation.scorer.assess_headline",
        lambda *_args, **_kwargs: SimpleNamespace(quality_score=0.9, hard_fail=False, issues=[]),
    )

    summary = EndToEndQualityScorer().score_case(_case(), _actual_outputs(), _artifact_manifest(tmp_path))

    assert summary.outcome is ScoringOutcome.REVIEW
    signals = {signal.signal_name: signal for signal in summary.reviewer_signals}
    assert signals["weak_summary"].triggered is True
    assert signals["low_confidence_fit"].triggered is True
    assert any("Review whether the summary sounds generic." in comment for comment in summary.reviewer_comments)


def test_end_to_end_scorer_fails_on_unsupported_claim_risk(monkeypatch, tmp_path: Path) -> None:
    def fake_parse(stage_output, model_cls):
        if model_cls.__name__ == "GenerateStructuredContentOutput":
            phase3_result = SimpleNamespace(
                summary=SimpleNamespace(text="Backend engineer building Python APIs.", confidence_score=0.8),
                headline=SimpleNamespace(text="Backend Engineer", confidence_score=0.9),
                selected_experiences=[SimpleNamespace(source_item_id="exp.good", generated_bullets=[SimpleNamespace(confidence_score=0.8)])],
                selected_projects=[],
                skills_to_highlight=[SimpleNamespace(skill_name="Python")],
                omitted_items=[SimpleNamespace(source_item_id="exp.old")],
                warnings=[],
            )
            return SimpleNamespace(generation_payload=SimpleNamespace(), phase3_result=phase3_result)
        if model_cls.__name__ == "VerifyGeneratedContentOutput":
            issue = SimpleNamespace(
                category=IssueCategory.UNSUPPORTED_CLAIM,
                severity=IssueSeverity.HIGH,
            )
            report = SimpleNamespace(
                status=VerificationStatus.FAILED,
                issues=[issue],
                item_results=[],
                renderable=False,
                decision_outcome=VerificationDecisionOutcome.FAIL_CLOSED,
            )
            phase3_result = SimpleNamespace(
                headline=SimpleNamespace(text="Backend Engineer"),
                summary=SimpleNamespace(text="Backend engineer building Python APIs."),
                selected_experiences=[SimpleNamespace(source_item_id="exp.good", generated_bullets=[SimpleNamespace(confidence_score=0.8)])],
                selected_projects=[],
                skills_to_highlight=[SimpleNamespace(skill_name="Python")],
            )
            return SimpleNamespace(verification_report=report, rendering_output=SimpleNamespace(verified_result=phase3_result))
        if model_cls.__name__ == "CompilePdfOutput":
            return SimpleNamespace(
                compile_result=SimpleNamespace(
                    compile_success=False,
                    return_code=1,
                    warnings_detected=[],
                    errors_detected=["compile error"],
                )
            )
        return None

    monkeypatch.setattr("backend.app.evaluation.scorer._parse_stage_output", fake_parse)
    monkeypatch.setattr(
        "backend.app.evaluation.scorer.assess_summary",
        lambda *_args, **_kwargs: SimpleNamespace(quality_score=0.9, hard_fail=False, issues=[]),
    )
    monkeypatch.setattr(
        "backend.app.evaluation.scorer.assess_headline",
        lambda *_args, **_kwargs: SimpleNamespace(quality_score=0.9, hard_fail=False, issues=[]),
    )

    case = _case().model_copy(
        update={
            "expected_outputs": _case().expected_outputs.model_copy(
                update={
                    "expected_output_snapshot": {
                        **_case().expected_outputs.expected_output_snapshot,
                        "require_render_success": True,
                    }
                }
            )
        }
    )
    actual = _actual_outputs().model_copy(
        update={
            "stage_outputs": [
                *_actual_outputs().stage_outputs,
                EvaluationStageActualOutput(
                    stage_name=StageName.COMPILE_PDF,
                    status=StageStatus.SUCCEEDED,
                    output_snapshot={},
                ),
            ]
        }
    )

    summary = EndToEndQualityScorer().score_case(case, actual, _artifact_manifest(tmp_path))

    assert summary.outcome is ScoringOutcome.FAIL
    signals = {signal.signal_name: signal for signal in summary.reviewer_signals}
    assert signals["unsupported_claim_risk"].triggered is True


def test_report_writer_outputs_markdown_and_json(tmp_path: Path) -> None:
    writer = MarkdownJsonEvaluationReportWriter()
    case = _case()
    run_summary = RunSummary(
        run_id="run.synthetic.end_to_end",
        case_id=case.metadata.case_id,
        pack_type=case.metadata.pack_type,
        status=EvaluationRunStatus.PASSED,
        pipeline_status=PipelineStatus.SUCCEEDED,
    )
    scoring_summary = ScoringSummary(
        run_id="run.synthetic.end_to_end",
        case_id=case.metadata.case_id,
        scorer_name="end_to_end_quality_scorer",
        outcome=ScoringOutcome.REVIEW,
        overall_score=0.72,
        metrics=[ScoringMetric(metric_name="summary_quality_fit", score=0.6, passed=False, details="weak summary")],
        findings=["weak summary"],
        reviewer_signals=[ReviewerSignal(signal_name="weak_summary", triggered=True, severity="warning", details="generic wording")],
        reviewer_comments=["Inspect the generated summary."],
        artifact_paths={"phase3_result": str(tmp_path / "phase3_result.json")},
    )
    manifest = _artifact_manifest(tmp_path)

    report_path = writer.write_case_report(
        case=case,
        run_summary=run_summary,
        scoring_summary=scoring_summary,
        artifact_manifest=manifest,
        output_root=tmp_path,
    )

    assert report_path.name == "report.md"
    assert (tmp_path / "report.json").exists()
    markdown = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "## Structured Checks" in markdown
    assert "## Reviewer Signals" in markdown
    assert "## Artifact Links" in markdown


def test_aggregate_json_and_compact_terminal_summary() -> None:
    results = [
        {
            "case_id": "case.a",
            "pipeline_status": "succeeded",
            "overall_score": 0.82,
            "outcome": "review",
            "reviewer_signals": [{"signal_name": "weak_summary", "triggered": True}],
        },
        {
            "case_id": "case.b",
            "pipeline_status": "succeeded",
            "overall_score": 0.95,
            "outcome": "pass",
            "reviewer_signals": [],
        },
    ]

    aggregate = build_aggregate_json_report(results=results)
    terminal = render_compact_terminal_summary(results)

    assert aggregate["total_cases"] == 2
    assert aggregate["outcomes"] == {"review": 1, "pass": 1}
    assert "[REVIEW] case.a" in terminal
    assert "signals=weak_summary" in terminal
    assert "[PASS] case.b" in terminal


def test_render_case_markdown_report_structure(tmp_path: Path) -> None:
    case = _case()
    run_summary = RunSummary(
        run_id="run.synthetic.end_to_end",
        case_id=case.metadata.case_id,
        pack_type=case.metadata.pack_type,
        status=EvaluationRunStatus.PASSED,
        pipeline_status=PipelineStatus.SUCCEEDED,
    )
    scoring_summary = ScoringSummary(
        run_id="run.synthetic.end_to_end",
        case_id=case.metadata.case_id,
        scorer_name="end_to_end_quality_scorer",
        outcome=ScoringOutcome.REVIEW,
        overall_score=0.68,
        metrics=[ScoringMetric(metric_name="render_success", score=1.0, passed=True, details="render not requested")],
        reviewer_signals=[ReviewerSignal(signal_name="section_imbalance", triggered=True, severity="warning", details="projects outweigh experience")],
        reviewer_comments=["Check the project/experience balance."],
        artifact_paths={"phase3_result": str(tmp_path / "phase3_result.json")},
    )
    markdown = render_case_markdown_report(
        case=case,
        run_summary=run_summary,
        scoring_summary=scoring_summary,
        artifact_manifest=_artifact_manifest(tmp_path),
    )

    assert "# Evaluation Report" in markdown
    assert "## Run" in markdown
    assert "## Structured Checks" in markdown
    assert "## Reviewer Comments" in markdown
