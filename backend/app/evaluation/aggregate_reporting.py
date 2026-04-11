"""Aggregate run-level reporting for Phase 7 evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
import csv
import json
import re
from typing import Any


_OUTCOME_RANK = {
    "fail": 0,
    "review": 1,
    "pass": 2,
}


def build_aggregate_json_report(
    *,
    results: list[dict[str, object]],
    previous_report: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build one aggregate JSON report across executed cases."""

    enriched_results = [_enrich_result(item) for item in results]
    outcomes = _count_values(item.get("outcome", "unknown") for item in enriched_results)
    aggregate = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_cases": len(enriched_results),
        "outcomes": outcomes,
        "pack_counts": _count_values(item.get("pack_type", "unknown") for item in enriched_results),
        "results": enriched_results,
        "machine_summary": {
            "parse_metrics": _metric_rollups(enriched_results, "jd_parse"),
            "selection_metrics": _metric_rollups(enriched_results, "selection"),
            "end_to_end_metrics": _metric_rollups(enriched_results, "end_to_end"),
            "verification_issue_counts": _verification_summary(enriched_results),
            "render_success_rate": _render_summary(enriched_results),
        },
        "human_summary": {
            "pass_count": outcomes.get("pass", 0),
            "review_count": outcomes.get("review", 0),
            "fail_count": outcomes.get("fail", 0),
            "worst_failing_cases": _worst_failing_cases(enriched_results),
        },
    }
    comparison = compare_aggregate_reports(current_report=aggregate, previous_report=previous_report)
    if comparison is not None:
        aggregate["comparison"] = comparison
        aggregate["human_summary"]["top_regressions"] = comparison["top_regressions"]
        aggregate["human_summary"]["top_improvements"] = comparison["top_improvements"]
    else:
        aggregate["human_summary"]["top_regressions"] = []
        aggregate["human_summary"]["top_improvements"] = []
    return aggregate


def compare_aggregate_reports(
    *,
    current_report: dict[str, object],
    previous_report: dict[str, object] | None,
    delta_threshold: float = 0.03,
) -> dict[str, object] | None:
    """Compare the current aggregate report to a previous saved run."""

    if previous_report is None:
        return None

    current_results = {
        str(item["case_id"]): item for item in current_report.get("results", []) if isinstance(item, dict) and "case_id" in item
    }
    previous_results = {
        str(item["case_id"]): item for item in previous_report.get("results", []) if isinstance(item, dict) and "case_id" in item
    }

    shared_case_ids = sorted(set(current_results) & set(previous_results))
    added_case_ids = sorted(set(current_results) - set(previous_results))
    removed_case_ids = sorted(set(previous_results) - set(current_results))

    case_deltas: list[dict[str, object]] = []
    metric_changes: dict[str, list[dict[str, object]]] = defaultdict(list)
    for case_id in shared_case_ids:
        current = current_results[case_id]
        previous = previous_results[case_id]
        current_score = _to_float(current.get("overall_score"))
        previous_score = _to_float(previous.get("overall_score"))
        outcome_delta = _OUTCOME_RANK.get(str(current.get("outcome")), -1) - _OUTCOME_RANK.get(str(previous.get("outcome")), -1)
        metric_deltas: list[dict[str, object]] = []
        current_metrics = {metric["metric_name"]: metric for metric in current.get("metrics", []) if isinstance(metric, dict) and "metric_name" in metric}
        previous_metrics = {metric["metric_name"]: metric for metric in previous.get("metrics", []) if isinstance(metric, dict) and "metric_name" in metric}

        for metric_name in sorted(set(current_metrics) & set(previous_metrics)):
            current_metric = current_metrics[metric_name]
            previous_metric = previous_metrics[metric_name]
            delta = round(_to_float(current_metric.get("score")) - _to_float(previous_metric.get("score")), 4)
            metric_deltas.append(
                {
                    "metric_name": metric_name,
                    "delta": delta,
                    "current_score": _to_float(current_metric.get("score")),
                    "previous_score": _to_float(previous_metric.get("score")),
                    "current_passed": bool(current_metric.get("passed", False)),
                    "previous_passed": bool(previous_metric.get("passed", False)),
                }
            )
            metric_changes[metric_name].append(
                {
                    "case_id": case_id,
                    "delta": delta,
                    "pack_type": current.get("pack_type"),
                    "report_path": current.get("report_path"),
                    "current_outcome": current.get("outcome"),
                    "previous_outcome": previous.get("outcome"),
                }
            )

        case_deltas.append(
            {
                "case_id": case_id,
                "pack_type": current.get("pack_type"),
                "overall_score_delta": round(current_score - previous_score, 4),
                "current_score": current_score,
                "previous_score": previous_score,
                "current_outcome": current.get("outcome"),
                "previous_outcome": previous.get("outcome"),
                "outcome_delta": outcome_delta,
                "metric_deltas": metric_deltas,
                "report_path": current.get("report_path"),
            }
        )

    regressions = [
        item
        for item in case_deltas
        if item["outcome_delta"] < 0 or float(item["overall_score_delta"]) <= -delta_threshold
    ]
    improvements = [
        item
        for item in case_deltas
        if item["outcome_delta"] > 0 or float(item["overall_score_delta"]) >= delta_threshold
    ]

    return {
        "previous_generated_at": previous_report.get("generated_at"),
        "delta_threshold": delta_threshold,
        "shared_case_count": len(shared_case_ids),
        "added_case_ids": added_case_ids,
        "removed_case_ids": removed_case_ids,
        "case_deltas": case_deltas,
        "top_regressions": sorted(regressions, key=lambda item: (item["outcome_delta"], float(item["overall_score_delta"])))[:5],
        "top_improvements": sorted(improvements, key=lambda item: (item["outcome_delta"], float(item["overall_score_delta"])), reverse=True)[:5],
        "metric_regressions": _metric_delta_summary(metric_changes, regression=True, delta_threshold=delta_threshold),
        "metric_improvements": _metric_delta_summary(metric_changes, regression=False, delta_threshold=delta_threshold),
    }


