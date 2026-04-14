"""Scorers for real evaluation runs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.app.evaluation.artifact_models import ArtifactManifest
from backend.app.evaluation.case_models import EvaluationActualOutputs, EvaluationCaseDefinition
from backend.app.evaluation.enums import EvaluationPackType, ScoringOutcome
from backend.app.evaluation.report_models import ReviewerSignal, ScoringMetric, ScoringSummary
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus
from backend.app.orchestration.pipeline_models import (
    CompilePdfOutput,
    GenerateStructuredContentOutput,
    RankSelectEvidenceOutput,
    VerifyGeneratedContentOutput,
)
from backend.app.services.verification.types import IssueCategory, IssueSeverity, VerificationStatus
from resume_optimizer.phase3_headline_summary import HeadlineSummaryIssueType, assess_headline, assess_summary


class BasicExpectationScorer:
    """Score basic contract alignment between expected and actual outputs."""

    def score_case(
        self,
        case: EvaluationCaseDefinition,
        actual_outputs: EvaluationActualOutputs,
        artifact_manifest: ArtifactManifest,
    ) -> ScoringSummary:
        expected = case.expected_outputs
        artifact_kinds = {entry.artifact_kind for entry in artifact_manifest.entries}
        status_match = actual_outputs.pipeline_status == expected.expected_pipeline_status
        required_artifacts_match = all(
            artifact_kind in artifact_kinds
            for artifact_kind in expected.required_artifact_kinds
        )
        metrics = [
            ScoringMetric(
                metric_name="pipeline_status_match",
                score=1.0 if status_match else 0.0,
                passed=status_match,
                details=(
                    f"expected={expected.expected_pipeline_status.value}, "
                    f"actual={actual_outputs.pipeline_status.value}"
                ),
            ),
            ScoringMetric(
                metric_name="required_artifacts_present",
                score=1.0 if required_artifacts_match else 0.0,
                passed=required_artifacts_match,
                details=f"required={len(expected.required_artifact_kinds)}, present={len(artifact_kinds)}",
            ),
        ]
        overall_score = sum(metric.score for metric in metrics) / len(metrics)
        outcome = ScoringOutcome.PASS if all(metric.passed for metric in metrics) else ScoringOutcome.FAIL
        findings = [metric.details for metric in metrics if metric.details is not None and not metric.passed]
        return ScoringSummary(
            run_id=actual_outputs.run_id,
            case_id=actual_outputs.case_id,
            scorer_name="basic_expectation_scorer",
            outcome=outcome,
            overall_score=overall_score,
            metrics=metrics,
            findings=findings,
            artifact_paths=_artifact_paths(artifact_manifest),
        )


@dataclass(frozen=True)
class _MetricDecision:
    score: float
    passed: bool
    details: str


class EndToEndQualityScorer:
    """End-to-end scorer for final structured output and optional render quality.

    This scorer does not claim to fully automate human resume judgment. It emits:
    - measurable structured checks
    - reviewer-visible risk signals
    - explicit artifact paths for manual inspection
    """

    def __init__(self) -> None:
        self._fallback = BasicExpectationScorer()

    def score_case(
        self,
        case: EvaluationCaseDefinition,
        actual_outputs: EvaluationActualOutputs,
        artifact_manifest: ArtifactManifest,
    ) -> ScoringSummary:
        if case.metadata.pack_type is not EvaluationPackType.END_TO_END:
            return self._fallback.score_case(case, actual_outputs, artifact_manifest)

        expected = case.expected_outputs
        expected_snapshot = expected.expected_output_snapshot
        stage_map = {stage.stage_name: stage for stage in actual_outputs.stage_outputs}
        artifact_paths = _artifact_paths(artifact_manifest)

        generation_output = _parse_stage_output(stage_map.get(StageName.GENERATE_STRUCTURED_CONTENT), GenerateStructuredContentOutput)
        verification_output = _parse_stage_output(stage_map.get(StageName.VERIFY_GENERATED_CONTENT), VerifyGeneratedContentOutput)
        compile_output = _parse_stage_output(stage_map.get(StageName.COMPILE_PDF), CompilePdfOutput)

        metrics: list[ScoringMetric] = []
        pipeline_match = actual_outputs.pipeline_status == expected.expected_pipeline_status
        metrics.append(
            ScoringMetric(
                metric_name="pipeline_status_match",
                score=1.0 if pipeline_match else 0.0,
                passed=pipeline_match,
                details=(
                    f"expected={expected.expected_pipeline_status.value}, "
                    f"actual={actual_outputs.pipeline_status.value}"
                ),
            )
        )

        summary_eval = self._score_summary_quality(generation_output, verification_output, expected_snapshot)
        metrics.append(
            ScoringMetric(
                metric_name="summary_quality_fit",
                score=summary_eval.score,
                passed=summary_eval.passed,
                details=summary_eval.details,
            )
        )

        section_eval = self._score_section_composition(generation_output, expected_snapshot)
        metrics.append(
            ScoringMetric(
                metric_name="section_composition_sanity",
                score=section_eval.score,
                passed=section_eval.passed,
                details=section_eval.details,
            )
        )

        faithfulness_eval = self._score_faithfulness(verification_output)
        metrics.append(
            ScoringMetric(
                metric_name="selected_content_faithfulness",
                score=faithfulness_eval.score,
                passed=faithfulness_eval.passed,
                details=faithfulness_eval.details,
            )
        )

        omission_eval = self._score_omissions(generation_output, expected_snapshot)
        metrics.append(
            ScoringMetric(
                metric_name="omission_correctness",
                score=omission_eval.score,
                passed=omission_eval.passed,
                details=omission_eval.details,
            )
        )

        verification_eval = self._score_verification_behavior(verification_output, expected_snapshot)
        metrics.append(
            ScoringMetric(
                metric_name="verification_behavior",
                score=verification_eval.score,
                passed=verification_eval.passed,
                details=verification_eval.details,
            )
        )

        completeness_eval = self._score_completeness(generation_output, verification_output, expected_snapshot)
        metrics.append(
            ScoringMetric(
                metric_name="final_output_completeness",
                score=completeness_eval.score,
                passed=completeness_eval.passed,
                details=completeness_eval.details,
            )
        )

        render_eval = self._score_render(compile_output, expected_snapshot, stage_map)
        metrics.append(
            ScoringMetric(
                metric_name="render_success",
                score=render_eval.score,
                passed=render_eval.passed,
                details=render_eval.details,
            )
        )

        reviewer_signals = self._build_reviewer_signals(
            generation_output=generation_output,
            verification_output=verification_output,
            expected_snapshot=expected_snapshot,
            summary_metric=summary_eval,
            section_metric=section_eval,
            omission_metric=omission_eval,
        )
        findings = [metric.details for metric in metrics if not metric.passed and metric.details]
        findings.extend(signal.details for signal in reviewer_signals if signal.triggered and signal.details)
        reviewer_comments = self._build_reviewer_comments(case, reviewer_signals, artifact_paths)

        measurable_scores = [metric.score for metric in metrics]
        overall_score = round(sum(measurable_scores) / len(measurable_scores), 4) if measurable_scores else 0.0

        outcome = _resolve_outcome(
            metrics=metrics,
            reviewer_signals=reviewer_signals,
            pipeline_status=actual_outputs.pipeline_status,
            verification_output=verification_output,
            require_render_success=bool(expected_snapshot.get("require_render_success", False)),
        )

        return ScoringSummary(
            run_id=actual_outputs.run_id,
            case_id=actual_outputs.case_id,
            scorer_name="end_to_end_quality_scorer",
            outcome=outcome,
            overall_score=overall_score,
            metrics=metrics,
            findings=[item for item in findings if item],
            reviewer_signals=reviewer_signals,
            reviewer_comments=reviewer_comments,
            artifact_paths=artifact_paths,
        )

    def _score_summary_quality(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        verification_output: VerifyGeneratedContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        require_summary = bool(expected_snapshot.get("require_summary", True))
        if generation_output is None or generation_output.phase3_result.summary is None:
            if require_summary:
                return _MetricDecision(0.0, False, "missing generated summary")
            return _MetricDecision(1.0, True, "summary not required")

        summary = generation_output.phase3_result.summary
        summary_assessment = assess_summary(generation_output.generation_payload, summary.text)
        headline_score = 1.0
        if generation_output.phase3_result.headline is not None:
            headline_score = assess_headline(
                generation_output.generation_payload,
                generation_output.phase3_result.headline.text,
            ).quality_score

        summary_verification_penalty = 0.0
        if verification_output is not None:
            summary_items = [
                item for item in verification_output.verification_report.item_results
                if item.item_type == "summary"
            ]
            if summary_items:
                summary_item = summary_items[0]
                if summary_item.status in {VerificationStatus.FAILED, VerificationStatus.BLOCKED}:
                    summary_verification_penalty = 0.4
                elif summary_item.status == VerificationStatus.PASSED_WITH_WARNINGS:
                    summary_verification_penalty = 0.15

        score = max(0.0, min(1.0, ((summary_assessment.quality_score + headline_score) / 2) - summary_verification_penalty))
        passed = not summary_assessment.hard_fail and score >= float(expected_snapshot.get("min_summary_quality", 0.55))
        details = (
            f"summary_quality={summary_assessment.quality_score:.2f}, "
            f"headline_quality={headline_score:.2f}, "
            f"hard_fail={summary_assessment.hard_fail}, "
            f"summary_words={len(summary.text.split())}"
        )
        return _MetricDecision(round(score, 4), passed, details)

    def _score_section_composition(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        if generation_output is None:
            return _MetricDecision(0.0, False, "generation output missing")

        result = generation_output.phase3_result
        required_sections = set(expected_snapshot.get("required_sections", ["summary", "experience", "skills"]))
        present_sections = {
            section
            for section, present in {
                "headline": result.headline is not None,
                "summary": result.summary is not None,
                "experience": bool(result.selected_experiences),
                "projects": bool(result.selected_projects),
                "skills": bool(result.skills_to_highlight),
            }.items()
            if present
        }
        required_present = len(required_sections & present_sections) / len(required_sections) if required_sections else 1.0

        experience_bullets = sum(len(item.generated_bullets) for item in result.selected_experiences)
        project_bullets = sum(len(item.generated_bullets) for item in result.selected_projects)
        if experience_bullets == 0 and project_bullets > 0:
            balance_score = 0.3
        elif experience_bullets > 0 and project_bullets > 0:
            dominant = max(experience_bullets, project_bullets) / max(1, experience_bullets + project_bullets)
            balance_score = 1.0 if dominant <= 0.75 else max(0.0, 1.0 - (dominant - 0.75) / 0.25)
        else:
            balance_score = 1.0

        warnings_penalty = min(0.4, len(result.warnings) * 0.05)
        score = max(0.0, ((required_present + balance_score) / 2) - warnings_penalty)
        passed = score >= float(expected_snapshot.get("min_section_sanity", 0.6))
        details = (
            f"required_present={required_present:.2f}, "
            f"experience_bullets={experience_bullets}, "
            f"project_bullets={project_bullets}, "
            f"warnings={len(result.warnings)}"
        )
        return _MetricDecision(round(score, 4), passed, details)

    def _score_faithfulness(
        self,
        verification_output: VerifyGeneratedContentOutput | None,
    ) -> _MetricDecision:
        if verification_output is None:
            return _MetricDecision(0.0, False, "verification output missing")

        report = verification_output.verification_report
        weighted_risk = 0.0
        unsupported_issue_count = 0
        for issue in [*report.issues, *[item_issue for item in report.item_results for item_issue in item.issues]]:
            severity_weight = {
                IssueSeverity.INFO: 0.02,
                IssueSeverity.LOW: 0.05,
                IssueSeverity.MEDIUM: 0.12,
                IssueSeverity.HIGH: 0.28,
                IssueSeverity.CRITICAL: 0.45,
            }[issue.severity]
            weighted_risk += severity_weight
            if issue.category.name.startswith("UNSUPPORTED") or issue.category in {
                IssueCategory.PROVENANCE_MISSING,
                IssueCategory.PROVENANCE_WEAK,
                IssueCategory.CONTENT_DRIFT,
            }:
                unsupported_issue_count += 1
        if report.status in {VerificationStatus.FAILED, VerificationStatus.BLOCKED}:
            weighted_risk += 0.35
        score = max(0.0, 1.0 - min(weighted_risk, 1.0))
        passed = unsupported_issue_count == 0 and report.status not in {VerificationStatus.FAILED, VerificationStatus.BLOCKED}
        details = (
            f"verification_status={report.status.value}, "
            f"unsupported_risk_weight={weighted_risk:.2f}, "
            f"issue_count={len(report.issues) + sum(len(item.issues) for item in report.item_results)}"
        )
        return _MetricDecision(round(score, 4), passed, details)

    def _score_omissions(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        if generation_output is None:
            return _MetricDecision(0.0, False, "generation output missing")

        result = generation_output.phase3_result
        selected_ids = {
            *[item.source_item_id for item in result.selected_experiences],
            *[item.source_item_id for item in result.selected_projects],
        }
        omitted_ids = {item.source_item_id for item in result.omitted_items}
        required_selected = set(expected_snapshot.get("expected_selected_source_ids", []))
        required_omitted = set(expected_snapshot.get("expected_omitted_source_ids", []))
        missing_required_selected = sorted(item for item in required_selected if item not in selected_ids)
        missing_required_omitted = sorted(item for item in required_omitted if item not in omitted_ids)

        score_parts: list[float] = []
        if required_selected:
            score_parts.append(1.0 - (len(missing_required_selected) / len(required_selected)))
        if required_omitted:
            score_parts.append(1.0 - (len(missing_required_omitted) / len(required_omitted)))
        if not score_parts:
            score_parts.append(1.0 if result.omitted_items or result.metadata.omitted_item_count == 0 else 0.8)
        score = max(0.0, sum(score_parts) / len(score_parts))
        passed = not missing_required_selected and not missing_required_omitted
        details = (
            f"selected_missing={missing_required_selected or 'none'}, "
            f"omitted_missing={missing_required_omitted or 'none'}, "
            f"omitted_count={len(result.omitted_items)}"
        )
        return _MetricDecision(round(score, 4), passed, details)

    def _score_verification_behavior(
        self,
        verification_output: VerifyGeneratedContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        if verification_output is None:
            return _MetricDecision(0.0, False, "verification output missing")

        report = verification_output.verification_report
        expected_status = expected_snapshot.get("expected_verification_status")
        expected_categories = set(expected_snapshot.get("expected_verification_issue_categories", []))
        actual_categories = {
            issue.category.value
            for issue in [*report.issues, *[item_issue for item in report.item_results for item_issue in item.issues]]
        }
        status_match = expected_status is None or report.status.value == expected_status
        categories_match = not expected_categories or expected_categories <= actual_categories
        max_issue_count = expected_snapshot.get("max_verification_issue_count")
        issue_count = len(report.issues) + sum(len(item.issues) for item in report.item_results)
        issue_count_ok = max_issue_count is None or issue_count <= int(max_issue_count)

        score = _average(
            1.0 if status_match else 0.0,
            1.0 if categories_match else 0.0,
            1.0 if issue_count_ok else 0.0,
        )
        passed = status_match and categories_match and issue_count_ok
        details = (
            f"status={report.status.value}, "
            f"decision={report.decision_outcome.value}, "
            f"issue_count={issue_count}, "
            f"renderable={report.renderable}"
        )
        return _MetricDecision(round(score, 4), passed, details)

    def _score_completeness(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        verification_output: VerifyGeneratedContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        if generation_output is None:
            return _MetricDecision(0.0, False, "generation output missing")

        result = (
            verification_output.rendering_output.verified_result
            if verification_output is not None
            else generation_output.phase3_result
        )
        checks = [
            (not expected_snapshot.get("require_headline", False)) or result.headline is not None,
            (not expected_snapshot.get("require_summary", True)) or result.summary is not None,
            len(result.selected_experiences) >= int(expected_snapshot.get("min_experience_count", 1)),
            len(result.skills_to_highlight) >= int(expected_snapshot.get("min_skill_count", 1)),
        ]
        required_projects = expected_snapshot.get("require_projects_section")
        if required_projects is not None:
            checks.append(bool(result.selected_projects) == bool(required_projects))
        score = sum(1.0 for check in checks if check) / len(checks)
        passed = all(checks)
        details = (
            f"headline={result.headline is not None}, "
            f"summary={result.summary is not None}, "
            f"experiences={len(result.selected_experiences)}, "
            f"projects={len(result.selected_projects)}, "
            f"skills={len(result.skills_to_highlight)}"
        )
        return _MetricDecision(round(score, 4), passed, details)

    def _score_render(
        self,
        compile_output: CompilePdfOutput | None,
        expected_snapshot: dict[str, Any],
        stage_map: dict[StageName, Any],
    ) -> _MetricDecision:
        require_render = bool(expected_snapshot.get("require_render_success", False))
        render_stage_seen = StageName.COMPILE_PDF in stage_map or StageName.RENDER_DETERMINISTIC_LATEX in stage_map
        if not require_render and not render_stage_seen:
            return _MetricDecision(1.0, True, "render not requested")
        if compile_output is None:
            return _MetricDecision(0.0, not require_render, "compile stage missing")
        success = compile_output.compile_result.compile_success
        details = (
            f"compile_success={success}, "
            f"return_code={compile_output.compile_result.return_code}, "
            f"warnings={len(compile_output.compile_result.warnings_detected)}, "
            f"errors={len(compile_output.compile_result.errors_detected)}"
        )
        return _MetricDecision(1.0 if success else 0.0, success or not require_render, details)

    def _build_reviewer_signals(
        self,
        *,
        generation_output: GenerateStructuredContentOutput | None,
        verification_output: VerifyGeneratedContentOutput | None,
        expected_snapshot: dict[str, Any],
        summary_metric: _MetricDecision,
        section_metric: _MetricDecision,
        omission_metric: _MetricDecision,
    ) -> list[ReviewerSignal]:
        weak_summary = False
        keyword_stuffing = False
        low_confidence_fit = False
        if generation_output is not None and generation_output.phase3_result.summary is not None:
            summary_assessment = assess_summary(
                generation_output.generation_payload,
                generation_output.phase3_result.summary.text,
            )
            weak_summary = summary_assessment.quality_score < 0.6 or any(
                issue.issue_type in {HeadlineSummaryIssueType.FILLER_LANGUAGE, HeadlineSummaryIssueType.WEAK_ALIGNMENT}
                for issue in summary_assessment.issues
            )
            keyword_stuffing = any(
                issue.issue_type == HeadlineSummaryIssueType.KEYWORD_STUFFING
                for issue in summary_assessment.issues
            )
            confidence_values = [
                item
                for item in [
                    generation_output.phase3_result.summary.confidence_score,
                    generation_output.phase3_result.headline.confidence_score if generation_output.phase3_result.headline is not None else None,
                    *[bullet.confidence_score for experience in generation_output.phase3_result.selected_experiences for bullet in experience.generated_bullets],
                    *[bullet.confidence_score for project in generation_output.phase3_result.selected_projects for bullet in project.generated_bullets],
                ]
                if item is not None
            ]
            avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else None
            low_confidence_fit = avg_confidence is not None and avg_confidence < float(expected_snapshot.get("min_fit_confidence", 0.6))

        unsupported_claim_risk = False
        if verification_output is not None:
            report = verification_output.verification_report
            unsupported_categories = {
                IssueCategory.UNSUPPORTED_METRIC,
                IssueCategory.UNSUPPORTED_TOOL,
                IssueCategory.UNSUPPORTED_SCOPE,
                IssueCategory.UNSUPPORTED_LEADERSHIP,
                IssueCategory.UNSUPPORTED_KEYWORD,
                IssueCategory.UNSUPPORTED_CLAIM,
                IssueCategory.UNSUPPORTED_DOMAIN,
                IssueCategory.UNSUPPORTED_YEARS_EXPERIENCE,
                IssueCategory.PROVENANCE_MISSING,
                IssueCategory.PROVENANCE_WEAK,
            }
            unsupported_claim_risk = any(
                issue.category in unsupported_categories and issue.severity in {IssueSeverity.MEDIUM, IssueSeverity.HIGH, IssueSeverity.CRITICAL}
                for issue in [*report.issues, *[item_issue for item in report.item_results for item_issue in item.issues]]
            )

        suspicious_omissions = not omission_metric.passed
        section_imbalance = not section_metric.passed

        return [
            ReviewerSignal(
                signal_name="weak_summary",
                triggered=weak_summary,
                severity="warning",
                details=summary_metric.details if weak_summary else None,
            ),
            ReviewerSignal(
                signal_name="keyword_stuffing_signs",
                triggered=keyword_stuffing,
                severity="warning",
                details="Summary or headline repeated role/skill terms too aggressively." if keyword_stuffing else None,
            ),
            ReviewerSignal(
                signal_name="unsupported_claim_risk",
                triggered=unsupported_claim_risk,
                severity="error",
                details="Verification flagged unsupported or weakly supported claims." if unsupported_claim_risk else None,
            ),
            ReviewerSignal(
                signal_name="section_imbalance",
                triggered=section_imbalance,
                severity="warning",
                details=section_metric.details if section_imbalance else None,
            ),
            ReviewerSignal(
                signal_name="suspicious_omissions",
                triggered=suspicious_omissions,
                severity="warning",
                details=omission_metric.details if suspicious_omissions else None,
            ),
            ReviewerSignal(
                signal_name="low_confidence_fit",
                triggered=low_confidence_fit,
                severity="warning",
                details="Generated fit signals were low-confidence and should be reviewed manually." if low_confidence_fit else None,
            ),
        ]

    def _build_reviewer_comments(
        self,
        case: EvaluationCaseDefinition,
        reviewer_signals: list[ReviewerSignal],
        artifact_paths: dict[str, str],
    ) -> list[str]:
        comments = list(case.expected_outputs.reviewer_guidance)
        for signal in reviewer_signals:
            if not signal.triggered:
                continue
            comments.append(f"Review {signal.signal_name.replace('_', ' ')}: {signal.details or 'check linked artifacts.'}")
        if "phase3_result" in artifact_paths:
            comments.append(f"Inspect generated structured output at {artifact_paths['phase3_result']}")
        if "verification_report" in artifact_paths:
            comments.append(f"Inspect verifier output at {artifact_paths['verification_report']}")
        if "pdf" in artifact_paths:
            comments.append(f"Inspect rendered PDF at {artifact_paths['pdf']}")
        return comments


class RedTeamQualityScorer:
    """Pessimistic scorer for adversarial and brittle pipeline behavior."""

    def __init__(self) -> None:
        self._fallback = BasicExpectationScorer()

    def score_case(
        self,
        case: EvaluationCaseDefinition,
        actual_outputs: EvaluationActualOutputs,
        artifact_manifest: ArtifactManifest,
    ) -> ScoringSummary:
        if case.metadata.pack_type is not EvaluationPackType.RED_TEAM:
            return self._fallback.score_case(case, actual_outputs, artifact_manifest)

        expected_snapshot = case.expected_outputs.expected_output_snapshot
        stage_map = {stage.stage_name: stage for stage in actual_outputs.stage_outputs}
        artifact_paths = _artifact_paths(artifact_manifest)

        ranking_output = _parse_stage_output(stage_map.get(StageName.RANK_SELECT_EVIDENCE), RankSelectEvidenceOutput)
        generation_output = _parse_stage_output(stage_map.get(StageName.GENERATE_STRUCTURED_CONTENT), GenerateStructuredContentOutput)
        verification_output = _parse_stage_output(stage_map.get(StageName.VERIFY_GENERATED_CONTENT), VerifyGeneratedContentOutput)

        overclaim = self._score_overclaim_risk(generation_output, verification_output, expected_snapshot)
        weak_fit = self._score_weak_fit_honesty(generation_output, verification_output, expected_snapshot)
        collapse = self._score_ranking_collapse(ranking_output, generation_output, expected_snapshot)
        dominance = self._score_one_source_dominance(ranking_output, generation_output, expected_snapshot)
        keyword_chasing = self._score_irrelevant_keyword_chasing(generation_output, expected_snapshot)
        summary_inflation = self._score_unsafe_summary_inflation(generation_output, verification_output, expected_snapshot)

        metrics = [
            ScoringMetric(metric_name="overclaim_risk", score=overclaim.score, passed=overclaim.passed, details=overclaim.details),
            ScoringMetric(metric_name="weak_fit_honesty", score=weak_fit.score, passed=weak_fit.passed, details=weak_fit.details),
            ScoringMetric(metric_name="ranking_collapse", score=collapse.score, passed=collapse.passed, details=collapse.details),
            ScoringMetric(metric_name="one_source_dominance", score=dominance.score, passed=dominance.passed, details=dominance.details),
            ScoringMetric(metric_name="irrelevant_keyword_chasing", score=keyword_chasing.score, passed=keyword_chasing.passed, details=keyword_chasing.details),
            ScoringMetric(metric_name="unsafe_summary_inflation", score=summary_inflation.score, passed=summary_inflation.passed, details=summary_inflation.details),
        ]
        reviewer_signals = [
            ReviewerSignal(signal_name="overclaim_risk", triggered=not overclaim.passed, severity="error", details=overclaim.details if not overclaim.passed else None),
            ReviewerSignal(signal_name="weak_fit_honesty", triggered=not weak_fit.passed, severity="warning", details=weak_fit.details if not weak_fit.passed else None),
            ReviewerSignal(signal_name="ranking_collapse", triggered=not collapse.passed, severity="warning", details=collapse.details if not collapse.passed else None),
            ReviewerSignal(signal_name="one_source_dominance", triggered=not dominance.passed, severity="warning", details=dominance.details if not dominance.passed else None),
            ReviewerSignal(signal_name="irrelevant_keyword_chasing", triggered=not keyword_chasing.passed, severity="error", details=keyword_chasing.details if not keyword_chasing.passed else None),
            ReviewerSignal(signal_name="unsafe_summary_inflation", triggered=not summary_inflation.passed, severity="error", details=summary_inflation.details if not summary_inflation.passed else None),
        ]
        findings = [metric.details for metric in metrics if not metric.passed and metric.details]
        reviewer_comments = []
        if case.expected_outputs.bad_behavior_to_catch is not None:
            reviewer_comments.append(f"Bad behavior target: {case.expected_outputs.bad_behavior_to_catch}")
        if case.expected_outputs.acceptable_fallback_behavior is not None:
            reviewer_comments.append(f"Acceptable fallback: {case.expected_outputs.acceptable_fallback_behavior}")
        reviewer_comments.extend(case.expected_outputs.reviewer_guidance)
        if "selection_output" in artifact_paths:
            reviewer_comments.append(f"Inspect selection artifact at {artifact_paths['selection_output']}")
        if "phase3_result" in artifact_paths:
            reviewer_comments.append(f"Inspect generated structured output at {artifact_paths['phase3_result']}")
        if "verification_report" in artifact_paths:
            reviewer_comments.append(f"Inspect verifier output at {artifact_paths['verification_report']}")

        overall_score = round(sum(metric.score for metric in metrics) / len(metrics), 4) if metrics else 0.0
        outcome = ScoringOutcome.PASS if all(metric.passed for metric in metrics) else ScoringOutcome.FAIL
        return ScoringSummary(
            run_id=actual_outputs.run_id,
            case_id=actual_outputs.case_id,
            scorer_name="red_team_quality_scorer",
            outcome=outcome,
            overall_score=overall_score,
            metrics=metrics,
            findings=findings,
            reviewer_signals=reviewer_signals,
            reviewer_comments=reviewer_comments,
            artifact_paths=artifact_paths,
        )

    def _score_overclaim_risk(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        verification_output: VerifyGeneratedContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        expected_categories = set(expected_snapshot.get("expected_verification_issue_categories", []))
        selected_ids = _selected_source_ids(generation_output)
        risky_ids = set(expected_snapshot.get("risky_source_item_ids", []))
        risky_selected = sorted(risky_ids & selected_ids)
        if verification_output is None:
            return _MetricDecision(0.0, False, "verification output missing")
        issue_categories = _verification_issue_categories(verification_output)
        unsupported_count = len(issue_categories & {category.value for category in _unsupported_categories()})
        expected_hit = not expected_categories or expected_categories <= issue_categories
        passed = not risky_selected and expected_hit
        if not passed and unsupported_count == 0 and expected_categories:
            details = f"expected_issue_categories={sorted(expected_categories)}, actual_categories={sorted(issue_categories) or 'none'}, risky_selected={risky_selected or 'none'}"
            return _MetricDecision(0.0, False, details)
        score = 1.0 if passed else max(0.0, 0.6 - (0.25 * len(risky_selected)))
        details = f"expected_issue_categories={sorted(expected_categories) or 'none'}, actual_categories={sorted(issue_categories) or 'none'}, risky_selected={risky_selected or 'none'}"
        return _MetricDecision(round(score, 4), passed, details)

    def _score_weak_fit_honesty(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        verification_output: VerifyGeneratedContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        if not expected_snapshot.get("expect_low_fit", False):
            return _MetricDecision(1.0, True, "case does not require weak-fit caution")
        if generation_output is None:
            return _MetricDecision(0.0, False, "generation output missing")
        confidence_values = _confidence_values(generation_output)
        avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 1.0
        omitted_count = len(generation_output.phase3_result.omitted_items)
        max_confidence = float(expected_snapshot.get("max_avg_confidence_for_weak_fit", 0.72))
        verification_status = verification_output.verification_report.status.value if verification_output is not None else "missing"
        passed = avg_confidence <= max_confidence or omitted_count > 0 or verification_status != "passed"
        score = 1.0 if passed else max(0.0, 1.0 - avg_confidence)
        details = f"avg_confidence={avg_confidence:.2f}, omitted_count={omitted_count}, verification_status={verification_status}"
        return _MetricDecision(round(score, 4), passed, details)

    def _score_ranking_collapse(
        self,
        ranking_output: RankSelectEvidenceOutput | None,
        generation_output: GenerateStructuredContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        min_distinct = int(expected_snapshot.get("min_distinct_selected_sources", 2))
        selected_ids = _selected_source_ids(generation_output)
        if ranking_output is not None and not selected_ids:
            selected_ids = {
                *[item.source_item_id for item in ranking_output.selection_result.selected_experiences],
                *[item.source_item_id for item in ranking_output.selection_result.selected_projects],
            }
        diagnostics = ranking_output.selection_result.diagnostics if ranking_output is not None else None
        weak_coverage = list(diagnostics.weak_coverage_areas) if diagnostics is not None else []
        distinct_count = len(selected_ids)
        passed = distinct_count >= min_distinct and not (distinct_count <= 1 and weak_coverage)
        score = min(1.0, distinct_count / max(1, min_distinct))
        details = f"distinct_selected_sources={distinct_count}, weak_coverage_areas={weak_coverage or 'none'}"
        return _MetricDecision(round(score, 4), passed, details)

    def _score_one_source_dominance(
        self,
        ranking_output: RankSelectEvidenceOutput | None,
        generation_output: GenerateStructuredContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        max_share = float(expected_snapshot.get("max_single_source_bullet_share", 0.7))
        source_counts = _source_bullet_counts(generation_output, ranking_output)
        total = sum(source_counts.values())
        dominant_share = (max(source_counts.values()) / total) if total else 1.0
        passed = total > 0 and dominant_share <= max_share
        details = f"dominant_share={dominant_share:.2f}, source_bullet_counts={dict(source_counts) or 'none'}"
        score = 1.0 if passed else max(0.0, 1.0 - dominant_share)
        return _MetricDecision(round(score, 4), passed, details)

    def _score_irrelevant_keyword_chasing(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        forbidden_ids = set(expected_snapshot.get("forbidden_source_item_ids", []))
        selected_ids = _selected_source_ids(generation_output)
        chased = sorted(forbidden_ids & selected_ids)
        passed = not chased
        score = 1.0 if passed else max(0.0, 1.0 - (len(chased) / max(1, len(forbidden_ids))))
        details = f"forbidden_selected={chased or 'none'}, selected_sources={sorted(selected_ids) or 'none'}"
        return _MetricDecision(round(score, 4), passed, details)

    def _score_unsafe_summary_inflation(
        self,
        generation_output: GenerateStructuredContentOutput | None,
        verification_output: VerifyGeneratedContentOutput | None,
        expected_snapshot: dict[str, Any],
    ) -> _MetricDecision:
        if generation_output is None or generation_output.phase3_result.summary is None:
            return _MetricDecision(0.0, False, "missing summary")
        summary = generation_output.phase3_result.summary
        assessment = assess_summary(generation_output.generation_payload, summary.text)
        issue_types = {issue.issue_type for issue in assessment.issues}
        avg_confidence = sum(_confidence_values(generation_output)) / max(1, len(_confidence_values(generation_output)))
        low_fit = bool(expected_snapshot.get("expect_low_fit", False))
        unsafe = (
            HeadlineSummaryIssueType.KEYWORD_STUFFING in issue_types
            or assessment.hard_fail
            or (low_fit and avg_confidence > float(expected_snapshot.get("max_avg_confidence_for_weak_fit", 0.72)))
            or (
                verification_output is not None
                and bool(_verification_issue_categories(verification_output) & {category.value for category in _unsupported_categories()})
                and avg_confidence > 0.75
            )
        )
        passed = not unsafe
        score = 1.0 if passed else max(0.0, assessment.quality_score - 0.4)
        details = f"summary_quality={assessment.quality_score:.2f}, issue_types={sorted(issue_types) or 'none'}, avg_confidence={avg_confidence:.2f}, summary_words={len(summary.text.split())}"
        return _MetricDecision(round(score, 4), passed, details)


def _resolve_outcome(
    *,
    metrics: list[ScoringMetric],
    reviewer_signals: list[ReviewerSignal],
    pipeline_status: PipelineStatus,
    verification_output: VerifyGeneratedContentOutput | None,
    require_render_success: bool,
) -> ScoringOutcome:
    failed_metric_names = {metric.metric_name for metric in metrics if not metric.passed}
    if pipeline_status in {PipelineStatus.FAILED, PipelineStatus.BLOCKED}:
        return ScoringOutcome.FAIL
    if verification_output is not None and verification_output.verification_report.status in {
        VerificationStatus.FAILED,
        VerificationStatus.BLOCKED,
    }:
        return ScoringOutcome.FAIL
    if "selected_content_faithfulness" in failed_metric_names or "final_output_completeness" in failed_metric_names:
        return ScoringOutcome.FAIL
    if require_render_success and "render_success" in failed_metric_names:
        return ScoringOutcome.FAIL
    if failed_metric_names or any(signal.triggered for signal in reviewer_signals):
        return ScoringOutcome.REVIEW
    return ScoringOutcome.PASS


def _artifact_paths(artifact_manifest: ArtifactManifest) -> dict[str, str]:
    paths: dict[str, str] = {}
    kind_aliases = {
        ArtifactKind.PHASE2_SELECTION: "selection_output",
        ArtifactKind.PHASE3_RESULT: "phase3_result",
        ArtifactKind.VERIFICATION_REPORT: "verification_report",
        ArtifactKind.RENDERING_GATE: "rendering_output",
        ArtifactKind.PDF: "pdf",
        ArtifactKind.COMPILE_LOG: "compile_log",
        ArtifactKind.LATEX_DOCUMENT: "latex_document",
    }
    for entry in artifact_manifest.entries:
        alias = kind_aliases.get(entry.artifact_kind)
        if alias is not None and alias not in paths:
            paths[alias] = entry.storage_path
    return paths


def _parse_stage_output(stage_output: Any, model_cls):
    if stage_output is None or stage_output.status != StageStatus.SUCCEEDED:
        return None
    snapshot = stage_output.output_snapshot or {}
    try:
        return model_cls.model_validate(snapshot)
    except Exception:
        return None


def _average(*values: float) -> float:
    return sum(values) / len(values) if values else 0.0


def _unsupported_categories() -> set[IssueCategory]:
    return {
        IssueCategory.UNSUPPORTED_METRIC,
        IssueCategory.UNSUPPORTED_TOOL,
        IssueCategory.UNSUPPORTED_SCOPE,
        IssueCategory.UNSUPPORTED_LEADERSHIP,
        IssueCategory.UNSUPPORTED_KEYWORD,
        IssueCategory.UNSUPPORTED_CLAIM,
        IssueCategory.UNSUPPORTED_DOMAIN,
        IssueCategory.UNSUPPORTED_YEARS_EXPERIENCE,
        IssueCategory.PROVENANCE_MISSING,
        IssueCategory.PROVENANCE_WEAK,
    }


def _verification_issue_categories(verification_output: VerifyGeneratedContentOutput) -> set[str]:
    return {
        issue.category.value
        for issue in [
            *verification_output.verification_report.issues,
            *[item_issue for item in verification_output.verification_report.item_results for item_issue in item.issues],
        ]
    }


def _selected_source_ids(generation_output: GenerateStructuredContentOutput | None) -> set[str]:
    if generation_output is None:
        return set()
    return {
        *[item.source_item_id for item in generation_output.phase3_result.selected_experiences],
        *[item.source_item_id for item in generation_output.phase3_result.selected_projects],
    }


def _confidence_values(generation_output: GenerateStructuredContentOutput) -> list[float]:
    return [
        value
        for value in [
            generation_output.phase3_result.summary.confidence_score if generation_output.phase3_result.summary is not None else None,
            generation_output.phase3_result.headline.confidence_score if generation_output.phase3_result.headline is not None else None,
            *[
                bullet.confidence_score
                for experience in generation_output.phase3_result.selected_experiences
                for bullet in experience.generated_bullets
            ],
            *[
                bullet.confidence_score
                for project in generation_output.phase3_result.selected_projects
                for bullet in project.generated_bullets
            ],
        ]
        if value is not None
    ]


def _source_bullet_counts(
    generation_output: GenerateStructuredContentOutput | None,
    ranking_output: RankSelectEvidenceOutput | None,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    if generation_output is not None:
        for experience in generation_output.phase3_result.selected_experiences:
            counts[experience.source_item_id] += len(experience.generated_bullets)
        for project in generation_output.phase3_result.selected_projects:
            counts[project.source_item_id] += len(project.generated_bullets)
        if counts:
            return counts
    if ranking_output is not None:
        for experience in ranking_output.selection_result.selected_experiences:
            counts[experience.source_item_id] += len(experience.selected_bullet_ids)
        for project in ranking_output.selection_result.selected_projects:
            counts[project.source_item_id] += len(project.selected_bullet_ids)
    return counts
