"""JD Parse Evaluation Runner for Phase 7.

This runner evaluates whether the real Phase 1 parser correctly captures:
- Job title correctness
- Functional role family correctness
- Organizational role mode correctness
- Seniority correctness
- Must-have skill extraction quality
- Nice-to-have skill extraction quality
- Responsibility cluster quality
- Parser confidence presence and sanity

Supports partial credit scoring and multiple evaluation modes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..phase1_parser import parse_job_description_with_llm_enrichment
from .case_models import (
    EvaluationCase,
    EvaluationPack,
    Expectation,
    Phase1ParseExpectations,
)
from .loader import load_evaluation_pack


class MatchMode(StrEnum):
    """How to evaluate a field against expected values."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    SUBSET = "subset"
    ACCEPTABLE = "acceptable"


@dataclass
class FieldScore:
    """Score for one field evaluation."""

    field_name: str
    expected: str | None
    actual: str | None
    matched: bool
    score: float
    max_score: float
    details: str = ""


@dataclass
class SkillScore:
    """Score for skill extraction evaluation."""

    skill_name: str
    expected_type: str
    matched: bool
    score: float
    max_score: float


@dataclass
class JDParseCaseResult:
    """Result for one evaluation case."""

    case_id: str
    description: str
    passed: bool
    overall_score: float

    title_score: FieldScore | None = None
    role_family_score: FieldScore | None = None
    org_mode_score: FieldScore | None = None
    seniority_score: FieldScore | None = None

    must_have_skills: list[SkillScore] = field(default_factory=list)
    nice_to_have_skills: list[SkillScore] = field(default_factory=list)

    responsibility_score: float = 0.0
    responsibility_details: str = ""

    confidence_score: float = 0.0
    confidence_details: str = ""

    failure_reasons: list[str] = field(default_factory=list)
    actual_output: dict[str, Any] = field(default_factory=dict)


@dataclass
class JDParseSummary:
    """Aggregate summary for all cases."""

    total_cases: int
    passed_cases: int
    failed_cases: int

    title_accuracy: float
    role_family_accuracy: float
    org_mode_accuracy: float
    seniority_accuracy: float

    must_have_skill_recall: float
    nice_to_have_skill_recall: float
    responsibility_recall: float

    average_confidence: float

    case_results: list[JDParseCaseResult] = field(default_factory=list)


def run_jd_parse_evaluation(
    pack_path: str | Path,
    *,
    client: Any = None,
    model: str | None = None,
    fail_fast: bool = False,
) -> JDParseSummary:
    """Run JD parse evaluation on a pack.

    Args:
        pack_path: Path to the evaluation pack YAML/JSON file.
        client: Optional OpenAI client for parsing.
        model: Optional model override.
        fail_fast: Stop on first failure.

    Returns:
        JDParseSummary with all results.
    """
    pack = load_evaluation_pack(pack_path)

    if pack.pack_type != "jd_parse":
        raise ValueError(f"Pack type must be jd_parse, got {pack.pack_type}")

    case_results: list[JDParseCaseResult] = []

    for case in pack.cases:
        result = _evaluate_single_case(case, client=client, model=model)
        case_results.append(result)

        if fail_fast and not result.passed:
            break

    return _build_summary(case_results)


