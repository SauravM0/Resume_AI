"""Concrete report writing for real evaluation runs."""

from __future__ import annotations

from pathlib import Path
import json

from backend.app.evaluation.aggregate_reporting import (
    build_aggregate_json_report,
    render_aggregate_markdown_report,
    render_case_metrics_csv,
    render_compact_terminal_summary,
)
from backend.app.evaluation.artifact_models import ArtifactManifest
from backend.app.evaluation.case_models import EvaluationCaseDefinition
from backend.app.evaluation.contracts import EvaluationReportWriter
from backend.app.evaluation.report_models import RunSummary, ScoringSummary


class MarkdownJsonEvaluationReportWriter(EvaluationReportWriter):
    """Write both machine-readable JSON and reviewer-friendly markdown reports."""

    def write_case_report(
        self,
        *,
        case: EvaluationCaseDefinition,
        run_summary: RunSummary,
        scoring_summary: ScoringSummary,
        artifact_manifest: ArtifactManifest,
        output_root: Path,
    ) -> Path:
        output_root.mkdir(parents=True, exist_ok=True)
        json_path = output_root / "report.json"
        markdown_path = output_root / "report.md"

        payload = {
            "case": case.model_dump(mode="json", exclude_none=True),
            "run_summary": run_summary.model_dump(mode="json", exclude_none=True),
            "scoring_summary": scoring_summary.model_dump(mode="json", exclude_none=True),
            "artifact_manifest": artifact_manifest.model_dump(mode="json", exclude_none=True),
        }
        json_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        markdown_path.write_text(
            render_case_markdown_report(
                case=case,
                run_summary=run_summary,
                scoring_summary=scoring_summary,
                artifact_manifest=artifact_manifest,
            ),
            encoding="utf-8",
        )
        return markdown_path


JsonEvaluationReportWriter = MarkdownJsonEvaluationReportWriter


def render_case_markdown_report(
    *,
    case: EvaluationCaseDefinition,
    run_summary: RunSummary,
    scoring_summary: ScoringSummary,
    artifact_manifest: ArtifactManifest,
) -> str:
    """Render one reviewer-readable markdown report."""

    lines = [
        f"# Evaluation Report `{case.metadata.case_id}`",
        "",
        "## Run",
        f"- Scenario: `{case.metadata.scenario}`",
        f"- Description: {case.metadata.description}",
        f"- Pack Type: `{case.metadata.pack_type.value}`",
        f"- Run Status: `{run_summary.status.value}`",
        f"- Pipeline Status: `{run_summary.pipeline_status.value if run_summary.pipeline_status is not None else 'n/a'}`",
        f"- Outcome: `{scoring_summary.outcome.value}`",
        f"- Structured Score: `{scoring_summary.overall_score:.2f}`",
    ]
    if (
        case.expected_outputs.bad_behavior_to_catch is not None
        or case.expected_outputs.acceptable_fallback_behavior is not None
    ):
        lines.extend(["", "## Red-Team Intent"])
        if case.expected_outputs.bad_behavior_to_catch is not None:
            lines.append(f"- Bad Behavior To Catch: {case.expected_outputs.bad_behavior_to_catch}")
        if case.expected_outputs.acceptable_fallback_behavior is not None:
            lines.append(f"- Acceptable Fallback: {case.expected_outputs.acceptable_fallback_behavior}")
    lines.extend(["", "## Structured Checks"])
    for metric in scoring_summary.metrics:
        status = "PASS" if metric.passed else "REVIEW"
        lines.append(
            f"- `{metric.metric_name}`: `{status}` score=`{metric.score:.2f}`"
            + (f" {metric.details}" if metric.details else "")
        )

    lines.extend(["", "## Reviewer Signals"])
    if scoring_summary.reviewer_signals:
        for signal in scoring_summary.reviewer_signals:
            status = "TRIGGERED" if signal.triggered else "clear"
            lines.append(
                f"- `{signal.signal_name}`: `{status}` severity=`{signal.severity}`"
                + (f" {signal.details}" if signal.details else "")
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Reviewer Comments"])
    if scoring_summary.reviewer_comments:
        for comment in scoring_summary.reviewer_comments:
            lines.append(f"- {comment}")
    else:
        lines.append("- none")

    lines.extend(["", "## Findings"])
    if scoring_summary.findings:
        for finding in scoring_summary.findings:
            lines.append(f"- {finding}")
    else:
        lines.append("- none")

    lines.extend(["", "## Artifact Links"])
    if scoring_summary.artifact_paths:
        for name, path in sorted(scoring_summary.artifact_paths.items()):
            lines.append(f"- `{name}`: `{path}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Persisted Artifacts"])
    for entry in artifact_manifest.entries:
        lines.append(
            f"- `{entry.stage_name.value}` `{entry.artifact_kind.value}` `{entry.relative_path}`"
        )
    return "\n".join(lines) + "\n"

__all__ = [
    "JsonEvaluationReportWriter",
    "MarkdownJsonEvaluationReportWriter",
    "build_aggregate_json_report",
    "render_aggregate_markdown_report",
    "render_case_markdown_report",
    "render_case_metrics_csv",
    "render_compact_terminal_summary",
]