def render_aggregate_markdown_report(aggregate_report: dict[str, object]) -> str:
    """Render a human-readable markdown summary for one run."""

    outcomes = aggregate_report.get("outcomes", {})
    machine_summary = aggregate_report.get("machine_summary", {})
    human_summary = aggregate_report.get("human_summary", {})
    comparison = aggregate_report.get("comparison")
    lines = [
        "# Phase 7 Evaluation Summary",
        "",
        "## Overview",
        f"- Generated At: `{aggregate_report.get('generated_at', 'unknown')}`",
        f"- Total Cases: `{aggregate_report.get('total_cases', 0)}`",
        f"- Pass/Review/Fail: `{outcomes.get('pass', 0)}/{outcomes.get('review', 0)}/{outcomes.get('fail', 0)}`",
        f"- Pack Coverage: `{_render_pack_counts(aggregate_report.get('pack_counts', {}))}`",
        "",
        "## Machine Summary",
    ]
    lines.extend(_render_metric_rollup_block("Parse Metrics", machine_summary.get("parse_metrics", {})))
    lines.extend(_render_metric_rollup_block("Selection Metrics", machine_summary.get("selection_metrics", {})))
    lines.extend(_render_metric_rollup_block("End-to-End Metrics", machine_summary.get("end_to_end_metrics", {})))

    verification = machine_summary.get("verification_issue_counts", {})
    lines.extend([
        "",
        "### Verification",
        f"- Total Issues: `{verification.get('total', 0)}`",
        f"- By Category: `{_render_counter(verification.get('by_category', {}))}`",
        f"- By Severity: `{_render_counter(verification.get('by_severity', {}))}`",
    ])
    render = machine_summary.get("render_success_rate", {})
    lines.extend([
        "",
        "### Render",
        f"- Success Rate: `{float(render.get('rate', 0.0)):.2f}` ({render.get('successes', 0)}/{render.get('attempted_cases', 0)})",
        "",
        "## Worst Failing Cases",
    ])

    worst_failing = human_summary.get("worst_failing_cases", [])
    if worst_failing:
        for item in worst_failing:
            lines.append(
                f"- `{item['case_id']}` pack=`{item.get('pack_type', 'unknown')}` "
                f"outcome=`{item.get('outcome', 'unknown')}` score=`{float(item.get('overall_score', 0.0)):.2f}` "
                f"report=`{item.get('report_path') or 'n/a'}`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Top Regressions"])
    regressions = (comparison or {}).get("top_regressions") or human_summary.get("top_regressions", [])
    if regressions:
        for item in regressions:
            lines.append(
                f"- `{item['case_id']}` score_delta=`{float(item.get('overall_score_delta', 0.0)):+.2f}` "
                f"outcome=`{item.get('previous_outcome', 'unknown')}` -> `{item.get('current_outcome', 'unknown')}`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Top Improvements"])
    improvements = (comparison or {}).get("top_improvements") or human_summary.get("top_improvements", [])
    if improvements:
        for item in improvements:
            lines.append(
                f"- `{item['case_id']}` score_delta=`{float(item.get('overall_score_delta', 0.0)):+.2f}` "
                f"outcome=`{item.get('previous_outcome', 'unknown')}` -> `{item.get('current_outcome', 'unknown')}`"
            )
    else:
        lines.append("- none")

    if comparison is not None:
        lines.extend([
            "",
            "## Trend Comparison",
            f"- Shared Cases: `{comparison.get('shared_case_count', 0)}`",
            f"- Added Cases: `{', '.join(comparison.get('added_case_ids', [])) or 'none'}`",
            f"- Removed Cases: `{', '.join(comparison.get('removed_case_ids', [])) or 'none'}`",
            "- Metric Regressions: `"
            + (
                ", ".join(
                    f"{item['metric_name']} {float(item['average_delta']):+.2f}"
                    for item in comparison.get("metric_regressions", [])[:5]
                )
                or "none"
            )
            + "`",
        ])

    lines.extend([
        "",
        "## Traceability",
        "- Every aggregate metric in `aggregate_report.json` includes case-level values or case references.",
        "- Use `aggregate_case_metrics.csv` to inspect one row per case/metric in CI or spreadsheets.",
    ])
    return "\n".join(lines) + "\n"


