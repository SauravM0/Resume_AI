"""Deterministic JD-quality scoring for Phase 1."""

from __future__ import annotations

from .phase1_deterministic_models import DeterministicJobDescriptionExtraction
from .phase1_merge_normalization import clamp_score, fold_key, stable_unique
from .phase1_models import JDQualityBreakdown

_VAGUE_PHRASES = (
    "someone",
    "help teams",
    "modern tools",
    "is a plus",
    "various",
    "etc",
    "other duties",
)


def score_job_description_quality(
    deterministic: DeterministicJobDescriptionExtraction,
) -> tuple[JDQualityBreakdown, float]:
    """Score JD quality and return both the breakdown and overall score."""

    completeness = _completeness_score(deterministic)
    specificity = _specificity_score(deterministic)
    ambiguity = _ambiguity_score(deterministic)
    consistency = _consistency_score(deterministic)
    downstream_risk = _downstream_risk_score(
        completeness=completeness,
        specificity=specificity,
        ambiguity=ambiguity,
        consistency=consistency,
    )
    overall = clamp_score(
        (completeness * 0.3)
        + (specificity * 0.26)
        + (consistency * 0.24)
        + ((1.0 - ambiguity) * 0.2)
    )
    overall = clamp_score(overall - (downstream_risk * 0.08) + 0.04)

    breakdown = JDQualityBreakdown(
        completeness_score=completeness,
        specificity_score=specificity,
        ambiguity_score=ambiguity,
        consistency_score=consistency,
        downstream_risk_score=downstream_risk,
        notes=_quality_notes(
            deterministic=deterministic,
            completeness=completeness,
            specificity=specificity,
            ambiguity=ambiguity,
            consistency=consistency,
            downstream_risk=downstream_risk,
        ),
    )
    return breakdown, overall


def _completeness_score(deterministic: DeterministicJobDescriptionExtraction) -> float:
    score = 0.2
    score += 0.12 if deterministic.title_candidates else 0.0
    score += 0.08 if deterministic.company_name_candidates else 0.0
    score += 0.1 if deterministic.sections else 0.0
    score += 0.12 if deterministic.requirement_markers else 0.0
    score += 0.08 if deterministic.years_experience_findings else 0.0
    score += 0.08 if deterministic.tool_platform_findings else 0.0
    score += 0.08 if deterministic.work_model_findings else 0.0
    score += 0.07 if deterministic.leadership_findings else 0.0
    score += 0.07 if deterministic.scope_indicator_findings else 0.0
    score += 0.08 if deterministic.domain_findings else 0.0
    return clamp_score(score)


def _specificity_score(deterministic: DeterministicJobDescriptionExtraction) -> float:
    score = 0.18
    score += min(len(deterministic.requirement_markers), 4) * 0.1
    score += min(len(deterministic.tool_platform_findings), 4) * 0.08
    score += min(len(deterministic.domain_findings), 3) * 0.08
    score += 0.08 if deterministic.years_experience_findings else 0.0
    score += 0.06 if deterministic.education_requirement_findings else 0.0
    score += min(len(deterministic.action_verb_findings), 4) * 0.04
    return clamp_score(score)


def _ambiguity_score(deterministic: DeterministicJobDescriptionExtraction) -> float:
    raw_text = fold_key(deterministic.raw_job_text)
    score = 0.12
    if not deterministic.requirement_markers:
        score += 0.18
    if len(deterministic.title_candidates) != 1:
        score += 0.14
    if len(deterministic.sections) <= 1:
        score += 0.14
    if not deterministic.tool_platform_findings:
        score += 0.08
    if not deterministic.domain_findings:
        score += 0.06
    score += sum(0.06 for phrase in _VAGUE_PHRASES if phrase in raw_text)
    return clamp_score(score)


def _consistency_score(deterministic: DeterministicJobDescriptionExtraction) -> float:
    score = 0.82
    work_models = {item.canonical_value for item in deterministic.work_model_findings}
    if "remote" in work_models and "onsite" in work_models:
        score -= 0.18
    if len({item.canonical_value for item in deterministic.title_candidates}) > 1:
        score -= 0.12
    leadership_values = {item.canonical_value for item in deterministic.leadership_findings}
    if "people_management" in leadership_values and "mentor" in leadership_values:
        score -= 0.04
    if not deterministic.sections:
        score -= 0.12
    return clamp_score(score)


def _downstream_risk_score(
    *,
    completeness: float,
    specificity: float,
    ambiguity: float,
    consistency: float,
) -> float:
    return clamp_score(
        ((1.0 - completeness) * 0.28)
        + ((1.0 - specificity) * 0.26)
        + (ambiguity * 0.28)
        + ((1.0 - consistency) * 0.18)
    )


def _quality_notes(
    *,
    deterministic: DeterministicJobDescriptionExtraction,
    completeness: float,
    specificity: float,
    ambiguity: float,
    consistency: float,
    downstream_risk: float,
) -> list[str]:
    notes: list[str] = []
    if completeness < 0.6:
        notes.append("JD is missing several structural anchors such as explicit requirements, company context, or work-model details.")
    if specificity < 0.6:
        notes.append("JD wording is light on concrete tools, quantified requirements, or named domains.")
    if ambiguity >= 0.5:
        notes.append("JD contains vague language that weakens downstream ranking confidence.")
    if consistency < 0.7:
        notes.append("JD contains internally mixed signals that may confuse role targeting.")
    if downstream_risk >= 0.5:
        notes.append("Downstream phases should weight this JD conservatively.")
    if deterministic.extraction_notes:
        notes.extend(deterministic.extraction_notes[:2])
    return stable_unique(notes)
