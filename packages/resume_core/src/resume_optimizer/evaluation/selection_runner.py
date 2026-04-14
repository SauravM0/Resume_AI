"""Real Phase 7 selection evaluation runner.

This pack evaluates whether the real Phase 2 path behaves like a strong human
resume strategist when choosing source material for a target role.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
import json
from pathlib import Path
import re
from typing import Iterable

from ..job_models import NormalizedJobAnalysis, NormalizedSkillRequirement, SkillPriority
from ..loaders import load_and_normalize_master_profile
from ..models import MasterProfile, RoleType, SeniorityLevel as ProfileSeniorityLevel
from ..phase1_deterministic_extractors import extract_deterministic_job_description_artifacts
from ..phase1_deterministic_models import RequirementStrength
from ..phase2_config import DEFAULT_PHASE2_CONFIG
from ..ranking_service import build_phase2_ranking_artifacts
from .case_models import (
    EvaluationCase,
    EvaluationPack,
    Expectation,
    ExpectationMatchMode,
    ExpectationType,
    RoleFamily,
    SelectionExpectations,
    SeniorityLevel,
)
from .loader import load_evaluation_pack

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_GENERIC_SKILL_TOKENS = {
    "and",
    "apis",
    "api",
    "build",
    "building",
    "engineer",
    "engineering",
    "experience",
    "preferred",
    "requirements",
    "responsibilities",
    "senior",
    "software",
    "systems",
    "team",
    "teams",
    "with",
    "years",
}


@dataclass
class ExpectationAssessment:
    """Explain one expectation bucket outcome."""

    label: str
    expectation_type: str
    weight: float
    required: bool
    matched: bool
    matched_item_labels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class CategoryScore:
    """Precision/recall plus detailed expectation assessments for one category."""

    precision: float
    recall: float
    matched_actual_count: int
    actual_count: int
    false_positive_count: int
    violated_exclusions: int
    positive_assessments: list[ExpectationAssessment] = field(default_factory=list)
    exclusion_assessments: list[ExpectationAssessment] = field(default_factory=list)


@dataclass
class PathologicalDetection:
    """Detection of strategically bad selection outcomes."""

    has_one_dominating: bool = False
    has_too_few_bullets: bool = False
    has_irrelevant_old: bool = False
    has_repetition: bool = False
    dominant_experience_share: float = 0.0
    repeated_source_share: float = 0.0
    total_selected_bullets: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class SelectionCaseResult:
    """Result for one selection evaluation case."""

    case_id: str
    description: str
    passed: bool
    overall_score: float
    experience_precision: float = 0.0
    experience_recall: float = 0.0
    project_precision: float = 0.0
    project_recall: float = 0.0
    bullet_precision: float = 0.0
    bullet_recall: float = 0.0
    skill_correctness: float = 0.0
    diversity_balance_score: float = 0.0
    average_selection_relevance: float = 0.0
    experience_score: CategoryScore | None = None
    project_score: CategoryScore | None = None
    bullet_score: CategoryScore | None = None
    skill_score: CategoryScore | None = None
    pathological: PathologicalDetection = field(default_factory=PathologicalDetection)
    failure_reasons: list[str] = field(default_factory=list)
    actual_selection: dict[str, object] = field(default_factory=dict)


@dataclass
class SelectionSummary:
    """Aggregate selection-evaluation summary."""

    total_cases: int
    passed_cases: int
    failed_cases: int
    avg_experience_precision: float
    avg_experience_recall: float
    avg_project_precision: float
    avg_project_recall: float
    avg_bullet_precision: float
    avg_bullet_recall: float
    avg_skill_correctness: float
    avg_diversity_balance: float
    pathology_rate: float
    case_results: list[SelectionCaseResult] = field(default_factory=list)


@dataclass(frozen=True)
class _ActualSelectable:
    id: str
    label: str
    match_values: tuple[str, ...]
    relevance_score: float = 0.0
    end_year: int | None = None
    source_item_id: str | None = None
    selected_bullet_count: int = 0
    evidence_count: int = 0


def run_selection_evaluation(
    pack_path: str | Path,
    *,
    today: date | None = None,
    fail_fast: bool = False,
) -> SelectionSummary:
    """Run selection evaluation on a fixture pack through the real Phase 2 path."""

    pack = load_evaluation_pack(pack_path)
    if pack.pack_type != "selection":
        raise ValueError(f"Pack type must be selection, got {pack.pack_type}")

    case_results: list[SelectionCaseResult] = []
    base_dir = Path(pack_path).resolve().parent

    for case in pack.cases:
        result = _evaluate_single_selection_case(case, base_dir=base_dir, today=today)
        case_results.append(result)
        if fail_fast and not result.passed:
            break

    return _build_selection_summary(case_results)


def _evaluate_single_selection_case(
    case: EvaluationCase,
    *,
    base_dir: Path,
    today: date | None,
) -> SelectionCaseResult:
    expectations = case.selection_expectations
    if expectations is None:
        return SelectionCaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            overall_score=0.0,
            failure_reasons=["No selection_expectations defined"],
        )
    if case.profile is None:
        return SelectionCaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            overall_score=0.0,
            failure_reasons=["No profile fixture defined"],
        )
    if case.job_description is None or not case.job_description.raw_text.strip():
        return SelectionCaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            overall_score=0.0,
            failure_reasons=["No job_description provided"],
        )

    profile = load_and_normalize_master_profile(base_dir / case.profile.path)
    job_analysis = _build_job_analysis(case)
    artifacts = build_phase2_ranking_artifacts(job_analysis, profile, today=today)
    actual_selection = _materialize_actual_selection(profile, artifacts.selection_result)

    experience_score = _score_category(
        expectations.experience_expectations,
        actual_selection["experiences"],
    )
    project_score = _score_category(
        expectations.project_expectations,
        actual_selection["projects"],
    )
    bullet_score = _score_category(
        expectations.bullet_expectations,
        actual_selection["bullets"],
    )
    skill_score = _score_category(
        expectations.skill_expectations,
        actual_selection["skills"],
    )

    skill_correctness = _mean(skill_score.precision, skill_score.recall)
    diversity_balance = _compute_diversity_balance(actual_selection)
    pathologies = _detect_pathologies(
        actual_selection=actual_selection,
        experience_score=experience_score,
        expectations=expectations,
        today=today or date.today(),
    )
    average_relevance = _average_selection_relevance(actual_selection)
    overall = _compute_selection_overall_score(
        experience_precision=experience_score.precision,
        experience_recall=experience_score.recall,
        project_precision=project_score.precision,
        project_recall=project_score.recall,
        bullet_precision=bullet_score.precision,
        bullet_recall=bullet_score.recall,
        skill_correctness=skill_correctness,
        diversity_balance=diversity_balance,
        pathological=pathologies,
    )
    failures = _build_failure_reasons(
        expectations=expectations,
        experience_score=experience_score,
        project_score=project_score,
        bullet_score=bullet_score,
        skill_score=skill_score,
        skill_correctness=skill_correctness,
        diversity_balance=diversity_balance,
        average_relevance=average_relevance,
        pathologies=pathologies,
    )

    return SelectionCaseResult(
        case_id=case.case_id,
        description=case.description,
        passed=not failures,
        overall_score=overall,
        experience_precision=experience_score.precision,
        experience_recall=experience_score.recall,
        project_precision=project_score.precision,
        project_recall=project_score.recall,
        bullet_precision=bullet_score.precision,
        bullet_recall=bullet_score.recall,
        skill_correctness=skill_correctness,
        diversity_balance_score=diversity_balance,
        average_selection_relevance=average_relevance,
        experience_score=experience_score,
        project_score=project_score,
        bullet_score=bullet_score,
        skill_score=skill_score,
        pathological=pathologies,
        failure_reasons=failures,
        actual_selection=_renderable_actual_selection(actual_selection),
    )


def _build_job_analysis(case: EvaluationCase) -> NormalizedJobAnalysis:
    jd_text = case.job_description.raw_text if case.job_description is not None else ""
    extraction = extract_deterministic_job_description_artifacts(jd_text)

    prioritized: dict[str, SkillPriority] = {}
    must_have_requirements: list[str] = []
    nice_to_have_requirements: list[str] = []
    technical_skills: list[str] = []

    for finding in extraction.tool_platform_findings:
        skill = finding.canonical_value or finding.value
        prioritized.setdefault(skill, SkillPriority.IMPORTANT)
        technical_skills.append(skill)

    for finding in extraction.requirement_markers:
        target = must_have_requirements if finding.strength == RequirementStrength.MUST_HAVE else nice_to_have_requirements
        target.append(finding.canonical_text)
        for keyword in finding.extracted_keywords:
            if _is_specific_skill(keyword):
                priority = (
                    SkillPriority.CORE
                    if finding.strength == RequirementStrength.MUST_HAVE
                    else SkillPriority.NICE_TO_HAVE
                )
                prioritized[keyword] = _highest_priority(prioritized.get(keyword), priority)
                technical_skills.append(keyword)

    for finding in extraction.repeated_keyword_findings:
        if finding.count >= 2 and _is_specific_skill(finding.keyword):
            prioritized.setdefault(finding.keyword, SkillPriority.IMPORTANT)
            technical_skills.append(finding.keyword)

    for phrase in _compound_requirement_skill_phrases(jd_text):
        prioritized.setdefault(phrase, SkillPriority.IMPORTANT)
        technical_skills.append(phrase)
        must_have_requirements.append(phrase)

    soft_skills = [finding.canonical_value for finding in extraction.leadership_findings]
    technical_skills = _stable_unique(technical_skills)
    must_have_requirements = _stable_unique(must_have_requirements + technical_skills[:4])
    nice_to_have_requirements = _stable_unique(nice_to_have_requirements)

    return NormalizedJobAnalysis(
        role_type=_role_type_for_case(case),
        seniority_level=_seniority_for_case(case),
        technical_skills=technical_skills,
        soft_skills=_stable_unique(soft_skills),
        key_action_verbs=_stable_unique([finding.canonical_value for finding in extraction.action_verb_findings]),
        must_have_requirements=must_have_requirements,
        nice_to_have_requirements=nice_to_have_requirements,
        years_experience_required=(
            max((finding.years for finding in extraction.years_experience_findings), default=None)
        ),
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name=skill, priority=priority)
            for skill, priority in prioritized.items()
        ],
    )


def _materialize_actual_selection(profile: MasterProfile, selection_result) -> dict[str, list[_ActualSelectable]]:
    experience_by_id = {item.id: item for item in profile.experience}
    project_by_id = {item.id: item for item in profile.projects}

    experiences: list[_ActualSelectable] = []
    projects: list[_ActualSelectable] = []
    bullets: list[_ActualSelectable] = []
    skills: list[_ActualSelectable] = []

    for selected in selection_result.selected_experiences:
        source = experience_by_id.get(selected.source_item_id)
        selected_bullets = [
            bullet for bullet in (source.bullets if source is not None else [])
            if bullet.id in set(selected.selected_bullet_ids)
        ]
        bullet_texts = [bullet.text for bullet in selected_bullets]
        label = (
            f"{source.title} @ {source.organization}"
            if source is not None
            else selected.source_item_id
        )
        experiences.append(
            _ActualSelectable(
                id=selected.source_item_id,
                label=label,
                match_values=tuple(
                    _stable_unique(
                        [
                            label,
                            source.title if source is not None else selected.source_item_id,
                            source.organization if source is not None else "",
                            *bullet_texts,
                            *selected.ranking_explanation.matched_keywords,
                            *selected.ranking_explanation.matched_job_requirements,
                        ]
                    )
                ),
                relevance_score=selected.relevance_score,
                end_year=source.end_date.year if source is not None and source.end_date is not None else None,
                source_item_id=selected.source_item_id,
                selected_bullet_count=len(selected.selected_bullet_ids),
                evidence_count=len(selected.evidence_unit_ids),
            )
        )
        for bullet in selected_bullets:
            bullets.append(
                _ActualSelectable(
                    id=bullet.id,
                    label=f"{label}: {bullet.text}",
                    match_values=(bullet.text, label, source.title if source is not None else selected.source_item_id),
                    relevance_score=selected.relevance_score,
                    end_year=source.end_date.year if source is not None and source.end_date is not None else None,
                    source_item_id=selected.source_item_id,
                    selected_bullet_count=1,
                    evidence_count=1,
                )
            )

    for selected in selection_result.selected_projects:
        source = project_by_id.get(selected.source_item_id)
        selected_bullets = [
            bullet for bullet in (source.bullets if source is not None else [])
            if bullet.id in set(selected.selected_bullet_ids)
        ]
        label = source.name if source is not None else selected.source_item_id
        projects.append(
            _ActualSelectable(
                id=selected.source_item_id,
                label=label,
                match_values=tuple(
                    _stable_unique(
                        [
                            label,
                            source.summary if source is not None and source.summary is not None else "",
                            *[bullet.text for bullet in selected_bullets],
                            *selected.ranking_explanation.matched_keywords,
                            *selected.ranking_explanation.matched_job_requirements,
                        ]
                    )
                ),
                relevance_score=selected.relevance_score,
                end_year=source.end_date.year if source is not None and source.end_date is not None else None,
                source_item_id=selected.source_item_id,
                selected_bullet_count=len(selected.selected_bullet_ids),
                evidence_count=len(selected.evidence_unit_ids),
            )
        )
        for bullet in selected_bullets:
            bullets.append(
                _ActualSelectable(
                    id=bullet.id,
                    label=f"{label}: {bullet.text}",
                    match_values=(bullet.text, label),
                    relevance_score=selected.relevance_score,
                    end_year=source.end_date.year if source is not None and source.end_date is not None else None,
                    source_item_id=selected.source_item_id,
                    selected_bullet_count=1,
                    evidence_count=1,
                )
            )

    for selected in selection_result.selected_skills:
        skills.append(
            _ActualSelectable(
                id=selected.id,
                label=selected.skill_name,
                match_values=(
                    selected.skill_name,
                    *selected.ranking_explanation.matched_keywords,
                    *selected.ranking_explanation.matched_required_skills,
                ),
                relevance_score=selected.relevance_score,
                source_item_id=selected.source_item_id,
                evidence_count=1,
            )
        )

    return {
        "experiences": experiences,
        "projects": projects,
        "bullets": bullets,
        "skills": skills,
    }


def _score_category(expectations: list[Expectation], actual_items: list[_ActualSelectable]) -> CategoryScore:
    positives = [
        expectation
        for expectation in expectations
        if expectation.type in {
            ExpectationType.MUST_INCLUDE,
            ExpectationType.PREFER_INCLUDE,
            ExpectationType.ACCEPTABLE_ALTERNATIVE,
        }
    ]
    exclusions = [
        expectation for expectation in expectations if expectation.type == ExpectationType.MUST_NOT_INCLUDE
    ]

    positive_units = _group_positive_expectations(positives)
    positive_assessments: list[ExpectationAssessment] = []
    matched_positive_item_ids: set[str] = set()
    earned_weight = 0.0
    total_weight = 0.0

    for _, group_expectations in positive_units:
        matched_items = _matched_items_for_group(group_expectations, actual_items)
        matched = bool(matched_items)
        representative = group_expectations[0]
        weight = max(expectation.weight for expectation in group_expectations)
        total_weight += weight
        if matched:
            earned_weight += weight
            matched_positive_item_ids.update(item.id for item in matched_items)
        label = " | ".join(expectation.value for expectation in group_expectations)
        positive_assessments.append(
            ExpectationAssessment(
                label=label,
                expectation_type=representative.type.value,
                weight=weight,
                required=any(item.type == ExpectationType.MUST_INCLUDE for item in group_expectations),
                matched=matched,
                matched_item_labels=[item.label for item in matched_items],
                notes=[item.reason for item in group_expectations if item.reason],
            )
        )

    exclusion_assessments: list[ExpectationAssessment] = []
    violating_item_ids: set[str] = set()
    for expectation in exclusions:
        matched_items = [
            item for item in actual_items if _expectation_matches_item(expectation, item)
        ]
        if matched_items:
            violating_item_ids.update(item.id for item in matched_items)
        exclusion_assessments.append(
            ExpectationAssessment(
                label=expectation.value,
                expectation_type=expectation.type.value,
                weight=expectation.weight,
                required=True,
                matched=not matched_items,
                matched_item_labels=[item.label for item in matched_items],
                notes=[expectation.reason] if expectation.reason else [],
            )
        )

    matched_actual_count = sum(
        1
        for item in actual_items
        if item.id in matched_positive_item_ids and item.id not in violating_item_ids
    )
    false_positive_count = sum(
        1
        for item in actual_items
        if item.id not in matched_positive_item_ids or item.id in violating_item_ids
    )
    precision = (
        matched_actual_count / len(actual_items)
        if actual_items
        else 1.0
    )
    recall = earned_weight / total_weight if total_weight > 0 else 1.0
    violated_exclusions = sum(1 for item in exclusion_assessments if not item.matched)

    return CategoryScore(
        precision=round(precision, 4),
        recall=round(recall, 4),
        matched_actual_count=matched_actual_count,
        actual_count=len(actual_items),
        false_positive_count=false_positive_count,
        violated_exclusions=violated_exclusions,
        positive_assessments=positive_assessments,
        exclusion_assessments=exclusion_assessments,
    )


def _group_positive_expectations(
    expectations: list[Expectation],
) -> list[tuple[str, list[Expectation]]]:
    ordered_groups: list[tuple[str, list[Expectation]]] = []
    seen: dict[str, int] = {}
    for index, expectation in enumerate(expectations):
        if expectation.type == ExpectationType.ACCEPTABLE_ALTERNATIVE:
            key = expectation.alternative_group or f"alt::{index}"
        else:
            key = f"single::{index}"
        if key not in seen:
            seen[key] = len(ordered_groups)
            ordered_groups.append((key, [expectation]))
            continue
        ordered_groups[seen[key]][1].append(expectation)
    return ordered_groups


def _matched_items_for_group(
    group_expectations: list[Expectation],
    actual_items: list[_ActualSelectable],
) -> list[_ActualSelectable]:
    matched: list[_ActualSelectable] = []
    for item in actual_items:
        if any(_expectation_matches_item(expectation, item) for expectation in group_expectations):
            matched.append(item)
    return matched


def _expectation_matches_item(expectation: Expectation, item: _ActualSelectable) -> bool:
    return any(
        _match_value(expectation.value, candidate, expectation.match_mode)
        for candidate in item.match_values
        if candidate
    )


def _match_value(expected: str, actual: str, mode: ExpectationMatchMode) -> bool:
    expected_key = _normalize_text(expected)
    actual_key = _normalize_text(actual)
    if not expected_key or not actual_key:
        return False
    if mode == ExpectationMatchMode.EXACT:
        return expected_key == actual_key
    if mode == ExpectationMatchMode.FUZZY:
        return (
            expected_key in actual_key
            or actual_key in expected_key
            or _token_overlap(expected_key, actual_key) >= 0.5
        )
    if mode == ExpectationMatchMode.SUBSET:
        expected_tokens = set(_tokenize(expected_key))
        actual_tokens = set(_tokenize(actual_key))
        return bool(expected_tokens) and expected_tokens <= actual_tokens
    if mode == ExpectationMatchMode.SUPERSET:
        expected_tokens = set(_tokenize(expected_key))
        actual_tokens = set(_tokenize(actual_key))
        return bool(actual_tokens) and actual_tokens <= expected_tokens
    return False


def _compute_diversity_balance(actual_selection: dict[str, list[_ActualSelectable]]) -> float:
    experience_items = actual_selection["experiences"]
    project_items = actual_selection["projects"]
    bullet_items = actual_selection["bullets"]
    selected_entries = [*experience_items, *project_items]

    if not selected_entries:
        return 1.0

    unique_sources = len({item.source_item_id or item.id for item in selected_entries})
    breadth_score = unique_sources / len(selected_entries)

    total_bullets = len(bullet_items)
    if total_bullets <= 0:
        bullet_balance = 1.0
    else:
        by_source: dict[str, int] = defaultdict(int)
        for bullet in bullet_items:
            by_source[bullet.source_item_id or bullet.id] += 1
        dominant_share = max(by_source.values()) / total_bullets
        threshold = DEFAULT_PHASE2_CONFIG.selection_limits.max_bullet_share_per_experience
        if dominant_share <= threshold:
            bullet_balance = 1.0
        else:
            bullet_balance = max(0.0, 1.0 - ((dominant_share - threshold) / max(1e-6, 1.0 - threshold)))

    skill_support = len(actual_selection["skills"])
    skill_balance = 1.0 if skill_support > 0 else 0.5
    return round(_mean(breadth_score, bullet_balance, skill_balance), 4)


def _detect_pathologies(
    *,
    actual_selection: dict[str, list[_ActualSelectable]],
    experience_score: CategoryScore,
    expectations: SelectionExpectations,
    today: date,
) -> PathologicalDetection:
    detection = PathologicalDetection()
    bullets = actual_selection["bullets"]
    experiences = actual_selection["experiences"]
    detection.total_selected_bullets = len(bullets)

    if bullets:
        by_source: dict[str, int] = defaultdict(int)
        for bullet in bullets:
            by_source[bullet.source_item_id or bullet.id] += 1
        detection.dominant_experience_share = max(by_source.values()) / len(bullets)
        detection.repeated_source_share = detection.dominant_experience_share

        if len(experiences) > 1:
            sorted_experiences = sorted(experiences, key=lambda item: item.relevance_score, reverse=True)
            gap = sorted_experiences[0].relevance_score - sorted_experiences[1].relevance_score
            if (
                detection.dominant_experience_share > DEFAULT_PHASE2_CONFIG.selection_limits.max_bullet_share_per_experience
                and gap < DEFAULT_PHASE2_CONFIG.thresholds.dominant_experience_score_gap
            ):
                detection.has_one_dominating = True
                detection.reasons.append(
                    "One experience supplied too many bullets without a score gap large enough to justify concentration."
                )

        if detection.repeated_source_share >= 0.75 and len({item.source_item_id for item in experiences if item.source_item_id}) > 1:
            detection.has_repetition = True
            detection.reasons.append(
                "Repeated evidence from the same source crowded out breadth across experiences/projects."
            )

    if detection.total_selected_bullets < expectations.min_bullet_count:
        detection.has_too_few_bullets = True
        detection.reasons.append(
            f"Only {detection.total_selected_bullets} bullets survived; expected at least {expectations.min_bullet_count}."
        )

    current_year = today.year
    matched_positive_labels = {
        assessment.matched_item_labels[0]
        for assessment in experience_score.positive_assessments
        if assessment.matched and assessment.matched_item_labels
    }
    for experience in experiences:
        if experience.end_year is None:
            continue
        years_old = current_year - experience.end_year
        if years_old < 6:
            continue
        if experience.relevance_score >= expectations.min_selection_relevance:
            continue
        if experience.label in matched_positive_labels:
            continue
        detection.has_irrelevant_old = True
        detection.reasons.append(
            f"Older experience '{experience.label}' was selected despite low relevance and no gold expectation support."
        )
        break

    return detection


def _build_failure_reasons(
    *,
    expectations: SelectionExpectations,
    experience_score: CategoryScore,
    project_score: CategoryScore,
    bullet_score: CategoryScore,
    skill_score: CategoryScore,
    skill_correctness: float,
    diversity_balance: float,
    average_relevance: float,
    pathologies: PathologicalDetection,
) -> list[str]:
    failures: list[str] = []

    failures.extend(_required_expectation_failures("experience", experience_score))
    failures.extend(_required_expectation_failures("project", project_score))
    failures.extend(_required_expectation_failures("bullet", bullet_score))
    failures.extend(_required_expectation_failures("skill", skill_score))

    if experience_score.precision < expectations.min_experience_precision:
        failures.append(
            f"experience precision {experience_score.precision:.2f} below {expectations.min_experience_precision:.2f}"
        )
    if experience_score.recall < expectations.min_experience_recall:
        failures.append(
            f"experience recall {experience_score.recall:.2f} below {expectations.min_experience_recall:.2f}"
        )
    if project_score.precision < expectations.min_project_precision:
        failures.append(
            f"project precision {project_score.precision:.2f} below {expectations.min_project_precision:.2f}"
        )
    if project_score.recall < expectations.min_project_recall:
        failures.append(
            f"project recall {project_score.recall:.2f} below {expectations.min_project_recall:.2f}"
        )
    if bullet_score.precision < expectations.min_bullet_precision:
        failures.append(
            f"bullet precision {bullet_score.precision:.2f} below {expectations.min_bullet_precision:.2f}"
        )
    if bullet_score.recall < expectations.min_bullet_recall:
        failures.append(
            f"bullet recall {bullet_score.recall:.2f} below {expectations.min_bullet_recall:.2f}"
        )
    if skill_correctness < expectations.min_skill_correctness:
        failures.append(
            f"skill correctness {skill_correctness:.2f} below {expectations.min_skill_correctness:.2f}"
        )
    if diversity_balance < expectations.min_diversity_balance:
        failures.append(
            f"diversity / balance score {diversity_balance:.2f} below {expectations.min_diversity_balance:.2f}"
        )
    if average_relevance < expectations.min_selection_relevance:
        failures.append(
            f"average selected relevance {average_relevance:.2f} below {expectations.min_selection_relevance:.2f}"
        )

    if pathologies.has_one_dominating:
        failures.append("pathology: one experience dominated selection without justification")
    if pathologies.has_too_few_bullets:
        failures.append("pathology: too few bullets survived final selection")
    if pathologies.has_irrelevant_old:
        failures.append("pathology: irrelevant old experience was included")
    if pathologies.has_repetition:
        failures.append("pathology: repeated evidence from one source crowded out breadth")
    return failures


def _required_expectation_failures(category_name: str, score: CategoryScore) -> list[str]:
    failures: list[str] = []
    for assessment in score.positive_assessments:
        if assessment.required and not assessment.matched:
            failures.append(f"{category_name} missing required expectation: {assessment.label}")
    for assessment in score.exclusion_assessments:
        if not assessment.matched:
            failures.append(
                f"{category_name} violated exclusion: {assessment.label} -> {', '.join(assessment.matched_item_labels)}"
            )
    return failures


def _compute_selection_overall_score(
    *,
    experience_precision: float,
    experience_recall: float,
    project_precision: float,
    project_recall: float,
    bullet_precision: float,
    bullet_recall: float,
    skill_correctness: float,
    diversity_balance: float,
    pathological: PathologicalDetection,
) -> float:
    score = (
        0.20 * _mean(experience_precision, experience_recall)
        + 0.15 * _mean(project_precision, project_recall)
        + 0.30 * _mean(bullet_precision, bullet_recall)
        + 0.20 * skill_correctness
        + 0.15 * diversity_balance
    )
    penalty = 0.0
    if pathological.has_one_dominating:
        penalty += 0.07
    if pathological.has_too_few_bullets:
        penalty += 0.07
    if pathological.has_irrelevant_old:
        penalty += 0.08
    if pathological.has_repetition:
        penalty += 0.05
    return round(max(0.0, score - penalty), 3)


def _average_selection_relevance(actual_selection: dict[str, list[_ActualSelectable]]) -> float:
    scored = [
        item.relevance_score
        for item in [*actual_selection["experiences"], *actual_selection["projects"]]
    ]
    return round(sum(scored) / len(scored), 4) if scored else 0.0


def _build_selection_summary(results: list[SelectionCaseResult]) -> SelectionSummary:
    if not results:
        return SelectionSummary(
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
            avg_experience_precision=0.0,
            avg_experience_recall=0.0,
            avg_project_precision=0.0,
            avg_project_recall=0.0,
            avg_bullet_precision=0.0,
            avg_bullet_recall=0.0,
            avg_skill_correctness=0.0,
            avg_diversity_balance=0.0,
            pathology_rate=0.0,
            case_results=[],
        )

    total = len(results)
    passed = sum(1 for result in results if result.passed)
    pathology_hits = sum(
        1
        for result in results
        if any(
            (
                result.pathological.has_one_dominating,
                result.pathological.has_too_few_bullets,
                result.pathological.has_irrelevant_old,
                result.pathological.has_repetition,
            )
        )
    )
    return SelectionSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        avg_experience_precision=round(sum(item.experience_precision for item in results) / total, 4),
        avg_experience_recall=round(sum(item.experience_recall for item in results) / total, 4),
        avg_project_precision=round(sum(item.project_precision for item in results) / total, 4),
        avg_project_recall=round(sum(item.project_recall for item in results) / total, 4),
        avg_bullet_precision=round(sum(item.bullet_precision for item in results) / total, 4),
        avg_bullet_recall=round(sum(item.bullet_recall for item in results) / total, 4),
        avg_skill_correctness=round(sum(item.skill_correctness for item in results) / total, 4),
        avg_diversity_balance=round(sum(item.diversity_balance_score for item in results) / total, 4),
        pathology_rate=round(pathology_hits / total, 4),
        case_results=results,
    )


def render_selection_case_report(result: SelectionCaseResult) -> str:
    """Render one case as a transparent, human-readable report."""

    lines = [
        f"Selection Evaluation Report: {result.case_id}",
        f"Description: {result.description}",
        f"Status: {'PASS' if result.passed else 'FAIL'} | overall={result.overall_score:.3f}",
        (
            "Metrics: "
            f"exp P/R={result.experience_precision:.2f}/{result.experience_recall:.2f}, "
            f"proj P/R={result.project_precision:.2f}/{result.project_recall:.2f}, "
            f"bullet P/R={result.bullet_precision:.2f}/{result.bullet_recall:.2f}, "
            f"skills={result.skill_correctness:.2f}, "
            f"diversity={result.diversity_balance_score:.2f}, "
            f"avg relevance={result.average_selection_relevance:.2f}"
        ),
        "",
        "Selected evidence:",
    ]
    lines.extend(_render_selected_items_block(result.actual_selection))

    for label, score in (
        ("Experiences", result.experience_score),
        ("Projects", result.project_score),
        ("Bullets", result.bullet_score),
        ("Skills", result.skill_score),
    ):
        if score is None:
            continue
        lines.append("")
        lines.append(
            f"{label}: precision={score.precision:.2f} recall={score.recall:.2f} "
            f"matched={score.matched_actual_count}/{score.actual_count} "
            f"false_positives={score.false_positive_count}"
        )
        lines.extend(_render_assessments("  expected", score.positive_assessments))
        lines.extend(_render_assessments("  exclude", score.exclusion_assessments))

    if result.pathological.reasons:
        lines.append("")
        lines.append("Pathology checks:")
        for reason in result.pathological.reasons:
            lines.append(f"  - {reason}")

    if result.failure_reasons:
        lines.append("")
        lines.append("Failures:")
        for failure in result.failure_reasons:
            lines.append(f"  - {failure}")

    return "\n".join(lines)


def render_selection_summary(summary: SelectionSummary) -> str:
    """Render the aggregate pack summary."""

    lines = [
        "Selection Evaluation Summary",
        (
            f"Cases: {summary.total_cases} | Passed: {summary.passed_cases} | "
            f"Failed: {summary.failed_cases}"
        ),
        (
            "Averages: "
            f"exp P/R={summary.avg_experience_precision:.2f}/{summary.avg_experience_recall:.2f}, "
            f"proj P/R={summary.avg_project_precision:.2f}/{summary.avg_project_recall:.2f}, "
            f"bullet P/R={summary.avg_bullet_precision:.2f}/{summary.avg_bullet_recall:.2f}, "
            f"skills={summary.avg_skill_correctness:.2f}, "
            f"diversity={summary.avg_diversity_balance:.2f}, "
            f"pathology_rate={summary.pathology_rate:.2f}"
        ),
        "",
    ]
    for result in summary.case_results:
        lines.append(
            f"[{'PASS' if result.passed else 'FAIL'}] {result.case_id} "
            f"overall={result.overall_score:.3f} "
            f"exp={result.experience_precision:.2f}/{result.experience_recall:.2f} "
            f"proj={result.project_precision:.2f}/{result.project_recall:.2f} "
            f"bullet={result.bullet_precision:.2f}/{result.bullet_recall:.2f} "
            f"skills={result.skill_correctness:.2f} "
            f"diversity={result.diversity_balance_score:.2f}"
        )
        if result.failure_reasons:
            for failure in result.failure_reasons:
                lines.append(f"  - {failure}")
    return "\n".join(lines)


def render_selection_summary_json(summary: SelectionSummary) -> str:
    """Render the pack summary as JSON."""

    payload = {
        "total_cases": summary.total_cases,
        "passed_cases": summary.passed_cases,
        "failed_cases": summary.failed_cases,
        "avg_experience_precision": summary.avg_experience_precision,
        "avg_experience_recall": summary.avg_experience_recall,
        "avg_project_precision": summary.avg_project_precision,
        "avg_project_recall": summary.avg_project_recall,
        "avg_bullet_precision": summary.avg_bullet_precision,
        "avg_bullet_recall": summary.avg_bullet_recall,
        "avg_skill_correctness": summary.avg_skill_correctness,
        "avg_diversity_balance": summary.avg_diversity_balance,
        "pathology_rate": summary.pathology_rate,
        "case_results": [
            {
                **asdict(result),
                "experience_score": asdict(result.experience_score) if result.experience_score is not None else None,
                "project_score": asdict(result.project_score) if result.project_score is not None else None,
                "bullet_score": asdict(result.bullet_score) if result.bullet_score is not None else None,
                "skill_score": asdict(result.skill_score) if result.skill_score is not None else None,
            }
            for result in summary.case_results
        ],
    }
    return json.dumps(payload, indent=2)


def _render_selected_items_block(actual_selection: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for category in ("experiences", "projects", "bullets", "skills"):
        items = actual_selection.get(category, [])
        labels = [item["label"] for item in items[:5]]
        suffix = " ..." if len(items) > 5 else ""
        lines.append(f"  {category}: {', '.join(labels) if labels else '(none)'}{suffix}")
    return lines


def _render_assessments(prefix: str, assessments: Iterable[ExpectationAssessment]) -> list[str]:
    lines: list[str] = []
    for assessment in assessments:
        status = "ok" if assessment.matched else "miss"
        matched = ", ".join(assessment.matched_item_labels) if assessment.matched_item_labels else "(none)"
        lines.append(f"{prefix} [{status}] {assessment.label} -> {matched}")
    return lines


def _renderable_actual_selection(actual_selection: dict[str, list[_ActualSelectable]]) -> dict[str, object]:
    return {
        key: [
            {
                "id": item.id,
                "label": item.label,
                "relevance_score": round(item.relevance_score, 4),
                "source_item_id": item.source_item_id,
                "selected_bullet_count": item.selected_bullet_count,
                "evidence_count": item.evidence_count,
                "end_year": item.end_year,
            }
            for item in value
        ]
        for key, value in actual_selection.items()
    }


def _role_type_for_case(case: EvaluationCase) -> RoleType | None:
    role_family = case.phase1_expectations.expected_role_family if case.phase1_expectations is not None else None
    if role_family == RoleFamily.MANAGEMENT:
        return RoleType.MANAGER
    return RoleType.INDIVIDUAL_CONTRIBUTOR


def _seniority_for_case(case: EvaluationCase) -> ProfileSeniorityLevel | None:
    seniority = case.phase1_expectations.expected_seniority if case.phase1_expectations is not None else None
    if seniority is None:
        return None
    mapping = {
        SeniorityLevel.JUNIOR: ProfileSeniorityLevel.JUNIOR,
        SeniorityLevel.MID: ProfileSeniorityLevel.MID,
        SeniorityLevel.SENIOR: ProfileSeniorityLevel.SENIOR,
        SeniorityLevel.STAFF: ProfileSeniorityLevel.STAFF,
        SeniorityLevel.PRINCIPAL: ProfileSeniorityLevel.PRINCIPAL,
        SeniorityLevel.DIRECTOR: ProfileSeniorityLevel.DIRECTOR,
        SeniorityLevel.VP: ProfileSeniorityLevel.EXECUTIVE,
    }
    return mapping.get(seniority)


def _highest_priority(current: SkillPriority | None, candidate: SkillPriority) -> SkillPriority:
    ordering = {
        SkillPriority.CORE: 3,
        SkillPriority.IMPORTANT: 2,
        SkillPriority.NICE_TO_HAVE: 1,
    }
    if current is None:
        return candidate
    return current if ordering[current] >= ordering[candidate] else candidate


def _compound_requirement_skill_phrases(jd_text: str) -> list[str]:
    lowered = jd_text.casefold()
    candidates = (
        "REST APIs",
        "distributed systems",
        "microservices",
        "observability",
        "incident response",
        "reliability engineering",
        "developer platform",
        "system design",
        "platform strategy",
        "fullstack",
        "frontend",
        "leadership",
    )
    return [phrase for phrase in candidates if phrase.casefold() in lowered]


def _is_specific_skill(value: str) -> bool:
    tokens = _tokenize(value)
    return bool(tokens) and not all(token in _GENERIC_SKILL_TOKENS for token in tokens)


def _normalize_text(value: str) -> str:
    return " ".join(_tokenize(value))


def _tokenize(value: str) -> list[str]:
    return _TOKEN_RE.findall(value.casefold())


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _stable_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _mean(*values: float) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