def _evaluate_single_case(
    case: EvaluationCase,
    *,
    client: Any = None,
    model: str | None = None,
) -> JDParseCaseResult:
    """Evaluate a single JD parse case."""
    expectations = case.phase1_expectations
    if expectations is None:
        return JDParseCaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            overall_score=0.0,
            failure_reasons=["No phase1_expectations defined"],
        )

    jd_text = case.job_description.raw_text if case.job_description else ""
    if not jd_text:
        return JDParseCaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            overall_score=0.0,
            failure_reasons=["No job description provided"],
        )

    try:
        parse_result = parse_job_description_with_llm_enrichment(
            jd_text,
            client=client,
            model=model,
        )
    except Exception as e:
        return JDParseCaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            overall_score=0.0,
            failure_reasons=[f"Parser error: {e}"],
        )

    analysis = parse_result.enriched_analysis

    title_result = _score_field(
        field_name="job_title",
        expected=expectations.expected_job_title,
        actual=analysis.job_title,
        match_mode=MatchMode.EXACT,
    )

    role_family_result = _score_field(
        field_name="role_family",
        expected=expectations.expected_role_family.value
        if expectations.expected_role_family
        else None,
        actual=analysis.functional_role_family.value,
        match_mode=MatchMode.EXACT,
    )

    org_mode_result = _score_field(
        field_name="org_mode",
        expected=None,
        actual=analysis.organizational_role_mode.value,
        match_mode=MatchMode.EXACT,
    )

    seniority_result = _score_field(
        field_name="seniority",
        expected=expectations.expected_seniority.value
        if expectations.expected_seniority
        else None,
        actual=analysis.seniority_level.value if analysis.seniority_level else None,
        match_mode=MatchMode.EXACT,
    )

    must_have_skills = _score_skill_list(
        expected_skills=[
            e for e in expectations.expected_skills if e.type == "must_include"
        ],
        actual_skills=analysis.must_have_skills,
    )

    nice_to_have_skills = _score_skill_list(
        expected_skills=[
            e for e in expectations.expected_skills if e.type == "prefer_include"
        ],
        actual_skills=analysis.nice_to_have_skills,
    )

    resp_score, resp_details = _score_responsibilities(
        expectations=expectations,
        actual_clusters=analysis.primary_responsibility_clusters,
    )

    conf_score, conf_details = _score_confidence(
        expectations=expectations,
        actual_confidence=analysis.parser_confidence,
        actual_quality=analysis.jd_quality_score,
    )

    failures: list[str] = []

    if not title_result.matched:
        failures.append(
            f"title: expected={title_result.expected!r} actual={title_result.actual!r}"
        )
    if not role_family_result.matched:
        failures.append(
            f"role_family: expected={role_family_result.expected!r} actual={role_family_result.actual!r}"
        )
    if not seniority_result.matched:
        failures.append(
            f"seniority: expected={seniority_result.expected!r} actual={seniority_result.actual!r}"
        )

    must_recall = _compute_recall(must_have_skills)
    if must_recall < 0.8 and expectations.expected_skills:
        failures.append(f"must_have skills recall={must_recall:.2f}")

    nice_recall = _compute_recall(nice_to_have_skills)
    if nice_to_have_skills and nice_recall < 0.5:
        failures.append(f"nice_to_have skills recall={nice_recall:.2f}")

    if resp_score < 0.5:
        failures.append(f"responsibility clusters score={resp_score:.2f}")

    if conf_score < 0.5:
        failures.append(f"confidence score={conf_score:.2f}")

    passed = len(failures) == 0

    overall = _compute_overall_score(
        title_result,
        role_family_result,
        seniority_result,
        must_have_skills,
        nice_to_have_skills,
        resp_score,
        conf_score,
    )

    return JDParseCaseResult(
        case_id=case.case_id,
        description=case.description,
        passed=passed,
        overall_score=overall,
        title_score=title_result,
        role_family_score=role_family_result,
        org_mode_score=org_mode_result,
        seniority_score=seniority_result,
        must_have_skills=must_have_skills,
        nice_to_have_skills=nice_to_have_skills,
        responsibility_score=resp_score,
        responsibility_details=resp_details,
        confidence_score=conf_score,
        confidence_details=conf_details,
        failure_reasons=failures,
        actual_output={
            "job_title": analysis.job_title,
            "role_family": analysis.functional_role_family.value,
            "org_mode": analysis.organizational_role_mode.value,
            "seniority": analysis.seniority_level.value
            if analysis.seniority_level
            else None,
            "must_have_skills": analysis.must_have_skills,
            "nice_to_have_skills": analysis.nice_to_have_skills,
            "responsibility_clusters": analysis.primary_responsibility_clusters,
            "parser_confidence": analysis.parser_confidence,
            "jd_quality_score": analysis.jd_quality_score,
        },
    )


def _score_field(
    field_name: str,
    expected: str | None,
    actual: str | None,
    match_mode: MatchMode,
) -> FieldScore:
    """Score a single field."""
    if expected is None:
        return FieldScore(
            field_name=field_name,
            expected=None,
            actual=actual,
            matched=True,
            score=1.0,
            max_score=1.0,
            details="no expectation",
        )

    if actual is None:
        return FieldScore(
            field_name=field_name,
            expected=expected,
            actual=None,
            matched=False,
            score=0.0,
            max_score=1.0,
            details="actual is None",
        )

    actual_lower = actual.lower().strip()
    expected_lower = expected.lower().strip()

    matched = _match_value(actual_lower, expected_lower, match_mode)

    return FieldScore(
        field_name=field_name,
        expected=expected,
        actual=actual,
        matched=matched,
        score=1.0 if matched else 0.0,
        max_score=1.0,
        details=f"matched={matched}",
    )


