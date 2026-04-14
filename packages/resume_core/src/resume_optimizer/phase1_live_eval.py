"""Live Phase 1 job understanding evaluation.

This module provides real-model-based evaluation of Phase 1 JD parsing quality.
It is separate from the synthetic fixture-based evaluation in phase1_eval.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json

from pydantic import Field

from resume_optimizer.ai_service import parse_job_description
from resume_optimizer.models import StrictModel, NonEmptyStr
from resume_optimizer.phase1_models import Phase1ParseResult
from resume_optimizer.phase1_deterministic_extractors import (
    extract_deterministic_job_description_artifacts,
)


DEFAULT_LIVE_EVAL_ROOT = Path("fixtures/evaluation/phase1_live")


class LiveGoldAnnotation(StrictModel):
    """Gold annotations for live Phase 1 evaluation with richer annotations."""

    job_title: NonEmptyStr
    role_family: NonEmptyStr
    seniority: NonEmptyStr | None = None
    must_have_skills: list[NonEmptyStr] = Field(default_factory=list)
    nice_to_have_skills: list[NonEmptyStr] = Field(default_factory=list)
    key_tools: list[NonEmptyStr] = Field(default_factory=list)
    responsibility_clusters: list[NonEmptyStr] = Field(default_factory=list)
    business_domain: NonEmptyStr | None = None
    evidence_type: NonEmptyStr | None = None
    intent_summary: NonEmptyStr


class LiveEvalCase(StrictModel):
    """One live Phase 1 evaluation case with messy real-world JD."""

    case_id: NonEmptyStr
    description: NonEmptyStr
    raw_jd: NonEmptyStr
    gold: LiveGoldAnnotation
    expected_difficulty: NonEmptyStr = "standard"


class LiveEvalManifest(StrictModel):
    """Collection of live Phase 1 evaluation cases."""

    cases: list[LiveEvalCase] = Field(default_factory=list)


class LiveMetricBreakdown(StrictModel):
    """Breakdown of per-metric performance."""

    role_family_accuracy: float = 0.0
    seniority_accuracy: float = 0.0
    title_accuracy: float = 0.0
    must_have_recall: float = 0.0
    must_have_precision: float = 0.0
    nice_to_have_recall: float = 0.0
    responsibility_recall: float = 0.0
    skill_extraction_quality: float = 0.0
    confidence_calibration: float = 0.0


class LiveEvalCaseResult(StrictModel):
    """Result for one live Phase 1 evaluation case."""

    case_id: NonEmptyStr
    passed: bool
    role_family_match: bool
    seniority_match: bool
    title_match: bool
    must_have_recall: float = 0.0
    must_have_precision: float = 0.0
    nice_to_have_recall: float = 0.0
    responsibility_recall: float = 0.0
    missing_must_haves: list[str] = Field(default_factory=list)
    extra_nice_to_haves: list[str] = Field(default_factory=list)
    confidence_calibration: float = 0.0
    parsed_output: dict | None = None
    error: str | None = None


class LiveEvalSummary(StrictModel):
    """Aggregate live Phase 1 evaluation summary."""

    eval_type: str = "live"
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    metrics: LiveMetricBreakdown = Field(default_factory=LiveMetricBreakdown)
    case_results: list[LiveEvalCaseResult] = Field(default_factory=list)
    run_date: date = Field(default_factory=date.today)


def _compute_skill_recall(gold_skills: list[str], parsed_skills: list[str]) -> float:
    if not gold_skills:
        return 1.0
    gold_set = {s.lower() for s in gold_skills}
    parsed_set = {s.lower() for s in parsed_skills}
    matches = gold_set & parsed_set
    return len(matches) / len(gold_set)


def _compute_skill_precision(gold_skills: list[str], parsed_skills: list[str]) -> float:
    if not parsed_skills:
        return 0.0
    gold_set = {s.lower() for s in gold_skills}
    parsed_set = {s.lower() for s in parsed_skills}
    matches = gold_set & parsed_set
    return len(matches) / len(parsed_set)


def _compute_responsibility_recall(
    gold_clusters: list[str], parsed_clusters: list[str]
) -> float:
    if not gold_clusters:
        return 1.0
    matched = 0
    gold_lower = [g.lower() for g in gold_clusters]
    for cluster in parsed_clusters:
        cluster_lower = cluster.lower()
        if any(g in cluster_lower or cluster_lower in g for g in gold_lower):
            matched += 1
    return matched / len(gold_clusters)


def _extract_must_haves(parsed: Phase1ParseResult) -> list[str]:
    if parsed.enriched_analysis and parsed.enriched_analysis.must_have_skills:
        return list(parsed.enriched_analysis.must_have_skills)
    return []


def _extract_nice_to_haves(parsed: Phase1ParseResult) -> list[str]:
    if parsed.enriched_analysis and parsed.enriched_analysis.nice_to_have_skills:
        return list(parsed.enriched_analysis.nice_to_have_skills)
    return []


def _extract_role_family(parsed: Phase1ParseResult) -> str:
    if parsed.enriched_analysis and parsed.enriched_analysis.functional_role_family:
        return parsed.enriched_analysis.functional_role_family.value
    return ""


def _extract_seniority(parsed: Phase1ParseResult) -> str:
    if parsed.enriched_analysis and parsed.enriched_analysis.seniority_level:
        return parsed.enriched_analysis.seniority_level.value
    return ""


def _compute_confidence_calibration(confidence: float, correctness: bool) -> float:
    if confidence >= 0.8 and correctness:
        return 1.0
    elif confidence >= 0.8 and not correctness:
        return 0.0
    elif confidence < 0.5 and not correctness:
        return 1.0
    elif confidence < 0.5 and correctness:
        return 0.5
    else:
        return 0.75


def load_live_eval_manifest(
    manifest_path: Path | None = None,
) -> LiveEvalManifest:
    """Load the live Phase 1 evaluation manifest."""
    if manifest_path is None:
        manifest_path = DEFAULT_LIVE_EVAL_ROOT / "live_cases.json"
    if not manifest_path.exists():
        return LiveEvalManifest(cases=[])
    return LiveEvalManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )


def run_live_phase1_eval(
    *,
    manifest_path: Path | None = None,
    case_ids: list[str] | None = None,
    verbose: bool = False,
) -> LiveEvalSummary:
    """Run live Phase 1 evaluation on real JDs using actual model calls."""

    manifest = load_live_eval_manifest(manifest_path)
    selected = set(case_ids) if case_ids else None

    case_results = []
    for case in manifest.cases:
        if selected is not None and case.case_id not in selected:
            continue

        result = _run_live_case(case, verbose=verbose)
        case_results.append(result)

    return _build_live_summary(case_results)


def _run_live_case(case: LiveEvalCase, verbose: bool = False) -> LiveEvalCaseResult:
    """Run one live Phase 1 eval case with real model call."""

    try:
        parsed = parse_job_description(case.raw_jd)
    except Exception as e:
        return LiveEvalCaseResult(
            case_id=case.case_id,
            passed=False,
            role_family_match=False,
            seniority_match=False,
            title_match=False,
            error=str(e),
        )

    parsed_role_family = _extract_role_family(parsed)
    parsed_seniority = _extract_seniority(parsed)
    parsed_title = (
        parsed.enriched_analysis.job_title if parsed.enriched_analysis else ""
    )

    role_family_match = parsed_role_family.lower() == case.gold.role_family.lower()
    seniority_match = (
        parsed_seniority.lower() == case.gold.seniority.lower()
        if case.gold.seniority and parsed_seniority
        else not case.gold.seniority or not parsed_seniority
    )
    title_match = (
        parsed_title.lower() == case.gold.job_title.lower()
        if parsed_title and case.gold.job_title
        else False
    )

    must_haves_parsed = _extract_must_haves(parsed)
    nice_to_haves_parsed = _extract_nice_to_haves(parsed)

    must_have_recall = _compute_skill_recall(
        case.gold.must_have_skills, must_haves_parsed
    )
    must_have_precision = _compute_skill_precision(
        case.gold.must_have_skills, must_haves_parsed
    )
    nice_to_have_recall = _compute_skill_recall(
        case.gold.nice_to_have_skills, nice_to_haves_parsed
    )

    parsed_clusters = []
    if (
        parsed.enriched_analysis
        and parsed.enriched_analysis.primary_responsibility_clusters
    ):
        parsed_clusters = list(parsed.enriched_analysis.primary_responsibility_clusters)

    responsibility_recall = _compute_responsibility_recall(
        case.gold.responsibility_clusters, parsed_clusters
    )

    gold_set = {s.lower() for s in case.gold.must_have_skills}
    parsed_set = {s.lower() for s in must_haves_parsed}
    missing = list(gold_set - parsed_set)

    parsed_nice_set = {s.lower() for s in nice_to_haves_parsed}
    gold_nice_set = {s.lower() for s in case.gold.nice_to_have_skills}
    extra_nice = list(parsed_nice_set - gold_nice_set)

    confidence = getattr(parsed, "parser_confidence", 0.7) or 0.7
    correctness = role_family_match and (not case.gold.seniority or seniority_match)
    confidence_cal = _compute_confidence_calibration(confidence, correctness)

    passed = (
        role_family_match and must_have_recall >= 0.6 and responsibility_recall >= 0.5
    )

    return LiveEvalCaseResult(
        case_id=case.case_id,
        passed=passed,
        role_family_match=role_family_match,
        seniority_match=seniority_match,
        title_match=title_match,
        must_have_recall=must_have_recall,
        must_have_precision=must_have_precision,
        nice_to_have_recall=nice_to_have_recall,
        responsibility_recall=responsibility_recall,
        missing_must_haves=missing,
        extra_nice_to_haves=extra_nice,
        confidence_calibration=confidence_cal,
        parsed_output=parsed.model_dump(mode="json") if verbose else None,
    )


def _build_live_summary(case_results: list[LiveEvalCaseResult]) -> LiveEvalSummary:
    """Build aggregate summary from individual case results."""

    total = len(case_results)
    passed = sum(1 for r in case_results if r.passed)
    failed = total - passed

    if total == 0:
        return LiveEvalSummary(
            eval_type="live",
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
        )

    role_family_matches = sum(1 for r in case_results if r.role_family_match)
    seniority_matches = sum(1 for r in case_results if r.seniority_match)
    title_matches = sum(1 for r in case_results if r.title_match)

    avg_must_recall = sum(r.must_have_recall for r in case_results) / total
    avg_must_precision = sum(r.must_have_precision for r in case_results) / total
    avg_nice_recall = sum(r.nice_to_have_recall for r in case_results) / total
    avg_resp_recall = sum(r.responsibility_recall for r in case_results) / total
    avg_conf_cal = sum(r.confidence_calibration for r in case_results) / total

    skill_quality = (avg_must_recall + avg_must_precision) / 2

    return LiveEvalSummary(
        eval_type="live",
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        metrics=LiveMetricBreakdown(
            role_family_accuracy=role_family_matches / total,
            seniority_accuracy=seniority_matches / total,
            title_accuracy=title_matches / total,
            must_have_recall=avg_must_recall,
            must_have_precision=avg_must_precision,
            nice_to_have_recall=avg_nice_recall,
            responsibility_recall=avg_resp_recall,
            skill_extraction_quality=skill_quality,
            confidence_calibration=avg_conf_cal,
        ),
        case_results=case_results,
    )


def render_live_eval_summary(summary: LiveEvalSummary) -> str:
    """Render a CLI-friendly text summary for live eval."""

    lines = [
        f"=== LIVE Phase 1 Evaluation (real model calls) ===",
        f"Date: {summary.run_date}",
        f"Cases: {summary.total_cases} | Passed: {summary.passed_cases} | Failed: {summary.failed_cases}",
        f"",
        f"Accuracy Metrics:",
        f"  role_family: {summary.metrics.role_family_accuracy:.2f}",
        f"  seniority: {summary.metrics.seniority_accuracy:.2f}",
        f"  title: {summary.metrics.title_accuracy:.2f}",
        f"",
        f"Recall/Precision:",
        f"  must_have recall: {summary.metrics.must_have_recall:.2f}",
        f"  must_have precision: {summary.metrics.must_have_precision:.2f}",
        f"  nice_to_have recall: {summary.metrics.nice_to_have_recall:.2f}",
        f"  responsibility recall: {summary.metrics.responsibility_recall:.2f}",
        f"",
        f"Quality:",
        f"  skill extraction: {summary.metrics.skill_extraction_quality:.2f}",
        f"  confidence calibration: {summary.metrics.confidence_calibration:.2f}",
        f"",
        f"Case Details:",
    ]

    for result in summary.case_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"  [{status}] {result.case_id}: "
            f"role={int(result.role_family_match)}, "
            f"seniority={int(result.seniority_match)}, "
            f"must_recall={result.must_have_recall:.2f}, "
            f"resp_recall={result.responsibility_recall:.2f}"
        )
        if result.missing_must_haves:
            lines.append(f"      missing must-haves: {result.missing_must_haves}")
        if result.error:
            lines.append(f"      error: {result.error}")

    return "\n".join(lines)


def live_eval_summary_json(summary: LiveEvalSummary) -> str:
    """Return the live eval summary as formatted JSON."""

    return json.dumps(summary.model_dump(mode="json"), indent=2)
