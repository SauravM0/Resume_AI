"""Fixture-driven evaluation harness for Phase 3 selection quality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path

from pydantic import Field

from backend.app.tests.fixtures.phase2_candidate_profiles import phase3_eval_profile_fixture

from .job_models import NormalizedJobAnalysis
from .models import NonEmptyStr, StrictModel
from .services.phase2_service import Phase2Service

DEFAULT_PHASE3_EVAL_FIXTURE_ROOT = Path("backend/app/tests/fixtures/phase3_eval")


class Phase3OmissionExpectation(StrictModel):
    """Expected omission annotation for one important omitted item."""

    item_id: NonEmptyStr
    omission_reason: NonEmptyStr | None = None


class Phase3EvalExpectation(StrictModel):
    """Gold expected selection output for one Phase 3 case."""

    selected_experiences: list[NonEmptyStr] = Field(default_factory=list)
    selected_projects: list[NonEmptyStr] = Field(default_factory=list)
    highlighted_skills: list[NonEmptyStr] = Field(default_factory=list)
    omitted_items: list[Phase3OmissionExpectation] = Field(default_factory=list)


class Phase3EvalCase(StrictModel):
    """One realistic job/profile selection case."""

    case_id: NonEmptyStr
    description: NonEmptyStr
    profile_fixture: NonEmptyStr
    job_analysis: NormalizedJobAnalysis
    expectation: Phase3EvalExpectation


class Phase3EvalManifest(StrictModel):
    """Collection of Phase 3 evaluation cases."""

    cases: list[Phase3EvalCase] = Field(default_factory=list)


class PrecisionRecallMetric(StrictModel):
    """Simple precision/recall/count metric."""

    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    true_positive_count: int = Field(ge=0)
    predicted_count: int = Field(ge=0)
    expected_count: int = Field(ge=0)


class OmissionEvaluationMetric(StrictModel):
    """Omission correctness over the annotated omission subset."""

    correctness: float = Field(ge=0.0, le=1.0)
    matched_count: int = Field(ge=0)
    expected_count: int = Field(ge=0)


class Phase3EvalCaseResult(StrictModel):
    """One case result with selection metrics and matched outputs."""

    case_id: NonEmptyStr
    description: NonEmptyStr
    passed: bool
    experience_selection: PrecisionRecallMetric
    project_selection: PrecisionRecallMetric
    skill_selection: PrecisionRecallMetric
    omission_evaluation: OmissionEvaluationMetric
    selected_experiences: list[str] = Field(default_factory=list)
    selected_projects: list[str] = Field(default_factory=list)
    highlighted_skills: list[str] = Field(default_factory=list)
    omitted_items: dict[str, str] = Field(default_factory=dict)
    unmet_expectations: list[str] = Field(default_factory=list)


class Phase3EvalSummary(StrictModel):
    """Aggregate Phase 3 evaluation summary."""

    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    average_experience_precision: float = Field(ge=0.0, le=1.0)
    average_experience_recall: float = Field(ge=0.0, le=1.0)
    average_project_precision: float = Field(ge=0.0, le=1.0)
    average_project_recall: float = Field(ge=0.0, le=1.0)
    average_skill_precision: float = Field(ge=0.0, le=1.0)
    average_skill_recall: float = Field(ge=0.0, le=1.0)
    average_omission_correctness: float = Field(ge=0.0, le=1.0)
    case_results: list[Phase3EvalCaseResult] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _SelectionSnapshot:
    selected_experiences: list[str]
    selected_projects: list[str]
    highlighted_skills: list[str]
    omitted_items: dict[str, str]


def load_phase3_eval_manifest(
    fixture_root: Path = DEFAULT_PHASE3_EVAL_FIXTURE_ROOT,
) -> Phase3EvalManifest:
    """Load the Phase 3 gold-case manifest."""

    manifest_path = fixture_root / "eval_cases.json"
    return Phase3EvalManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def run_phase3_eval(
    *,
    fixture_root: Path = DEFAULT_PHASE3_EVAL_FIXTURE_ROOT,
    case_ids: list[str] | None = None,
    today: date | None = None,
) -> Phase3EvalSummary:
    """Run all or a selected subset of Phase 3 evaluation cases."""

    manifest = load_phase3_eval_manifest(fixture_root)
    selected_case_ids = set(case_ids) if case_ids is not None else None
    case_results = [
        run_phase3_eval_case(case, today=today)
        for case in manifest.cases
        if selected_case_ids is None or case.case_id in selected_case_ids
    ]
    return _build_summary(case_results)


def run_phase3_eval_case(
    case: Phase3EvalCase,
    *,
    today: date | None = None,
) -> Phase3EvalCaseResult:
    """Run one Phase 3 selection case through the normal service path."""

    profile = phase3_eval_profile_fixture(case.profile_fixture)
    service_result = Phase2Service().run(case.job_analysis, source_profile=profile, today=today)
    decision = service_result.phase2_result.resume_selection_decision
    snapshot = _SelectionSnapshot(
        selected_experiences=[item.source_item_id for item in decision.selected_experiences],
        selected_projects=[item.source_item_id for item in decision.selected_projects],
        highlighted_skills=[item.skill_name for item in decision.selected_skills],
        omitted_items={item.source_item_id: item.reason for item in decision.omitted_items},
    )
    experience_selection = _precision_recall(
        predicted=snapshot.selected_experiences,
        expected=case.expectation.selected_experiences,
    )
    project_selection = _precision_recall(
        predicted=snapshot.selected_projects,
        expected=case.expectation.selected_projects,
    )
    skill_selection = _precision_recall(
        predicted=snapshot.highlighted_skills,
        expected=case.expectation.highlighted_skills,
    )
    omission_evaluation = _omission_correctness(
        predicted=snapshot.omitted_items,
        expected=case.expectation.omitted_items,
    )
    unmet_expectations = _evaluate_expectations(case.expectation, snapshot)
    return Phase3EvalCaseResult(
        case_id=case.case_id,
        description=case.description,
        passed=not unmet_expectations,
        experience_selection=experience_selection,
        project_selection=project_selection,
        skill_selection=skill_selection,
        omission_evaluation=omission_evaluation,
        selected_experiences=snapshot.selected_experiences,
        selected_projects=snapshot.selected_projects,
        highlighted_skills=snapshot.highlighted_skills,
        omitted_items=snapshot.omitted_items,
        unmet_expectations=unmet_expectations,
    )


def render_phase3_eval_summary(summary: Phase3EvalSummary) -> str:
    """Render a local CLI-friendly text summary."""

    lines = [
        "Phase 3 Evaluation Summary",
        f"Cases: {summary.total_cases} | Passed: {summary.passed_cases} | Failed: {summary.failed_cases}",
        (
            "Averages: "
            f"experience P/R={summary.average_experience_precision:.2f}/{summary.average_experience_recall:.2f}, "
            f"project P/R={summary.average_project_precision:.2f}/{summary.average_project_recall:.2f}, "
            f"skill P/R={summary.average_skill_precision:.2f}/{summary.average_skill_recall:.2f}, "
            f"omission correctness={summary.average_omission_correctness:.2f}"
        ),
        "",
    ]
    for result in summary.case_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"[{status}] {result.case_id}: "
            f"exp={result.experience_selection.precision:.2f}/{result.experience_selection.recall:.2f}, "
            f"proj={result.project_selection.precision:.2f}/{result.project_selection.recall:.2f}, "
            f"skills={result.skill_selection.precision:.2f}/{result.skill_selection.recall:.2f}, "
            f"omit={result.omission_evaluation.correctness:.2f}"
        )
        if result.selected_experiences:
            lines.append(f"  selected experiences: {', '.join(result.selected_experiences)}")
        if result.selected_projects:
            lines.append(f"  selected projects: {', '.join(result.selected_projects)}")
        if result.highlighted_skills:
            lines.append(f"  highlighted skills: {', '.join(result.highlighted_skills)}")
        if result.omitted_items:
            omitted = ", ".join(
                f"{item_id} ({reason})" for item_id, reason in sorted(result.omitted_items.items())
            )
            lines.append(f"  omitted items: {omitted}")
        if result.unmet_expectations:
            lines.append(f"  unmet expectations: {'; '.join(result.unmet_expectations)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def phase3_eval_summary_json(summary: Phase3EvalSummary) -> str:
    """Return the Phase 3 eval summary as formatted JSON."""

    return json.dumps(summary.model_dump(mode="json"), indent=2)


def _precision_recall(*, predicted: list[str], expected: list[str]) -> PrecisionRecallMetric:
    predicted_set = set(predicted)
    expected_set = set(expected)
    true_positive_count = len(predicted_set.intersection(expected_set))
    precision = 1.0 if not predicted_set and not expected_set else true_positive_count / max(1, len(predicted_set))
    recall = 1.0 if not expected_set and not predicted_set else true_positive_count / max(1, len(expected_set))
    return PrecisionRecallMetric(
        precision=round(precision, 4),
        recall=round(recall, 4),
        true_positive_count=true_positive_count,
        predicted_count=len(predicted_set),
        expected_count=len(expected_set),
    )


def _omission_correctness(
    *,
    predicted: dict[str, str],
    expected: list[Phase3OmissionExpectation],
) -> OmissionEvaluationMetric:
    if not expected:
        return OmissionEvaluationMetric(correctness=1.0, matched_count=0, expected_count=0)
    matched_count = 0
    for omission in expected:
        predicted_reason = predicted.get(omission.item_id)
        if predicted_reason is None:
            continue
        if omission.omission_reason is None or predicted_reason == omission.omission_reason:
            matched_count += 1
    return OmissionEvaluationMetric(
        correctness=round(matched_count / len(expected), 4),
        matched_count=matched_count,
        expected_count=len(expected),
    )


def _evaluate_expectations(
    expectation: Phase3EvalExpectation,
    snapshot: _SelectionSnapshot,
) -> list[str]:
    unmet: list[str] = []
    if set(snapshot.selected_experiences) != set(expectation.selected_experiences):
        unmet.append(
            "selected experiences mismatch"
        )
    if set(snapshot.selected_projects) != set(expectation.selected_projects):
        unmet.append(
            "selected projects mismatch"
        )
    if set(snapshot.highlighted_skills) != set(expectation.highlighted_skills):
        unmet.append(
            "highlighted skills mismatch"
        )
    for omission in expectation.omitted_items:
        predicted_reason = snapshot.omitted_items.get(omission.item_id)
        if predicted_reason is None:
            unmet.append(f"expected omitted item missing: {omission.item_id}")
            continue
        if omission.omission_reason is not None and predicted_reason != omission.omission_reason:
            unmet.append(
                f"omission reason mismatch for {omission.item_id}: expected {omission.omission_reason}, got {predicted_reason}"
            )
    return unmet


def _build_summary(case_results: list[Phase3EvalCaseResult]) -> Phase3EvalSummary:
    total = len(case_results)
    passed = sum(1 for result in case_results if result.passed)
    failed = total - passed
    return Phase3EvalSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        average_experience_precision=_average(result.experience_selection.precision for result in case_results),
        average_experience_recall=_average(result.experience_selection.recall for result in case_results),
        average_project_precision=_average(result.project_selection.precision for result in case_results),
        average_project_recall=_average(result.project_selection.recall for result in case_results),
        average_skill_precision=_average(result.skill_selection.precision for result in case_results),
        average_skill_recall=_average(result.skill_selection.recall for result in case_results),
        average_omission_correctness=_average(
            result.omission_evaluation.correctness for result in case_results
        ),
        case_results=case_results,
    )


def _average(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
