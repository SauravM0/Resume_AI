from __future__ import annotations

from backend.app.evaluation.aggregate_reporting import (
    build_aggregate_json_report,
    render_aggregate_markdown_report,
    render_case_metrics_csv,
)


def test_aggregate_report_rolls_up_pack_metrics_and_traceability() -> None:
    previous = {
        "generated_at": "2026-04-09T00:00:00+00:00",
        "results": [
            {
                "case_id": "sel.case.1",
                "pack_type": "selection",
                "outcome": "pass",
                "overall_score": 0.92,
                "metrics": [
                    {"metric_name": "experience_precision", "score": 0.9, "passed": True},
                    {"metric_name": "bullet_precision", "score": 0.9, "passed": True},
                ],
            },
            {
                "case_id": "e2e.case.1",
                "pack_type": "end_to_end",
                "outcome": "review",
                "overall_score": 0.75,
                "metrics": [{"metric_name": "summary_quality_fit", "score": 0.7, "passed": True}],
            },
        ],
    }
    current = [
        {
            "case_id": "parse.case.1",
            "pack_type": "jd_parse",
            "outcome": "pass",
            "overall_score": 0.88,
            "report_path": "/tmp/parse.case.1/report.md",
            "metrics": [
                {"metric_name": "title_accuracy", "score": 1.0, "passed": True},
                {"metric_name": "must_have_skill_recall", "score": 0.8, "passed": True},
            ],
        },
        {
            "case_id": "sel.case.1",
            "pack_type": "selection",
            "outcome": "review",
            "overall_score": 0.71,
            "report_path": "/tmp/sel.case.1/report.md",
            "metrics": [
                {"metric_name": "experience_precision", "score": 0.6, "passed": False},
                {"metric_name": "bullet_precision", "score": 0.55, "passed": False},
            ],
        },
        {
            "case_id": "e2e.case.1",
            "pack_type": "end_to_end",
            "outcome": "pass",
            "overall_score": 0.82,
            "report_path": "/tmp/e2e.case.1/report.md",
            "metrics": [
                {"metric_name": "summary_quality_fit", "score": 0.85, "passed": True},
                {"metric_name": "verification_behavior", "score": 0.8, "passed": True, "details": "issue_count=2"},
                {"metric_name": "render_success", "score": 1.0, "passed": True, "details": "compile_success=True"},
            ],
            "verification_issue_count": 2,
            "verification_issue_categories": {"unsupported_claim": 1, "provenance_weak": 1},
            "verification_issue_severity_counts": {"medium": 1, "high": 1},
            "render_attempted": True,
            "render_success": True,
        },
    ]

    aggregate = build_aggregate_json_report(results=current, previous_report=previous)

    assert aggregate["total_cases"] == 3
    assert aggregate["outcomes"] == {"pass": 2, "review": 1}
    assert aggregate["machine_summary"]["selection_metrics"]["experience_precision"]["average_score"] == 0.6
    assert aggregate["machine_summary"]["selection_metrics"]["experience_precision"]["case_values"][0]["case_id"] == "sel.case.1"
    assert aggregate["machine_summary"]["verification_issue_counts"]["total"] == 2
    assert aggregate["machine_summary"]["render_success_rate"]["rate"] == 1.0
    assert aggregate["comparison"]["top_regressions"][0]["case_id"] == "sel.case.1"
    assert aggregate["comparison"]["metric_regressions"][0]["metric_name"] in {"experience_precision", "bullet_precision"}


def test_render_aggregate_markdown_and_csv() -> None:
    aggregate = build_aggregate_json_report(
        results=[
            {
                "case_id": "case.a",
                "pack_type": "selection",
                "outcome": "fail",
                "overall_score": 0.42,
                "report_path": "/tmp/case.a/report.md",
                "metrics": [{"metric_name": "experience_recall", "score": 0.4, "passed": False}],
            },
            {
                "case_id": "case.b",
                "pack_type": "end_to_end",
                "outcome": "pass",
                "overall_score": 0.91,
                "report_path": "/tmp/case.b/report.md",
                "metrics": [{"metric_name": "render_success", "score": 1.0, "passed": True, "details": "compile_success=True"}],
                "render_attempted": True,
                "render_success": True,
            },
        ]
    )

    markdown = render_aggregate_markdown_report(aggregate)
    csv_text = render_case_metrics_csv(aggregate["results"])

    assert "# Phase 7 Evaluation Summary" in markdown
    assert "## Worst Failing Cases" in markdown
    assert "## Top Regressions" in markdown
    assert "case_id,pack_type,outcome,overall_score,metric_name,metric_score,metric_passed,report_path" in csv_text
    assert "case.a,selection,fail,0.42,experience_recall,0.4,False,/tmp/case.a/report.md" in csv_text
