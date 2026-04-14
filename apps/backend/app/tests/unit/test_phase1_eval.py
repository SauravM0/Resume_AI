from __future__ import annotations

import json

from resume_optimizer.phase1_eval import (
    load_phase1_eval_manifest,
    phase1_eval_summary_json,
    render_phase1_eval_summary,
    run_phase1_eval,
)


def test_phase1_eval_manifest_exists_and_has_required_coverage() -> None:
    manifest = load_phase1_eval_manifest()

    assert len(manifest.cases) >= 30
    tag_coverage = {tag for case in manifest.cases for tag in case.tags}
    assert {
        "frontend",
        "backend",
        "fullstack",
        "platform",
        "devops",
        "data",
        "analytics",
        "ml",
        "product",
        "design",
        "startup",
        "enterprise",
        "junior",
        "senior",
        "manager",
        "lead",
        "vague",
        "noisy",
        "highly_structured",
    }.issubset(tag_coverage)


def test_phase1_eval_runner_executes_gold_cases_successfully() -> None:
    summary = run_phase1_eval()

    assert summary.total_cases >= 30
    assert summary.passed_cases == summary.total_cases
    assert summary.failed_cases == 0
    assert summary.title_accuracy == 1.0
    assert summary.role_family_accuracy == 1.0
    assert summary.org_mode_accuracy == 1.0
    assert summary.average_must_have_skill_recall >= 0.98
    assert summary.average_responsibility_recall >= 0.9
    assert summary.average_recruiter_intent_similarity >= 0.7
    assert summary.quality_pass_rate == 1.0


def test_phase1_eval_summary_renderers_expose_case_metrics() -> None:
    summary = run_phase1_eval(case_ids=["frontend_junior_react_startup", "vague_software_role"])

    text_output = render_phase1_eval_summary(summary)
    json_output = phase1_eval_summary_json(summary)
    parsed = json.loads(json_output)

    assert "Phase 1 Evaluation Summary" in text_output
    assert "frontend_junior_react_startup" in text_output
    assert "vague_software_role" in text_output
    assert parsed["total_cases"] == 2
    assert len(parsed["case_results"]) == 2