def render_compact_terminal_summary(
    results: list[dict[str, object]],
    aggregate_report: dict[str, object] | None = None,
) -> str:
    """Render a compact terminal summary suitable for local runs and CI logs."""

    report = aggregate_report or build_aggregate_json_report(results=results)
    lines = [
        f"cases={report['total_cases']} pass={report['outcomes'].get('pass', 0)} review={report['outcomes'].get('review', 0)} fail={report['outcomes'].get('fail', 0)}"
    ]
    for item in report["results"]:
        signal_names = [
            signal["signal_name"]
            for signal in item.get("reviewer_signals", [])
            if signal.get("triggered")
        ]
        lines.append(
            f"[{str(item.get('outcome', 'unknown')).upper()}] {item['case_id']} "
            f"pack={item.get('pack_type', 'unknown')} mode={item.get('execution_mode')} "
            f"pipeline={item.get('pipeline_status')} score={float(item.get('overall_score', 0.0)):.2f} "
            f"signals={','.join(signal_names) if signal_names else 'none'}"
        )
    comparison = report.get("comparison")
    if comparison is not None and comparison.get("top_regressions"):
        lines.append(
            "regressions="
            + ",".join(
                f"{item['case_id']}:{float(item['overall_score_delta']):+.2f}"
                for item in comparison["top_regressions"][:3]
            )
        )
    return "\n".join(lines)


def render_case_metrics_csv(results: list[dict[str, object]]) -> str:
    """Flatten one row per case-level metric for spreadsheet and CI artifact use."""

    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "case_id",
            "pack_type",
            "outcome",
            "overall_score",
            "metric_name",
            "metric_score",
            "metric_passed",
            "report_path",
        ],
    )
    writer.writeheader()
    for item in results:
        metrics = item.get("metrics", [])
        if not metrics:
            writer.writerow(
                {
                    "case_id": item.get("case_id"),
                    "pack_type": item.get("pack_type"),
                    "outcome": item.get("outcome"),
                    "overall_score": item.get("overall_score"),
                    "metric_name": "",
                    "metric_score": "",
                    "metric_passed": "",
                    "report_path": item.get("report_path"),
                }
            )
            continue
        for metric in metrics:
            writer.writerow(
                {
                    "case_id": item.get("case_id"),
                    "pack_type": item.get("pack_type"),
                    "outcome": item.get("outcome"),
                    "overall_score": item.get("overall_score"),
                    "metric_name": metric.get("metric_name"),
                    "metric_score": metric.get("score"),
                    "metric_passed": metric.get("passed"),
                    "report_path": item.get("report_path"),
                }
            )
    return buffer.getvalue()


def load_aggregate_report(path: Path) -> dict[str, object]:
    """Load a saved aggregate report from a file path or run directory."""

    target = path / "aggregate_report.json" if path.is_dir() else path
    return json.loads(target.read_text(encoding="utf-8"))


def _metric_rollups(results: list[dict[str, object]], pack_type: str) -> dict[str, object]:
    pack_results = [item for item in results if item.get("pack_type") == pack_type]
    metric_cases: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in pack_results:
        for metric in item.get("metrics", []):
            metric_name = metric.get("metric_name")
            if not metric_name:
                continue
            metric_cases[str(metric_name)].append(
                {
                    "case_id": item.get("case_id"),
                    "score": _to_float(metric.get("score")),
                    "passed": bool(metric.get("passed", False)),
                    "outcome": item.get("outcome"),
                    "report_path": item.get("report_path"),
                }
            )
    return {
        metric_name: {
            "average_score": round(sum(entry["score"] for entry in entries) / len(entries), 4),
            "pass_rate": round(sum(1 for entry in entries if entry["passed"]) / len(entries), 4),
            "case_values": entries,
        }
        for metric_name, entries in sorted(metric_cases.items())
    }


