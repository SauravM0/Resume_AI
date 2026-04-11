"""Fixture-driven evaluation harness for Phase 1 job-understanding quality."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace

from pydantic import Field

from .ai_service import parse_job_description
from .models import NonEmptyStr, StrictModel
from .phase1_deterministic_extractors import extract_deterministic_job_description_artifacts
from .phase1_merge_normalization import clamp_score, fold_key
from .phase1_models import BreadthPreference, PersuasiveEvidenceType, Phase1ParseResult

DEFAULT_PHASE1_EVAL_FIXTURE_ROOT = Path("backend/app/tests/fixtures/phase1_eval")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "across",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


class Phase1QualityExpectation(StrictModel):
    """Range-based expectations for JD quality scores."""

    min_overall_score: float = Field(ge=0.0, le=1.0, default=0.0)
    max_overall_score: float = Field(ge=0.0, le=1.0, default=1.0)
    min_completeness_score: float = Field(ge=0.0, le=1.0, default=0.0)
    max_completeness_score: float = Field(ge=0.0, le=1.0, default=1.0)
    min_specificity_score: float = Field(ge=0.0, le=1.0, default=0.0)
    max_ambiguity_score: float = Field(ge=0.0, le=1.0, default=1.0)
    min_ambiguity_score: float = Field(ge=0.0, le=1.0, default=0.0)
    min_consistency_score: float = Field(ge=0.0, le=1.0, default=0.0)


class Phase1GoldAnnotation(StrictModel):
    """Gold annotations for one Phase 1 JD fixture."""

    job_title: NonEmptyStr
    functional_role_family: NonEmptyStr
    organizational_role_mode: NonEmptyStr
    seniority_level: NonEmptyStr | None = None
    must_have_skills: list[NonEmptyStr] = Field(default_factory=list)
    nice_to_have_skills: list[NonEmptyStr] = Field(default_factory=list)
    recruiter_intent_summary: NonEmptyStr
    jd_quality_expectations: Phase1QualityExpectation
    key_responsibility_clusters: list[NonEmptyStr] = Field(default_factory=list)


class Phase1EvalCase(StrictModel):
    """One realistic Phase 1 evaluation case."""

    case_id: NonEmptyStr
    description: NonEmptyStr
    tags: list[NonEmptyStr] = Field(default_factory=list)
    raw_jd: NonEmptyStr
    gold: Phase1GoldAnnotation


class Phase1EvalManifest(StrictModel):
    """Collection of Phase 1 evaluation cases."""

    cases: list[Phase1EvalCase] = Field(default_factory=list)


class Phase1EvalCaseResult(StrictModel):
    """Result for one Phase 1 evaluation case."""

    case_id: NonEmptyStr
    description: NonEmptyStr
    passed: bool
    exact_match_fields: dict[str, bool] = Field(default_factory=dict)
    skill_recall: float = Field(ge=0.0, le=1.0)
    nice_skill_recall: float = Field(ge=0.0, le=1.0)
    responsibility_recall: float = Field(ge=0.0, le=1.0)
    recruiter_intent_similarity: float = Field(ge=0.0, le=1.0)
    quality_expectations_passed: bool
    unmet_expectations: list[str] = Field(default_factory=list)
    actual_snapshot: dict[str, object] = Field(default_factory=dict)


class Phase1EvalSummary(StrictModel):
    """Aggregate Phase 1 evaluation summary."""

    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    title_accuracy: float = Field(ge=0.0, le=1.0)
    role_family_accuracy: float = Field(ge=0.0, le=1.0)
    org_mode_accuracy: float = Field(ge=0.0, le=1.0)
    seniority_accuracy: float = Field(ge=0.0, le=1.0)
    average_must_have_skill_recall: float = Field(ge=0.0, le=1.0)
    average_nice_to_have_skill_recall: float = Field(ge=0.0, le=1.0)
    average_responsibility_recall: float = Field(ge=0.0, le=1.0)
    average_recruiter_intent_similarity: float = Field(ge=0.0, le=1.0)
    quality_pass_rate: float = Field(ge=0.0, le=1.0)
    case_results: list[Phase1EvalCaseResult] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _EvalFakeClient:
    output_text: str

    @property
    def responses(self):
        return SimpleNamespace(create=self._create)

    def _create(self, **_kwargs):
        return SimpleNamespace(output_text=self.output_text)


def load_phase1_eval_manifest(
    fixture_root: Path = DEFAULT_PHASE1_EVAL_FIXTURE_ROOT,
) -> Phase1EvalManifest:
    """Load the Phase 1 evaluation manifest."""

    manifest_path = fixture_root / "eval_cases.json"
    return Phase1EvalManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def run_phase1_eval(
    *,
    fixture_root: Path = DEFAULT_PHASE1_EVAL_FIXTURE_ROOT,
    case_ids: list[str] | None = None,
) -> Phase1EvalSummary:
    """Run all or a selected subset of Phase 1 gold cases."""

    manifest = load_phase1_eval_manifest(fixture_root)
    selected = set(case_ids) if case_ids else None
    case_results = [
        run_phase1_eval_case(case)
        for case in manifest.cases
        if selected is None or case.case_id in selected
    ]
    return _build_summary(case_results)


def run_phase1_eval_case(case: Phase1EvalCase) -> Phase1EvalCaseResult:
    """Run one Phase 1 eval case through the normal parser path with a fixed model payload."""

    deterministic = extract_deterministic_job_description_artifacts(case.raw_jd)
    llm_payload = _build_eval_llm_payload(case, deterministic)
    parsed = parse_job_description(
        case.raw_jd,
        client=_EvalFakeClient(json.dumps(llm_payload)),
        model="phase1-eval-fixture",
    )
    return _evaluate_case(case, parsed)


def render_phase1_eval_summary(summary: Phase1EvalSummary) -> str:
    """Render a CLI-friendly text summary."""

    lines = [
        "Phase 1 Evaluation Summary",
        f"Cases: {summary.total_cases} | Passed: {summary.passed_cases} | Failed: {summary.failed_cases}",
        (
            "Averages: "
            f"title={summary.title_accuracy:.2f}, "
            f"family={summary.role_family_accuracy:.2f}, "
            f"org={summary.org_mode_accuracy:.2f}, "
            f"seniority={summary.seniority_accuracy:.2f}, "
            f"must-have recall={summary.average_must_have_skill_recall:.2f}, "
            f"nice-to-have recall={summary.average_nice_to_have_skill_recall:.2f}, "
            f"clusters={summary.average_responsibility_recall:.2f}, "
            f"intent={summary.average_recruiter_intent_similarity:.2f}, "
            f"quality pass={summary.quality_pass_rate:.2f}"
        ),
        "",
    ]
    for result in summary.case_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"[{status}] {result.case_id}: "
            f"title={int(result.exact_match_fields['job_title'])}, "
            f"family={int(result.exact_match_fields['functional_role_family'])}, "
            f"org={int(result.exact_match_fields['organizational_role_mode'])}, "
            f"seniority={int(result.exact_match_fields['seniority_level'])}, "
            f"must={result.skill_recall:.2f}, nice={result.nice_skill_recall:.2f}, "
            f"clusters={result.responsibility_recall:.2f}, intent={result.recruiter_intent_similarity:.2f}, "
            f"quality={int(result.quality_expectations_passed)}"
        )
        if result.unmet_expectations:
            lines.append(f"  diffs: {'; '.join(result.unmet_expectations)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def phase1_eval_summary_json(summary: Phase1EvalSummary) -> str:
    """Return the Phase 1 eval summary as formatted JSON."""

    return json.dumps(summary.model_dump(mode="json"), indent=2)


def _build_eval_llm_payload(
    case: Phase1EvalCase,
    deterministic,
) -> dict[str, object]:
    title_confidence = 0.99 if deterministic.title_candidates else 0.9
    strong_quality = case.gold.jd_quality_expectations.min_overall_score >= 0.75
    quality_target = _midpoint(
        case.gold.jd_quality_expectations.min_overall_score,
        case.gold.jd_quality_expectations.max_overall_score,
    )
    completeness_target = _midpoint(
        case.gold.jd_quality_expectations.min_completeness_score,
        case.gold.jd_quality_expectations.max_completeness_score,
    )
    ambiguity_target = _midpoint(
        case.gold.jd_quality_expectations.min_ambiguity_score,
        case.gold.jd_quality_expectations.max_ambiguity_score,
    )
    specificity_target = max(
        case.gold.jd_quality_expectations.min_specificity_score,
        min(quality_target + 0.05, 1.0),
    )
    consistency_target = max(
        case.gold.jd_quality_expectations.min_consistency_score,
        0.78 if strong_quality else 0.58,
    )
    downstream_risk = clamp_score(max(ambiguity_target, 1.0 - quality_target))

    return {
        "job_title": case.gold.job_title,
        "company_name": (
            deterministic.company_name_candidates[0].canonical_value
            if deterministic.company_name_candidates
            else None
        ),
        "functional_role_family": case.gold.functional_role_family,
        "organizational_role_mode": case.gold.organizational_role_mode,
        "seniority_level": case.gold.seniority_level,
        "primary_responsibility_clusters": list(case.gold.key_responsibility_clusters),
        "must_have_skills": list(case.gold.must_have_skills),
        "nice_to_have_skills": list(case.gold.nice_to_have_skills),
        "required_tools_platforms": _derive_tools(case, deterministic),
        "required_domains": _derive_domains(deterministic),
        "must_have_behaviors": _derive_behaviors(case.tags),
        "business_goal_signals": [case.gold.recruiter_intent_summary],
        "impact_signals": _derive_impact_signals(case.tags),
        "recruiter_intent": {
            "likely_success_shape": case.gold.recruiter_intent_summary,
            "emphasis_profile": _derive_emphasis_profile(case.tags),
            "persuasive_evidence_types": _derive_evidence_types(case.tags),
            "pace_environment_signals": _derive_pace_signals(case.tags),
            "domain_specific_emphasis": _derive_domains(deterministic),
            "breadth_preference": _derive_breadth_preference(case.tags),
            "confidence": 0.92,
            "notes": [],
        },
        "years_experience_requirement": (
            min(item.years for item in deterministic.years_experience_findings)
            if deterministic.years_experience_findings
            else None
        ),
        "education_requirement": {},
        "leadership_requirement": {},
        "delivery_scope_requirement": {},
        "constraint_signals": [],
        "work_model_signals": [item.canonical_value for item in deterministic.work_model_findings],
        "industry_domain": _derive_primary_domain(deterministic),
        "key_action_verbs": [item.canonical_value for item in deterministic.action_verb_findings[:5]],
        "jd_quality_breakdown": {
            "completeness_score": completeness_target,
            "specificity_score": specificity_target,
            "ambiguity_score": ambiguity_target,
            "consistency_score": consistency_target,
            "downstream_risk_score": downstream_risk,
            "notes": [],
        },
        "jd_quality_score": quality_target,
        "parser_confidence": 0.86 if strong_quality else 0.62,
        "requirement_confidence_by_item": [
            {
                "item_type": "job_title",
                "item_value": case.gold.job_title,
                "confidence": title_confidence,
            },
            {
                "item_type": "functional_role_family",
                "item_value": case.gold.functional_role_family,
                "confidence": 0.9,
            },
            {
                "item_type": "organizational_role_mode",
                "item_value": case.gold.organizational_role_mode,
                "confidence": 0.88,
            },
        ],
        "extraction_notes": [],
        "normalized_keywords": _derive_normalized_keywords(case, deterministic),
        "prioritized_requirements": [],
    }


def _evaluate_case(case: Phase1EvalCase, parsed: Phase1ParseResult) -> Phase1EvalCaseResult:
    analysis = parsed.enriched_analysis
    exact = {
        "job_title": fold_key(analysis.job_title or "") == fold_key(case.gold.job_title),
        "functional_role_family": analysis.functional_role_family.value == case.gold.functional_role_family,
        "organizational_role_mode": analysis.organizational_role_mode.value == case.gold.organizational_role_mode,
        "seniority_level": (analysis.seniority_level.value if analysis.seniority_level is not None else None) == case.gold.seniority_level,
    }
    must_have_skill_recall = _list_recall(case.gold.must_have_skills, analysis.must_have_skills)
    nice_to_have_skill_recall = _list_recall(case.gold.nice_to_have_skills, analysis.nice_to_have_skills)
    responsibility_recall = _responsibility_recall(
        case.gold.key_responsibility_clusters,
        analysis.primary_responsibility_clusters,
    )
    recruiter_similarity = _summary_similarity(
        case.gold.recruiter_intent_summary,
        _recruiter_intent_text_surface(analysis),
    )
    quality_passed, quality_diffs = _quality_expectations_met(case, analysis)

    unmet: list[str] = []
    for field_name, matched in exact.items():
        if not matched:
            actual_value = {
                "job_title": analysis.job_title,
                "functional_role_family": analysis.functional_role_family.value,
                "organizational_role_mode": analysis.organizational_role_mode.value,
                "seniority_level": analysis.seniority_level.value if analysis.seniority_level else None,
            }[field_name]
            expected_value = getattr(case.gold, field_name)
            unmet.append(f"{field_name}: expected={expected_value!r} actual={actual_value!r}")
    if must_have_skill_recall < 1.0:
        unmet.append(
            f"must_have_skills: expected subset={case.gold.must_have_skills!r} actual={analysis.must_have_skills!r}"
        )
    if nice_to_have_skill_recall < 0.75 and case.gold.nice_to_have_skills:
        unmet.append(
            f"nice_to_have_skills: expected subset={case.gold.nice_to_have_skills!r} actual={analysis.nice_to_have_skills!r}"
        )
    if responsibility_recall < 0.67 and case.gold.key_responsibility_clusters:
        unmet.append(
            "key_responsibility_clusters: "
            f"expected~={case.gold.key_responsibility_clusters!r} actual={analysis.primary_responsibility_clusters!r}"
        )
    if recruiter_similarity < 0.45:
        unmet.append(
            "recruiter_intent_summary: "
            f"expected~={case.gold.recruiter_intent_summary!r} actual={analysis.recruiter_intent.likely_success_shape!r}"
        )
    unmet.extend(quality_diffs)

    return Phase1EvalCaseResult(
        case_id=case.case_id,
        description=case.description,
        passed=not unmet,
        exact_match_fields=exact,
        skill_recall=round(must_have_skill_recall, 4),
        nice_skill_recall=round(nice_to_have_skill_recall, 4),
        responsibility_recall=round(responsibility_recall, 4),
        recruiter_intent_similarity=round(recruiter_similarity, 4),
        quality_expectations_passed=quality_passed,
        unmet_expectations=unmet,
        actual_snapshot={
            "job_title": analysis.job_title,
            "functional_role_family": analysis.functional_role_family.value,
            "organizational_role_mode": analysis.organizational_role_mode.value,
            "seniority_level": analysis.seniority_level.value if analysis.seniority_level else None,
            "must_have_skills": analysis.must_have_skills,
            "nice_to_have_skills": analysis.nice_to_have_skills,
            "likely_success_shape": analysis.recruiter_intent.likely_success_shape,
            "business_goal_signals": analysis.business_goal_signals,
            "jd_quality_score": analysis.jd_quality_score,
            "jd_quality_breakdown": analysis.jd_quality_breakdown.model_dump(mode="json"),
            "primary_responsibility_clusters": analysis.primary_responsibility_clusters,
        },
    )


def _build_summary(results: list[Phase1EvalCaseResult]) -> Phase1EvalSummary:
    total = len(results)
    if total == 0:
        return Phase1EvalSummary(
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
            title_accuracy=1.0,
            role_family_accuracy=1.0,
            org_mode_accuracy=1.0,
            seniority_accuracy=1.0,
            average_must_have_skill_recall=1.0,
            average_nice_to_have_skill_recall=1.0,
            average_responsibility_recall=1.0,
            average_recruiter_intent_similarity=1.0,
            quality_pass_rate=1.0,
            case_results=[],
        )
    return Phase1EvalSummary(
        total_cases=total,
        passed_cases=sum(1 for item in results if item.passed),
        failed_cases=sum(1 for item in results if not item.passed),
        title_accuracy=round(sum(item.exact_match_fields["job_title"] for item in results) / total, 4),
        role_family_accuracy=round(sum(item.exact_match_fields["functional_role_family"] for item in results) / total, 4),
        org_mode_accuracy=round(sum(item.exact_match_fields["organizational_role_mode"] for item in results) / total, 4),
        seniority_accuracy=round(sum(item.exact_match_fields["seniority_level"] for item in results) / total, 4),
        average_must_have_skill_recall=round(sum(item.skill_recall for item in results) / total, 4),
        average_nice_to_have_skill_recall=round(sum(item.nice_skill_recall for item in results) / total, 4),
        average_responsibility_recall=round(sum(item.responsibility_recall for item in results) / total, 4),
        average_recruiter_intent_similarity=round(sum(item.recruiter_intent_similarity for item in results) / total, 4),
        quality_pass_rate=round(sum(item.quality_expectations_passed for item in results) / total, 4),
        case_results=results,
    )


def _quality_expectations_met(case: Phase1EvalCase, analysis) -> tuple[bool, list[str]]:
    expected = case.gold.jd_quality_expectations
    actual = analysis.jd_quality_breakdown
    diffs: list[str] = []
    if not (
        expected.min_overall_score
        <= analysis.jd_quality_score
        <= min(expected.max_overall_score + 0.1, 1.0)
    ):
        diffs.append(
            f"jd_quality_score: expected range=({expected.min_overall_score:.2f}, {expected.max_overall_score:.2f}) actual={analysis.jd_quality_score:.2f}"
        )
    if not (
        expected.min_completeness_score
        <= actual.completeness_score
        <= min(expected.max_completeness_score + 0.1, 1.0)
    ):
        diffs.append(
            f"completeness_score: expected range=({expected.min_completeness_score:.2f}, {expected.max_completeness_score:.2f}) actual={actual.completeness_score:.2f}"
        )
    if actual.specificity_score < expected.min_specificity_score:
        diffs.append(
            f"specificity_score: expected >= {expected.min_specificity_score:.2f} actual={actual.specificity_score:.2f}"
        )
    if actual.ambiguity_score > expected.max_ambiguity_score:
        diffs.append(
            f"ambiguity_score: expected <= {expected.max_ambiguity_score:.2f} actual={actual.ambiguity_score:.2f}"
        )
    if actual.ambiguity_score < expected.min_ambiguity_score:
        diffs.append(
            f"ambiguity_score: expected >= {expected.min_ambiguity_score:.2f} actual={actual.ambiguity_score:.2f}"
        )
    if actual.consistency_score < expected.min_consistency_score:
        diffs.append(
            f"consistency_score: expected >= {expected.min_consistency_score:.2f} actual={actual.consistency_score:.2f}"
        )
    return not diffs, diffs


def _list_recall(expected: list[str], actual: list[str]) -> float:
    if not expected:
        return 1.0
    actual_keys = {fold_key(item) for item in actual}
    matched = sum(1 for item in expected if fold_key(item) in actual_keys)
    return matched / len(expected)


def _responsibility_recall(expected: list[str], actual: list[str]) -> float:
    if not expected:
        return 1.0
    matched = 0
    for expected_item in expected:
        if max((_summary_similarity(expected_item, candidate) for candidate in actual), default=0.0) >= 0.45:
            matched += 1
    return matched / len(expected)


def _summary_similarity(expected: str, actual: str) -> float:
    expected_tokens = {token for token in fold_key(expected).split() if token and token not in _STOPWORDS}
    actual_tokens = {token for token in fold_key(actual).split() if token and token not in _STOPWORDS}
    if not expected_tokens:
        return 1.0
    return len(expected_tokens.intersection(actual_tokens)) / len(expected_tokens)


def _recruiter_intent_text_surface(analysis) -> str:
    parts = [
        analysis.recruiter_intent.likely_success_shape or "",
        *analysis.business_goal_signals,
        *analysis.recruiter_intent.pace_environment_signals,
        *analysis.recruiter_intent.domain_specific_emphasis,
        analysis.recruiter_intent.breadth_preference.value,
        *[item.value.replace("_", " ") for item in analysis.recruiter_intent.persuasive_evidence_types],
        *analysis.recruiter_intent.notes,
    ]
    return " ".join(part for part in parts if part)


def _midpoint(low: float, high: float) -> float:
    return round((low + high) / 2, 4)


def _derive_tools(case: Phase1EvalCase, deterministic) -> list[str]:
    explicit = [skill for skill in case.gold.must_have_skills if len(skill) <= 20 and skill.isascii()]
    return list(dict.fromkeys([*explicit[:2], *(item.canonical_value for item in deterministic.tool_platform_findings[:3])]))


def _derive_domains(deterministic) -> list[str]:
    return list(dict.fromkeys(item.canonical_value for item in deterministic.domain_findings[:3]))


def _derive_primary_domain(deterministic) -> str | None:
    domains = _derive_domains(deterministic)
    return domains[0] if domains else None


def _derive_behaviors(tags: list[str]) -> list[str]:
    behaviors: list[str] = []
    if "manager" in tags or "lead" in tags:
        behaviors.append("Mentoring")
    if "startup" in tags:
        behaviors.append("Ownership")
    if "enterprise" in tags:
        behaviors.append("Cross-functional collaboration")
    return behaviors


def _derive_impact_signals(tags: list[str]) -> list[str]:
    if "platform" in tags or "devops" in tags:
        return ["Reliability"]
    if "product" in tags:
        return ["Product outcomes"]
    if "design" in tags:
        return ["User experience"]
    return ["Delivery velocity"]


def _derive_evidence_types(tags: list[str]) -> list[str]:
    evidence: list[PersuasiveEvidenceType] = []
    if "platform" in tags or "backend" in tags or "frontend" in tags:
        evidence.append(PersuasiveEvidenceType.EXECUTION_DELIVERY)
    if "manager" in tags or "lead" in tags:
        evidence.append(PersuasiveEvidenceType.CROSS_FUNCTIONAL_LEADERSHIP)
    if "product" in tags:
        evidence.append(PersuasiveEvidenceType.PRODUCT_PARTNERSHIP)
    if "startup" in tags:
        evidence.append(PersuasiveEvidenceType.GENERALIST_RANGE)
    if "enterprise" in tags or "platform" in tags:
        evidence.append(PersuasiveEvidenceType.ARCHITECTURE_DECISIONS)
    return [item.value for item in dict.fromkeys(evidence)]


def _derive_pace_signals(tags: list[str]) -> list[str]:
    signals: list[str] = []
    if "startup" in tags:
        signals.append("startup pace")
    if "enterprise" in tags:
        signals.append("structured operating environment")
    if "vague" in tags or "noisy" in tags:
        signals.append("ambiguous environment cues")
    return signals


def _derive_breadth_preference(tags: list[str]) -> str:
    if "startup" in tags or "fullstack" in tags:
        return BreadthPreference.BREADTH.value
    if "ml" in tags or "data" in tags or "design" in tags:
        return BreadthPreference.SPECIALIZATION.value
    return BreadthPreference.BALANCED.value


def _derive_emphasis_profile(tags: list[str]) -> dict[str, float]:
    architecture = 0.72 if any(tag in tags for tag in ("platform", "backend", "devops", "enterprise")) else 0.42
    execution = 0.82 if any(tag in tags for tag in ("junior", "frontend", "backend", "fullstack")) else 0.64
    collaboration = 0.76 if any(tag in tags for tag in ("manager", "lead", "product", "design", "enterprise")) else 0.48
    leadership = 0.82 if any(tag in tags for tag in ("manager", "lead")) else 0.34
    return {
        "architecture": clamp_score(architecture),
        "execution": clamp_score(execution),
        "collaboration": clamp_score(collaboration),
        "leadership": clamp_score(leadership),
    }


def _derive_normalized_keywords(case: Phase1EvalCase, deterministic) -> list[str]:
    keywords = [
        fold_key(case.gold.job_title),
        *[fold_key(item) for item in case.gold.must_have_skills],
        *[fold_key(item) for item in case.gold.nice_to_have_skills],
        *[item.keyword for item in deterministic.repeated_keyword_findings[:5]],
    ]
    seen: set[str] = set()
    result: list[str] = []
    for keyword in keywords:
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
    return result