def _match_value(actual: str, expected: str, mode: MatchMode) -> bool:
    """Match actual against expected using the specified mode."""
    actual_lower = actual.lower()
    expected_lower = expected.lower()

    if mode == MatchMode.EXACT:
        return actual_lower == expected_lower

    if mode == MatchMode.FUZZY:
        return expected_lower in actual_lower or actual_lower in expected_lower

    if mode == MatchMode.SUBSET:
        exp_tokens = set(expected_lower.split())
        act_tokens = set(actual_lower.split())
        return exp_tokens.issubset(act_tokens) if exp_tokens else True

    if mode == MatchMode.ACCEPTABLE:
        return _fuzzy_overlap(actual_lower, expected_lower) >= 0.5

    return False


def _fuzzy_overlap(a: str, b: str) -> float:
    """Compute fuzzy overlap between two strings."""
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = a_tokens & b_tokens
    return len(intersection) / min(len(a_tokens), len(b_tokens))


def _score_skill_list(
    expected_skills: list[Expectation],
    actual_skills: list[str],
) -> list[SkillScore]:
    """Score a list of skill expectations against actual skills."""
    if not expected_skills:
        return []

    actual_lower = {s.lower().strip() for s in actual_skills}
    results: list[SkillScore] = []

    for exp in expected_skills:
        exp_value = exp.value.lower().strip()

        if exp.match_mode == "fuzzy":
            matched = any(exp_value in a or a in exp_value for a in actual_lower)
        elif exp.match_mode == "subset":
            exp_tokens = set(exp_value.split())
            matched = exp_tokens.issubset(actual_lower) if exp_tokens else True
        else:
            matched = exp_value in actual_lower

        score = exp.weight if matched else 0.0
        max_score = exp.weight

        results.append(
            SkillScore(
                skill_name=exp.value,
                expected_type=exp.type,
                matched=matched,
                score=score,
                max_score=max_score,
            )
        )

    return results


def _compute_recall(skill_scores: list[SkillScore]) -> float:
    """Compute recall for skill scores."""
    if not skill_scores:
        return 1.0

    total_score = sum(s.score for s in skill_scores)
    total_max = sum(s.max_score for s in skill_scores)

    return total_score / total_max if total_max > 0 else 1.0


def _score_responsibilities(
    expectations: Phase1ParseExpectations,
    actual_clusters: list[str],
) -> tuple[float, str]:
    """Score responsibility cluster extraction."""
    if not expectations.expected_skills:
        return 1.0, "no expected responsibilities"

    skill_names = {
        e.value.lower(): e.weight
        for e in expectations.expected_skills
        if e.type in ("must_include", "prefer_include")
    }

    if not skill_names:
        return 1.0, "no skill expectations"

    matched = 0
    total = 0

    for skill, weight in skill_names.items():
        total += weight
        if any(skill in cluster.lower() for cluster in actual_clusters):
            matched += weight

    score = matched / total if total > 0 else 0.0

    return score, f"matched={matched}/{total}"


def _score_confidence(
    expectations: Phase1ParseExpectations,
    actual_confidence: float,
    actual_quality: float,
) -> tuple[float, str]:
    """Score parser confidence presence and sanity."""
    min_confidence = expectations.min_parser_confidence
    min_quality = expectations.min_quality_score

    confidence_ok = actual_confidence >= min_confidence
    quality_ok = actual_quality >= min_quality

    if confidence_ok and quality_ok:
        return 1.0, f"conf={actual_confidence:.2f} qual={actual_quality:.2f}"

    issues = []
    if not confidence_ok:
        issues.append(f"conf={actual_confidence:.2f}<{min_confidence}")
    if not quality_ok:
        issues.append(f"qual={actual_quality:.2f}<{min_quality}")

    score = 0.5 if (confidence_ok or quality_ok) else 0.0

    return score, ", ".join(issues)


def _compute_overall_score(
    title: FieldScore,
    role_family: FieldScore,
    seniority: FieldScore,
    must_have: list[SkillScore],
    nice_to_have: list[SkillScore],
    resp_score: float,
    conf_score: float,
) -> float:
    """Compute weighted overall score."""
    weights = {
        "title": 0.15,
        "role_family": 0.20,
        "seniority": 0.10,
        "must_have": 0.25,
        "nice_to_have": 0.10,
        "responsibility": 0.10,
        "confidence": 0.10,
    }

    score = 0.0

    score += weights["title"] * title.score
    score += weights["role_family"] * role_family.score
    score += weights["seniority"] * seniority.score

    must_recall = _compute_recall(must_have)
    score += weights["must_have"] * must_recall

    nice_recall = _compute_recall(nice_to_have)
    score += weights["nice_to_have"] * nice_recall

    score += weights["responsibility"] * resp_score
    score += weights["confidence"] * conf_score

    return round(score, 3)