def _verification_summary(results: list[dict[str, object]]) -> dict[str, object]:
    cases: list[dict[str, object]] = []
    by_category: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    total = 0
    for item in results:
        if item.get("pack_type") != "end_to_end":
            continue
        count = int(item.get("verification_issue_count", _extract_issue_count_from_metrics(item)))
        total += count
        category_counts = item.get("verification_issue_categories") or {}
        severity_counts = item.get("verification_issue_severity_counts") or {}
        by_category.update({str(key): int(value) for key, value in category_counts.items()})
        by_severity.update({str(key): int(value) for key, value in severity_counts.items()})
        cases.append(
            {
                "case_id": item.get("case_id"),
                "issue_count": count,
                "report_path": item.get("report_path"),
                "categories": category_counts,
                "severities": severity_counts,
            }
        )
    return {
        "total": total,
        "by_category": dict(sorted(by_category.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "case_values": cases,
    }


def _render_summary(results: list[dict[str, object]]) -> dict[str, object]:
    attempted = 0
    successes = 0
    case_values: list[dict[str, object]] = []
    for item in results:
        if item.get("pack_type") != "end_to_end":
            continue
        render_attempted = bool(item.get("render_attempted", False))
        render_success = item.get("render_success")
        if not render_attempted and render_success is None:
            continue
        attempted += 1
        if bool(render_success):
            successes += 1
        case_values.append(
            {
                "case_id": item.get("case_id"),
                "attempted": render_attempted,
                "success": bool(render_success),
                "report_path": item.get("report_path"),
            }
        )
    return {
        "attempted_cases": attempted,
        "successes": successes,
        "rate": round(successes / attempted, 4) if attempted else 0.0,
        "case_values": case_values,
    }


def _worst_failing_cases(results: list[dict[str, object]], limit: int = 5) -> list[dict[str, object]]:
    failures = [item for item in results if item.get("outcome") in {"fail", "review"}]
    failures.sort(key=lambda item: (_OUTCOME_RANK.get(str(item.get("outcome")), -1), _to_float(item.get("overall_score"))))
    return [
        {
            "case_id": item.get("case_id"),
            "pack_type": item.get("pack_type"),
            "outcome": item.get("outcome"),
            "overall_score": _to_float(item.get("overall_score")),
            "report_path": item.get("report_path"),
        }
        for item in failures[:limit]
    ]


def _metric_delta_summary(
    metric_changes: dict[str, list[dict[str, object]]],
    *,
    regression: bool,
    delta_threshold: float,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for metric_name, entries in metric_changes.items():
        if regression:
            changed_entries = [entry for entry in entries if float(entry["delta"]) <= -delta_threshold]
        else:
            changed_entries = [entry for entry in entries if float(entry["delta"]) >= delta_threshold]
        if not changed_entries:
            continue
        average_delta = sum(float(entry["delta"]) for entry in entries) / len(entries)
        items.append(
            {
                "metric_name": metric_name,
                "average_delta": round(average_delta, 4),
                "affected_cases": len(changed_entries),
                "cases": changed_entries[:10],
            }
        )
    items.sort(key=lambda item: item["average_delta"], reverse=not regression)
    return items[:10]


def _enrich_result(item: dict[str, object]) -> dict[str, object]:
    enriched = dict(item)
    metrics = [metric for metric in enriched.get("metrics", []) if isinstance(metric, dict)]
    metric_map = {str(metric.get("metric_name")): metric for metric in metrics if metric.get("metric_name")}
    if "verification_issue_count" not in enriched:
        enriched["verification_issue_count"] = _extract_issue_count_from_metrics(enriched)
    if "render_success" not in enriched:
        render_metric = metric_map.get("render_success")
        if render_metric is not None:
            details = str(render_metric.get("details", ""))
            enriched["render_attempted"] = details != "render not requested"
            enriched["render_success"] = bool(render_metric.get("passed")) if details != "render not requested" else None
    return enriched


def _extract_issue_count_from_metrics(item: dict[str, object]) -> int:
    for metric in item.get("metrics", []):
        if metric.get("metric_name") not in {"verification_behavior", "selected_content_faithfulness"}:
            continue
        details = str(metric.get("details", ""))
        match = re.search(r"issue_count=(\d+)", details)
        if match:
            return int(match.group(1))
    return 0


def _count_values(values) -> dict[str, int]:
    counter = Counter(str(value) for value in values)
    return dict(sorted(counter.items()))


def _render_metric_rollup_block(title: str, block: dict[str, object]) -> list[str]:
    lines = ["", f"### {title}"]
    if not block:
        lines.append("- none")
        return lines
    for metric_name, details in block.items():
        lines.append(
            f"- `{metric_name}` average=`{float(details['average_score']):.2f}` "
            f"pass_rate=`{float(details['pass_rate']):.2f}` "
            f"cases=`{len(details['case_values'])}`"
        )
    return lines


def _render_pack_counts(packs: dict[str, object]) -> str:
    if not packs:
        return "none"
    return ", ".join(f"{pack}={count}" for pack, count in sorted(packs.items()))


def _render_counter(counter: dict[str, object]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
