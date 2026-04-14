"""Workflow helpers for integrating Phase 7 into local and CI loops."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import json
from typing import Any

from src.resume_optimizer.evaluation.jd_parse_runner import JDParseSummary
from src.resume_optimizer.evaluation.selection_runner import SelectionSummary


DEFAULT_PHASE7_THRESHOLD_PATH = Path("fixtures/evaluation/phase7_thresholds.json").resolve()
_LOWER_IS_BETTER_SELECTION_METRICS = {"pathology_rate"}


@dataclass
class WorkflowCheckResult:
    name: str
    status: str
    confidence_level: str
    message: str
    findings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    artifact_paths: dict[str, str] = field(default_factory=dict)


def load_phase7_thresholds(path: Path | None = None) -> dict[str, Any]:
    threshold_path = path or DEFAULT_PHASE7_THRESHOLD_PATH
    return json.loads(threshold_path.read_text(encoding="utf-8"))


def evaluate_selection_ci(summary: SelectionSummary, thresholds: dict[str, Any]) -> WorkflowCheckResult:
    regression_config = thresholds.get("regression_guardrail", {})
    absolute_quality = thresholds.get("absolute_quality", {})
    baseline = regression_config.get("baseline", thresholds.get("baseline", {}))
    max_regression = float(regression_config.get("max_metric_regression", thresholds.get("max_metric_regression", 0.03)))
    min_total_cases = int(thresholds.get("min_total_cases", 1))
    findings: list[str] = []
    regression_findings: list[str] = []
    quality_findings: list[str] = []
    pass_rate = summary.passed_cases / max(1, summary.total_cases)
    avg_selection_relevance = round(
        sum(case.average_selection_relevance for case in summary.case_results) / max(1, len(summary.case_results)),
        4,
    )
    metrics = {
        "pass_rate": round(pass_rate, 4),
        "avg_experience_precision": round(summary.avg_experience_precision, 4),
        "avg_experience_recall": round(summary.avg_experience_recall, 4),
        "avg_project_precision": round(summary.avg_project_precision, 4),
        "avg_project_recall": round(summary.avg_project_recall, 4),
        "avg_bullet_precision": round(summary.avg_bullet_precision, 4),
        "avg_bullet_recall": round(summary.avg_bullet_recall, 4),
        "avg_skill_correctness": round(summary.avg_skill_correctness, 4),
        "avg_diversity_balance": round(summary.avg_diversity_balance, 4),
        "pathology_rate": round(summary.pathology_rate, 4),
        "avg_selection_relevance": avg_selection_relevance,
        "avg_overall_score": round(
            sum(case.overall_score for case in summary.case_results) / max(1, len(summary.case_results)),
            4,
        ),
    }

    if summary.total_cases < min_total_cases:
        quality_findings.append(f"selection cases below minimum: {summary.total_cases} < {min_total_cases}")
    if summary.passed_cases <= 0:
        quality_findings.append("absolute quality failure: all selection cases failed")
    if pass_rate < float(absolute_quality.get("min_pass_rate", 0.0)):
        quality_findings.append(
            f"absolute quality failure: pass_rate below threshold: {pass_rate:.4f} < {float(absolute_quality.get('min_pass_rate', 0.0)):.4f}"
        )
    if summary.pathology_rate > float(absolute_quality.get("max_pathology_rate", 1.0)):
        quality_findings.append(
            f"absolute quality failure: pathology_rate above threshold: {summary.pathology_rate:.4f} > {float(absolute_quality.get('max_pathology_rate', 1.0)):.4f}"
        )
    if metrics["avg_project_recall"] < float(absolute_quality.get("min_avg_project_recall", 0.0)):
        quality_findings.append(
            f"absolute quality failure: avg_project_recall below threshold: {metrics['avg_project_recall']:.4f} < {float(absolute_quality.get('min_avg_project_recall', 0.0)):.4f}"
        )
    if metrics["avg_selection_relevance"] < float(absolute_quality.get("min_avg_selection_relevance", 0.0)):
        quality_findings.append(
            f"absolute quality failure: avg_selection_relevance below threshold: {metrics['avg_selection_relevance']:.4f} < {float(absolute_quality.get('min_avg_selection_relevance', 0.0)):.4f}"
        )
    if metrics["avg_overall_score"] < float(absolute_quality.get("min_avg_overall_score", 0.0)):
        quality_findings.append(
            f"absolute quality failure: avg_overall_score below threshold: {metrics['avg_overall_score']:.4f} < {float(absolute_quality.get('min_avg_overall_score', 0.0)):.4f}"
        )
    if _has_zero_required_project_recall(summary):
        quality_findings.append(
            "absolute quality failure: at least one case required projects but achieved zero project recall"
        )

    for metric_name, baseline_value in baseline.items():
        current = metrics.get(metric_name)
        if current is None:
            continue
        baseline_float = float(baseline_value)
        if metric_name in _LOWER_IS_BETTER_SELECTION_METRICS:
            regressed = current > baseline_float + max_regression
        else:
            regressed = current < baseline_float - max_regression
        if regressed:
            regression_findings.append(
                f"regression guardrail failure: {metric_name} regressed from baseline: current={current:.4f} baseline={baseline_float:.4f} tolerance={max_regression:.4f}"
            )

    findings.extend(quality_findings)
    findings.extend(regression_findings)
    absolute_quality_pass = not quality_findings
    regression_guardrail_pass = not regression_findings
    status = "pass" if absolute_quality_pass and regression_guardrail_pass else "fail"
    message = (
        "selection quality gate passed: absolute quality and regression guardrail both passed"
        if status == "pass"
        else "selection quality gate failed"
    )
    metrics["absolute_quality_pass"] = 1.0 if absolute_quality_pass else 0.0
    metrics["regression_guardrail_pass"] = 1.0 if regression_guardrail_pass else 0.0
    return WorkflowCheckResult(
        name="selection",
        status=status,
        confidence_level="quality",
        message=message,
        findings=findings,
        metrics=metrics,
    )


def _has_zero_required_project_recall(summary: SelectionSummary) -> bool:
    for case in summary.case_results:
        project_score = case.project_score
        if project_score is None:
            continue
        requires_project = any(
            assessment.required
            for assessment in project_score.positive_assessments
        )
        if requires_project and case.project_recall <= 0.0:
            return True
    return False


def evaluate_jd_parse_live(summary: JDParseSummary, thresholds: dict[str, Any]) -> WorkflowCheckResult:
    pass_rate = summary.passed_cases / max(1, summary.total_cases)
    findings: list[str] = []
    metrics = {
        "pass_rate": round(pass_rate, 4),
        "title_accuracy": round(summary.title_accuracy, 4),
        "must_have_skill_recall": round(summary.must_have_skill_recall, 4),
        "responsibility_recall": round(summary.responsibility_recall, 4),
        "average_confidence": round(summary.average_confidence, 4),
    }
    if pass_rate < float(thresholds.get("min_pass_rate", 0.0)):
        findings.append(f"pass_rate below threshold: {pass_rate:.4f}")
    if summary.must_have_skill_recall < float(thresholds.get("min_must_have_skill_recall", 0.0)):
        findings.append(f"must_have_skill_recall below threshold: {summary.must_have_skill_recall:.4f}")
    if summary.responsibility_recall < float(thresholds.get("min_responsibility_recall", 0.0)):
        findings.append(f"responsibility_recall below threshold: {summary.responsibility_recall:.4f}")
    return WorkflowCheckResult(
        name="jd_parse",
        status="pass" if not findings else "fail",
        confidence_level="quality",
        message="jd_parse live evaluation passed" if not findings else "jd_parse live evaluation failed",
        findings=findings,
        metrics=metrics,
    )


def evaluate_backend_live(
    *,
    name: str,
    aggregate_payload: dict[str, Any],
    thresholds: dict[str, Any],
) -> WorkflowCheckResult:
    fail_count = int(aggregate_payload.get("outcomes", {}).get("fail", 0))
    review_count = int(aggregate_payload.get("outcomes", {}).get("review", 0))
    findings: list[str] = []
    if fail_count > int(thresholds.get("max_fail_count", 0)):
        findings.append(f"{name} fail_count above threshold: {fail_count}")
    if review_count > int(thresholds.get("max_review_count", review_count)):
        findings.append(f"{name} review_count above threshold: {review_count}")
    return WorkflowCheckResult(
        name=name,
        status="pass" if not findings else "fail",
        confidence_level="quality",
        message=f"{name} live evaluation {'passed' if not findings else 'failed'}",
        findings=findings,
        metrics={
            "total_cases": float(aggregate_payload.get("total_cases", 0)),
            "fail_count": float(fail_count),
            "review_count": float(review_count),
        },
    )


def build_suite_report(
    *,
    mode: str,
    command: str,
    checks: list[WorkflowCheckResult],
) -> dict[str, Any]:
    outcomes = {
        "pass": sum(1 for check in checks if check.status == "pass"),
        "fail": sum(1 for check in checks if check.status == "fail"),
        "skip": sum(1 for check in checks if check.status == "skip"),
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "command": command,
        "outcomes": outcomes,
        "checks": [asdict(check) for check in checks],
    }


def render_suite_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 7 Workflow Summary",
        "",
        f"- Generated At: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Command: `{report['command']}`",
        f"- Pass/Fail/Skip: `{report['outcomes']['pass']}/{report['outcomes']['fail']}/{report['outcomes']['skip']}`",
        "",
        "## Checks",
    ]
    for check in report["checks"]:
        lines.append(
            f"- `{check['name']}` status=`{check['status']}` confidence=`{check['confidence_level']}` {check['message']}"
        )
        for finding in check.get("findings", []):
            lines.append(f"  finding: {finding}")
        for name, path in sorted(check.get("artifact_paths", {}).items()):
            lines.append(f"  artifact: {name}={path}")
    lines.extend(
        [
            "",
            "## Confidence Model",
            "- `quality` means the result contributes to product-confidence gating.",
            "- In `ci-safe`, the `selection` check passes only when both absolute quality and regression guardrails pass; stable bad behavior is still a failure.",
            "- `smoke` means the path exercised artifact/log generation only and does not prove live quality.",
            "- `skip` means the pack was not run in this mode, typically because live model access was intentionally disabled.",
        ]
    )
    return "\n".join(lines) + "\n"