def _build_summary(results: list[JDParseCaseResult]) -> JDParseSummary:
    """Build aggregate summary from individual results."""
    if not results:
        return JDParseSummary(
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
            title_accuracy=0.0,
            role_family_accuracy=0.0,
            org_mode_accuracy=0.0,
            seniority_accuracy=0.0,
            must_have_skill_recall=0.0,
            nice_to_have_skill_recall=0.0,
            responsibility_recall=0.0,
            average_confidence=0.0,
            case_results=[],
        )

    total = len(results)
    passed = sum(1 for r in results if r.passed)

    title_acc = _compute_field_accuracy(results, lambda r: r.title_score)
    role_acc = _compute_field_accuracy(results, lambda r: r.role_family_score)
    org_acc = _compute_field_accuracy(results, lambda r: r.org_mode_score)
    senior_acc = _compute_field_accuracy(results, lambda r: r.seniority_score)

    must_recall = sum(_compute_recall(r.must_have_skills) for r in results) / total
    nice_recall = sum(_compute_recall(r.nice_to_have_skills) for r in results) / total

    resp_recall = sum(r.responsibility_score for r in results) / total
    avg_conf = sum(r.confidence_score for r in results) / total

    return JDParseSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        title_accuracy=title_acc,
        role_family_accuracy=role_acc,
        org_mode_accuracy=org_acc,
        seniority_accuracy=senior_acc,
        must_have_skill_recall=must_recall,
        nice_to_have_skill_recall=nice_recall,
        responsibility_recall=resp_recall,
        average_confidence=avg_conf,
        case_results=results,
    )


def _compute_field_accuracy(
    results: list[JDParseCaseResult],
    field_getter,
) -> float:
    """Compute accuracy for a field across all results."""
    if not results:
        return 0.0

    matched = 0
    total = 0

    for r in results:
        field = field_getter(r)
        if field is not None:
            total += 1
            if field.matched:
                matched += 1

    return matched / total if total > 0 else 0.0


def render_jd_parse_summary(summary: JDParseSummary) -> str:
    """Render JD parse summary as human-readable text."""
    lines = [
        "=" * 50,
        "JD Parse Evaluation Summary",
        "=" * 50,
        f"Cases: {summary.total_cases} | Passed: {summary.passed_cases} | Failed: {summary.failed_cases}",
        "",
        "Field Accuracies:",
        f"  title:         {summary.title_accuracy:.2%}",
        f"  role_family:  {summary.role_family_accuracy:.2%}",
        f"  org_mode:     {summary.org_mode_accuracy:.2%}",
        f"  seniority:    {summary.seniority_accuracy:.2%}",
        "",
        "Extraction Quality:",
        f"  must_have skill recall:   {summary.must_have_skill_recall:.2%}",
        f"  nice_to_have skill recall: {summary.nice_to_have_skill_recall:.2%}",
        f"  responsibility recall:   {summary.responsibility_recall:.2%}",
        "",
        "Confidence:",
        f"  average: {summary.average_confidence:.2%}",
        "",
        "-" * 50,
        "Case Details:",
        "-" * 50,
    ]

    for result in summary.case_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"\n[{status}] {result.case_id}")
        lines.append(f"  Description: {result.description}")
        lines.append(f"  Overall: {result.overall_score:.3f}")

        if result.title_score:
            lines.append(
                f"  title: {'✓' if result.title_score.matched else '✗'} "
                f"(expected={result.title_score.expected!r}, actual={result.title_score.actual!r})"
            )
        if result.role_family_score:
            lines.append(
                f"  role_family: {'✓' if result.role_family_score.matched else '✗'}"
            )
        if result.seniority_score:
            lines.append(
                f"  seniority: {'✓' if result.seniority_score.matched else '✗'} "
                f"(expected={result.seniority_score.expected!r}, actual={result.seniority_score.actual!r})"
            )

        must_recall = _compute_recall(result.must_have_skills)
        lines.append(f"  must_have skills: {must_recall:.2%}")

        nice_recall = _compute_recall(result.nice_to_have_skills)
        if result.nice_to_have_skills:
            lines.append(f"  nice_to_have skills: {nice_recall:.2%}")

        lines.append(f"  responsibility: {result.responsibility_score:.2%}")
        lines.append(f"  confidence: {result.confidence_score:.2%}")

        if result.failure_reasons:
            lines.append("  Failures:")
            for reason in result.failure_reasons:
                lines.append(f"    - {reason}")

    return "\n".join(lines)


def render_jd_parse_summary_json(summary: JDParseSummary) -> str:
    """Render summary as JSON."""
    return json.dumps(summary, indent=2, default=lambda x: x.__dict__)
