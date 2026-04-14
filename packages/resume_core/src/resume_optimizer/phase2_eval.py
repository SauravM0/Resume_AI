"""Repeatable evaluation harness for Phase 2 ranking, selection, and explainability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path

from pydantic import Field, ValidationError

from .job_feature_adapter import adapt_job_analysis_to_ranking_features
from .job_models import NormalizedJobAnalysis
from .loaders import load_and_normalize_master_profile
from .models import NonEmptyStr, StrictModel
from .phase2_models import Phase2Status, RankingExplanation
from .services.phase2_service import Phase2Service

DEFAULT_PHASE2_EVAL_FIXTURE_ROOT = Path("backend/app/tests/fixtures/phase2_eval")


class Phase2EvalFixtureError(ValueError):
    """Raised when the Phase 2 eval fixture pack is missing or malformed."""

    pass


class Phase2EvalExpectation(StrictModel):
    """Sanity expectations for one eval case used to catch regressions."""

    allowed_statuses: list[Phase2Status] = Field(
        default_factory=lambda: [Phase2Status.SUCCESS, Phase2Status.PARTIAL]
    )
    require_nonempty_selection: bool = True
    min_selected_item_count: int = Field(default=1, ge=0)
    min_must_have_skill_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    min_provenance_completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    min_explanation_completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    min_selection_diversity: float = Field(default=0.0, ge=0.0, le=1.0)
    min_duplicate_suppression: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_top_experience_source_ids: list[NonEmptyStr] = Field(default_factory=list)
    expected_top_project_source_ids: list[NonEmptyStr] = Field(default_factory=list)
    expected_top_certification_ids: list[NonEmptyStr] = Field(default_factory=list)
    required_selected_skill_names: list[NonEmptyStr] = Field(default_factory=list)
    required_selected_project_source_ids: list[NonEmptyStr] = Field(
        default_factory=list
    )
    forbidden_experience_source_ids: list[NonEmptyStr] = Field(default_factory=list)
    required_warning_signals: list[NonEmptyStr] = Field(default_factory=list)
    forbidden_warning_signals: list[NonEmptyStr] = Field(default_factory=list)
    max_duplicate_selected_count: int | None = Field(default=None, ge=0)
    max_diagnostic_warning_count: int | None = Field(default=None, ge=0)


class Phase2EvalCase(StrictModel):
    """One profile x job-analysis evaluation case loaded from fixture data."""

    case_id: NonEmptyStr
    description: NonEmptyStr
    profile_fixture: NonEmptyStr
    job_analysis_fixture: NonEmptyStr
    expectation: Phase2EvalExpectation = Field(default_factory=Phase2EvalExpectation)


class Phase2EvalManifest(StrictModel):
    """Collection of evaluation cases executed by the batch harness."""

    cases: list[Phase2EvalCase] = Field(default_factory=list)


class Phase2EvalCaseResult(StrictModel):
    """Per-case evaluation metrics and expectation outcomes."""

    case_id: NonEmptyStr
    description: NonEmptyStr
    passed: bool
    diagnostic_status: Phase2Status
    selected_item_count: int = Field(ge=0)
    top_n_relevance_sanity: float = Field(ge=0.0, le=1.0)
    must_have_skill_coverage: float = Field(ge=0.0, le=1.0)
    selection_diversity: float = Field(ge=0.0, le=1.0)
    duplicate_suppression: float = Field(ge=0.0, le=1.0)
    provenance_completeness: float = Field(ge=0.0, le=1.0)
    explanation_completeness: float = Field(ge=0.0, le=1.0)
    duplicate_selected_count: int = Field(ge=0)
    diagnostic_warning_count: int = Field(ge=0)
    top_experience_source_ids: list[str] = Field(default_factory=list)
    top_project_source_ids: list[str] = Field(default_factory=list)
    top_certification_ids: list[str] = Field(default_factory=list)
    selected_skill_names: list[str] = Field(default_factory=list)
    warning_signals: list[str] = Field(default_factory=list)
    unmet_expectations: list[str] = Field(default_factory=list)


class Phase2EvalSummary(StrictModel):
    """Batch evaluation summary with aggregate metrics and per-case results."""

    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    average_top_n_relevance_sanity: float = Field(ge=0.0, le=1.0)
    average_must_have_skill_coverage: float = Field(ge=0.0, le=1.0)
    average_selection_diversity: float = Field(ge=0.0, le=1.0)
    average_duplicate_suppression: float = Field(ge=0.0, le=1.0)
    average_provenance_completeness: float = Field(ge=0.0, le=1.0)
    average_explanation_completeness: float = Field(ge=0.0, le=1.0)
    case_results: list[Phase2EvalCaseResult] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _SelectedEvalItem:
    source_item_id: str | None
    item_id: str
    warning_signals: list[str]
    provenance: dict[str, object]
    ranking_explanation: RankingExplanation


def load_phase2_eval_manifest(
    fixture_root: Path = DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
) -> Phase2EvalManifest:
    """Load the Phase 2 eval manifest from fixture JSON."""

    fixture_root = Path(fixture_root)
    manifest_path = fixture_root / "eval_cases.json"
    if not fixture_root.exists():
        raise Phase2EvalFixtureError(
            f"Phase 2 eval fixture root does not exist: {fixture_root}"
        )
    if not fixture_root.is_dir():
        raise Phase2EvalFixtureError(
            f"Phase 2 eval fixture root is not a directory: {fixture_root}"
        )
    if not manifest_path.exists():
        raise Phase2EvalFixtureError(
            f"Phase 2 eval manifest not found: {manifest_path}. "
            "Expected eval_cases.json under the fixture root."
        )
    try:
        manifest = Phase2EvalManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise Phase2EvalFixtureError(
            f"Failed to load Phase 2 eval manifest at {manifest_path}: {exc}"
        ) from exc

    validate_phase2_eval_fixtures(manifest, fixture_root)
    return manifest


def run_phase2_eval(
    *,
    fixture_root: Path = DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
    case_ids: list[str] | None = None,
    today: date | None = None,
) -> Phase2EvalSummary:
    """Execute the Phase 2 eval matrix and return aggregate metrics."""

    manifest = load_phase2_eval_manifest(fixture_root)
    requested_case_ids = set(case_ids) if case_ids is not None else None
    known_case_ids = {case.case_id for case in manifest.cases}
    if requested_case_ids is not None:
        missing_case_ids = sorted(requested_case_ids - known_case_ids)
        if missing_case_ids:
            raise Phase2EvalFixtureError(
                "Unknown Phase 2 eval case id(s): "
                + ", ".join(missing_case_ids)
                + f". Available cases: {', '.join(sorted(known_case_ids))}"
            )
    selected_cases = [
        case
        for case in manifest.cases
        if requested_case_ids is None or case.case_id in requested_case_ids
    ]
    case_results = [
        run_phase2_eval_case(case, fixture_root=fixture_root, today=today)
        for case in selected_cases
    ]
    return _build_summary(case_results)


def run_phase2_eval_case(
    case: Phase2EvalCase,
    *,
    fixture_root: Path = DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
    today: date | None = None,
) -> Phase2EvalCaseResult:
    """Run one eval case against the full Phase 2 service path."""

    fixture_root = Path(fixture_root)
    profile_path = fixture_root / case.profile_fixture
    job_analysis_path = fixture_root / case.job_analysis_fixture
    profile = load_and_normalize_master_profile(profile_path)
    try:
        job_analysis = NormalizedJobAnalysis.model_validate_json(
            job_analysis_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise Phase2EvalFixtureError(
            f"Failed to load job analysis fixture for case '{case.case_id}' at {job_analysis_path}: {exc}"
        ) from exc
    job_features = adapt_job_analysis_to_ranking_features(job_analysis)
    service_result = Phase2Service().run(
        job_analysis, source_profile=profile, today=today
    )

    selected_items = _selected_items(service_result)
    top_experience_source_ids = [
        item.source_item_id
        for item in service_result.ranking_response.ranked_experiences[:3]
        if item.source_item_id is not None
    ]
    top_project_source_ids = [
        item.source_item_id
        for item in service_result.ranking_response.ranked_projects[:3]
        if item.source_item_id is not None
    ]
    top_certification_ids = [
        item.source_item_id
        for item in service_result.ranking_response.ranked_certifications[:2]
        if item.source_item_id is not None
    ]
    selected_skill_names = [
        item.skill_name for item in service_result.phase2_result.selected_skills
    ]
    warning_signals = _dedupe(
        signal for item in selected_items for signal in item.warning_signals
    )

    metrics = {
        "selected_item_count": len(selected_items),
        "top_n_relevance_sanity": _top_n_relevance_sanity(service_result),
        "must_have_skill_coverage": _must_have_skill_coverage(
            selected_items,
            selected_skill_names,
            job_features.canonical_must_have_skills.values,
        ),
        "selection_diversity": _selection_diversity(selected_items),
        "duplicate_suppression": _duplicate_suppression(selected_items),
        "provenance_completeness": _provenance_completeness(selected_items),
        "explanation_completeness": _explanation_completeness(selected_items),
        "duplicate_selected_count": sum(
            1
            for item in selected_items
            if "duplicate_or_near_duplicate" in item.warning_signals
        ),
        "diagnostic_warning_count": len(
            service_result.phase2_result.diagnostics.warnings
        ),
    }
    result = Phase2EvalCaseResult(
        case_id=case.case_id,
        description=case.description,
        passed=False,
        diagnostic_status=service_result.phase2_result.diagnostics.status,
        top_experience_source_ids=top_experience_source_ids,
        top_project_source_ids=top_project_source_ids,
        top_certification_ids=top_certification_ids,
        selected_skill_names=selected_skill_names,
        warning_signals=warning_signals,
        **metrics,
    )
    unmet_expectations = _evaluate_expectations(case.expectation, result)
    return result.model_copy(
        update={
            "passed": not unmet_expectations,
            "unmet_expectations": unmet_expectations,
        }
    )


def render_phase2_eval_summary(summary: Phase2EvalSummary) -> str:
    """Render a developer-readable Phase 2 evaluation report."""

    lines = [
        "Phase 2 Evaluation Summary",
        f"Cases: {summary.total_cases} | Passed: {summary.passed_cases} | Failed: {summary.failed_cases}",
        (
            "Averages: "
            f"top-N sanity={summary.average_top_n_relevance_sanity:.2f}, "
            f"must-have coverage={summary.average_must_have_skill_coverage:.2f}, "
            f"diversity={summary.average_selection_diversity:.2f}, "
            f"duplicate suppression={summary.average_duplicate_suppression:.2f}, "
            f"provenance={summary.average_provenance_completeness:.2f}, "
            f"explanations={summary.average_explanation_completeness:.2f}"
        ),
        "",
    ]
    for result in summary.case_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"[{status}] {result.case_id}: selected={result.selected_item_count}, "
            f"coverage={result.must_have_skill_coverage:.2f}, "
            f"diversity={result.selection_diversity:.2f}, "
            f"duplicates={result.duplicate_selected_count}, "
            f"warnings={result.diagnostic_warning_count}"
        )
        if result.top_experience_source_ids:
            lines.append(
                f"  top experiences: {', '.join(result.top_experience_source_ids)}"
            )
        if result.top_project_source_ids:
            lines.append(f"  top projects: {', '.join(result.top_project_source_ids)}")
        if result.selected_skill_names:
            lines.append(f"  selected skills: {', '.join(result.selected_skill_names)}")
        if result.warning_signals:
            lines.append(f"  warning signals: {', '.join(result.warning_signals)}")
        if result.unmet_expectations:
            lines.append(
                f"  unmet expectations: {'; '.join(result.unmet_expectations)}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def phase2_eval_summary_json(summary: Phase2EvalSummary) -> str:
    """Return the eval summary as formatted JSON for scripting and CI output."""

    return json.dumps(summary.model_dump(mode="json"), indent=2)


def _selected_items(service_result) -> list[_SelectedEvalItem]:
    items: list[_SelectedEvalItem] = []
    for ranked_item in (
        service_result.ranking_response.ranked_experiences
        + service_result.ranking_response.ranked_projects
        + service_result.ranking_response.ranked_certifications
    ):
        items.append(
            _SelectedEvalItem(
                source_item_id=ranked_item.source_item_id,
                item_id=ranked_item.id,
                warning_signals=ranked_item.ranking_explanation.warning_signals,
                provenance=ranked_item.provenance,
                ranking_explanation=ranked_item.ranking_explanation,
            )
        )

    for selected_skill in service_result.phase2_result.selected_skills:
        items.append(
            _SelectedEvalItem(
                source_item_id=selected_skill.source_item_id,
                item_id=selected_skill.id,
                warning_signals=selected_skill.ranking_explanation.warning_signals,
                provenance=selected_skill.provenance,
                ranking_explanation=selected_skill.ranking_explanation,
            )
        )
    return items


def _top_n_relevance_sanity(service_result) -> float:
    sections = [
        service_result.ranking_response.ranked_experiences,
        service_result.ranking_response.ranked_projects,
        service_result.ranking_response.ranked_certifications,
    ]
    checks = []
    for items in sections:
        if not items:
            continue
        descending = all(
            items[index].relevance_score >= items[index + 1].relevance_score
            for index in range(len(items) - 1)
        )
        checks.append(1.0 if descending and items[0].relevance_score > 0 else 0.0)
    return round(sum(checks) / len(checks), 4) if checks else 1.0


def _must_have_skill_coverage(
    selected_items: list[_SelectedEvalItem],
    selected_skill_names: list[str],
    must_have_skills: list[str],
) -> float:
    if not must_have_skills:
        return 1.0
    matched = {
        skill
        for item in selected_items
        for skill in item.ranking_explanation.matched_required_skills
    }
    matched.update(skill for skill in selected_skill_names if skill in must_have_skills)
    return round(
        len(matched.intersection(must_have_skills)) / len(set(must_have_skills)), 4
    )


def _selection_diversity(selected_items: list[_SelectedEvalItem]) -> float:
    if not selected_items:
        return 1.0
    distinct_sources = {
        item.source_item_id
        for item in selected_items
        if item.source_item_id is not None
    }
    return round(len(distinct_sources) / len(selected_items), 4)


def _duplicate_suppression(selected_items: list[_SelectedEvalItem]) -> float:
    if not selected_items:
        return 1.0
    duplicate_count = sum(
        1
        for item in selected_items
        if "duplicate_or_near_duplicate" in item.warning_signals
    )
    return round(1.0 - (duplicate_count / len(selected_items)), 4)


def _provenance_completeness(selected_items: list[_SelectedEvalItem]) -> float:
    if not selected_items:
        return 1.0
    complete_count = 0
    for item in selected_items:
        if not item.provenance:
            continue
        if item.provenance.get("source_entity_id") or item.provenance.get(
            "source_item_id"
        ):
            complete_count += 1
    return round(complete_count / len(selected_items), 4)


def _explanation_completeness(selected_items: list[_SelectedEvalItem]) -> float:
    if not selected_items:
        return 1.0
    complete_count = 0
    for item in selected_items:
        explanation = item.ranking_explanation
        if explanation.summary and (
            explanation.explanation_fragments
            or explanation.matched_keywords
            or explanation.signal_labels
        ):
            complete_count += 1
    return round(complete_count / len(selected_items), 4)


def _evaluate_expectations(
    expectation: Phase2EvalExpectation,
    result: Phase2EvalCaseResult,
) -> list[str]:
    failures: list[str] = []
    if result.diagnostic_status not in expectation.allowed_statuses:
        failures.append(f"diagnostic status {result.diagnostic_status} not allowed")
    if expectation.require_nonempty_selection and result.selected_item_count == 0:
        failures.append("selection was unexpectedly empty")
    if result.selected_item_count < expectation.min_selected_item_count:
        failures.append(
            f"selected item count {result.selected_item_count} below {expectation.min_selected_item_count}"
        )
    if result.must_have_skill_coverage < expectation.min_must_have_skill_coverage:
        failures.append(
            f"must-have coverage {result.must_have_skill_coverage:.2f} below {expectation.min_must_have_skill_coverage:.2f}"
        )
    if result.provenance_completeness < expectation.min_provenance_completeness:
        failures.append(
            f"provenance completeness {result.provenance_completeness:.2f} below {expectation.min_provenance_completeness:.2f}"
        )
    if result.explanation_completeness < expectation.min_explanation_completeness:
        failures.append(
            f"explanation completeness {result.explanation_completeness:.2f} below {expectation.min_explanation_completeness:.2f}"
        )
    if result.selection_diversity < expectation.min_selection_diversity:
        failures.append(
            f"selection diversity {result.selection_diversity:.2f} below {expectation.min_selection_diversity:.2f}"
        )
    if result.duplicate_suppression < expectation.min_duplicate_suppression:
        failures.append(
            f"duplicate suppression {result.duplicate_suppression:.2f} below {expectation.min_duplicate_suppression:.2f}"
        )
    if expectation.max_duplicate_selected_count is not None and (
        result.duplicate_selected_count > expectation.max_duplicate_selected_count
    ):
        failures.append(
            f"duplicate selected count {result.duplicate_selected_count} exceeds {expectation.max_duplicate_selected_count}"
        )
    if expectation.max_diagnostic_warning_count is not None and (
        result.diagnostic_warning_count > expectation.max_diagnostic_warning_count
    ):
        failures.append(
            f"diagnostic warning count {result.diagnostic_warning_count} exceeds {expectation.max_diagnostic_warning_count}"
        )

    failures.extend(
        _expected_prefix_failures(
            "top experience ids",
            expectation.expected_top_experience_source_ids,
            result.top_experience_source_ids,
        )
    )
    failures.extend(
        _expected_prefix_failures(
            "top project ids",
            expectation.expected_top_project_source_ids,
            result.top_project_source_ids,
        )
    )
    failures.extend(
        _expected_prefix_failures(
            "top certification ids",
            expectation.expected_top_certification_ids,
            result.top_certification_ids,
        )
    )

    # New expectations: required selected projects
    missing_projects = sorted(
        set(expectation.required_selected_project_source_ids)
        - set(result.top_project_source_ids)
    )
    if missing_projects:
        failures.append("missing selected projects: " + ", ".join(missing_projects))

    # New expectations: forbidden experiences
    present_forbidden_exp = sorted(
        set(expectation.forbidden_experience_source_ids).intersection(
            set(result.top_experience_source_ids)
        )
    )
    if present_forbidden_exp:
        failures.append(
            "forbidden experiences present: " + ", ".join(present_forbidden_exp)
        )

    missing_skills = sorted(
        set(expectation.required_selected_skill_names)
        - set(result.selected_skill_names)
    )
    if missing_skills:
        failures.append("missing selected skills: " + ", ".join(missing_skills))

    missing_warnings = sorted(
        set(expectation.required_warning_signals) - set(result.warning_signals)
    )
    if missing_warnings:
        failures.append("missing warning signals: " + ", ".join(missing_warnings))

    present_forbidden = sorted(
        set(expectation.forbidden_warning_signals).intersection(result.warning_signals)
    )
    if present_forbidden:
        failures.append(
            "forbidden warning signals present: " + ", ".join(present_forbidden)
        )
    return failures


def _expected_prefix_failures(
    label: str, expected: list[str], actual: list[str]
) -> list[str]:
    if not expected:
        return []
    if actual[: len(expected)] != expected:
        return [
            f"{label} mismatch: expected prefix {expected}, got {actual[: len(expected)]}"
        ]
    return []


def _build_summary(case_results: list[Phase2EvalCaseResult]) -> Phase2EvalSummary:
    total = len(case_results)
    passed = sum(1 for item in case_results if item.passed)
    return Phase2EvalSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        average_top_n_relevance_sanity=_average(
            item.top_n_relevance_sanity for item in case_results
        ),
        average_must_have_skill_coverage=_average(
            item.must_have_skill_coverage for item in case_results
        ),
        average_selection_diversity=_average(
            item.selection_diversity for item in case_results
        ),
        average_duplicate_suppression=_average(
            item.duplicate_suppression for item in case_results
        ),
        average_provenance_completeness=_average(
            item.provenance_completeness for item in case_results
        ),
        average_explanation_completeness=_average(
            item.explanation_completeness for item in case_results
        ),
        case_results=case_results,
    )


def _average(values) -> float:
    values = list(values)
    if not values:
        return 1.0
    return round(sum(values) / len(values), 4)


def _dedupe(values) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def validate_phase2_eval_fixtures(
    manifest: Phase2EvalManifest,
    fixture_root: Path = DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
) -> None:
    """Validate that the manifest and referenced fixture files are present and parseable."""

    fixture_root = Path(fixture_root)
    errors: list[str] = []
    if not manifest.cases:
        errors.append("Phase 2 eval manifest defines no cases.")

    seen_case_ids: set[str] = set()
    for case in manifest.cases:
        if case.case_id in seen_case_ids:
            errors.append(f"Duplicate case_id in Phase 2 eval manifest: {case.case_id}")
        seen_case_ids.add(case.case_id)

        profile_path = fixture_root / case.profile_fixture
        job_analysis_path = fixture_root / case.job_analysis_fixture

        if not profile_path.exists():
            errors.append(
                f"Case '{case.case_id}' profile fixture is missing: {profile_path}"
            )
        else:
            try:
                load_and_normalize_master_profile(profile_path)
            except Exception as exc:  # pragma: no cover - defensive aggregation
                errors.append(
                    f"Case '{case.case_id}' profile fixture is invalid at {profile_path}: {exc}"
                )

        if not job_analysis_path.exists():
            errors.append(
                f"Case '{case.case_id}' job analysis fixture is missing: {job_analysis_path}"
            )
        else:
            try:
                NormalizedJobAnalysis.model_validate_json(
                    job_analysis_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                errors.append(
                    f"Case '{case.case_id}' job analysis fixture is invalid at {job_analysis_path}: {exc}"
                )

    if errors:
        raise Phase2EvalFixtureError(
            "Phase 2 eval fixture validation failed:\n- " + "\n- ".join(errors)
        )
