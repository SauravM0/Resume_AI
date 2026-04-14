"""Deterministic recruiter-intent extraction for Phase 1."""

from __future__ import annotations

from .phase1_deterministic_models import DeterministicJobDescriptionExtraction
from .phase1_merge_normalization import clamp_score, stable_unique
from .phase1_models import (
    BreadthPreference,
    IntentEmphasisProfile,
    PersuasiveEvidenceType,
    RecruiterIntentProfile,
)
from .phase1_role_modeling import InferredRoleAxes


def infer_recruiter_intent_profile(
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
) -> RecruiterIntentProfile:
    """Infer an inspectable recruiter-intent profile from deterministic evidence."""

    architecture_hits = _count_matches(
        deterministic.scope_indicator_findings,
        {"architecture", "platform", "system"},
    )
    execution_hits = len(deterministic.requirement_markers) + _count_matches(
        deterministic.action_verb_findings,
        {"build", "improve", "ship", "deliver", "execute", "drive"},
    )
    collaboration_hits = _count_matches(
        deterministic.scope_indicator_findings,
        {"cross_functional", "work_across", "multi_team", "stakeholder"},
    ) + _count_matches(
        deterministic.leadership_findings,
        {"stakeholder", "cross_functional_leadership"},
    )
    leadership_hits = _count_matches(
        deterministic.leadership_findings,
        {"mentor", "mentorship", "lead", "manage", "people_management", "coach", "strategy", "roadmap"},
    )

    emphasis = IntentEmphasisProfile(
        architecture=_axis_score(architecture_hits, bonus=1 if role_axes.functional_role_family.value in {"platform", "backend", "fullstack"} else 0),
        execution=_axis_score(execution_hits, bonus=1 if deterministic.years_experience_findings else 0),
        collaboration=_axis_score(collaboration_hits, bonus=1 if deterministic.work_model_findings else 0),
        leadership=_axis_score(leadership_hits, bonus=1 if role_axes.organizational_role_mode.value in {"tech_lead", "people_manager", "director_or_head"} else 0),
    )

    evidence_types: list[PersuasiveEvidenceType] = []
    if emphasis.architecture >= 0.6:
        evidence_types.append(PersuasiveEvidenceType.ARCHITECTURE_DECISIONS)
    if emphasis.execution >= 0.6:
        evidence_types.append(PersuasiveEvidenceType.EXECUTION_DELIVERY)
    if emphasis.collaboration >= 0.55:
        evidence_types.append(PersuasiveEvidenceType.CROSS_FUNCTIONAL_LEADERSHIP)
    if emphasis.leadership >= 0.55:
        evidence_types.append(
            PersuasiveEvidenceType.PEOPLE_LEADERSHIP
            if role_axes.organizational_role_mode.value in {"people_manager", "director_or_head"}
            else PersuasiveEvidenceType.CROSS_FUNCTIONAL_LEADERSHIP
        )
    if deterministic.domain_findings:
        evidence_types.append(PersuasiveEvidenceType.DOMAIN_DEPTH)
    if any(item.keyword in {"reliability", "observability"} for item in deterministic.repeated_keyword_findings):
        evidence_types.append(PersuasiveEvidenceType.RELIABILITY_SCALE)
    if role_axes.organizational_role_mode.value == "founder_or_generalist":
        evidence_types.append(PersuasiveEvidenceType.GENERALIST_RANGE)

    pace_environment_signals = _pace_environment_signals(deterministic)
    domain_specific_emphasis = stable_unique(
        [
            item.canonical_value.replace("-", " ").replace("_", " ")
            for item in deterministic.domain_findings[:5]
        ]
    )

    breadth_preference = _breadth_preference(
        deterministic=deterministic,
        role_axes=role_axes,
        collaboration_score=emphasis.collaboration,
        architecture_score=emphasis.architecture,
    )
    confidence = _intent_confidence(
        deterministic=deterministic,
        role_axes=role_axes,
        emphasis=emphasis,
    )
    notes = _intent_notes(
        deterministic=deterministic,
        breadth_preference=breadth_preference,
        evidence_types=evidence_types,
        confidence=confidence,
    )

    return RecruiterIntentProfile(
        likely_success_shape=_likely_success_shape(
            deterministic=deterministic,
            role_axes=role_axes,
            emphasis=emphasis,
            breadth_preference=breadth_preference,
        ),
        emphasis_profile=emphasis,
        persuasive_evidence_types=stable_unique(evidence_types),
        pace_environment_signals=pace_environment_signals,
        domain_specific_emphasis=domain_specific_emphasis,
        breadth_preference=breadth_preference,
        confidence=confidence,
        notes=notes,
    )


def _axis_score(raw_hits: int, *, bonus: int = 0) -> float:
    return clamp_score(0.18 + (min(raw_hits + bonus, 5) * 0.14))


def _count_matches(findings, allowed_values: set[str]) -> int:
    return sum(1 for item in findings if item.canonical_value in allowed_values)


def _pace_environment_signals(
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[str]:
    raw_text = deterministic.raw_job_text.casefold()
    signals: list[str] = []
    if any(token in raw_text for token in ("founding", "early-stage", "startup", "fast-paced", "move faster")):
        signals.append("startup pace")
    if any(token in raw_text for token in ("regulated", "compliance", "enterprise", "internal tooling")):
        signals.append("structured operating environment")
    if any(item.canonical_value == "remote" for item in deterministic.work_model_findings):
        signals.append("distributed collaboration")
    if any(item.canonical_value == "hybrid" for item in deterministic.work_model_findings):
        signals.append("hybrid coordination")
    if any(item.canonical_value == "onsite" for item in deterministic.work_model_findings):
        signals.append("onsite execution cadence")
    return stable_unique(signals)


def _breadth_preference(
    *,
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
    collaboration_score: float,
    architecture_score: float,
) -> BreadthPreference:
    breadth_hits = 0
    if role_axes.organizational_role_mode.value == "founder_or_generalist":
        breadth_hits += 2
    if role_axes.functional_role_family.value == "fullstack":
        breadth_hits += 2
    if collaboration_score >= 0.6:
        breadth_hits += 1
    if len(deterministic.tool_platform_findings) >= 3:
        breadth_hits += 1

    specialization_hits = 0
    if len(deterministic.domain_findings) >= 2:
        specialization_hits += 1
    if architecture_score >= 0.7 and role_axes.functional_role_family.value in {"platform", "security", "ml", "data"}:
        specialization_hits += 1
    if len(deterministic.requirement_markers) >= 3 and len(deterministic.tool_platform_findings) <= 2:
        specialization_hits += 1

    if breadth_hits >= specialization_hits + 2:
        return BreadthPreference.BREADTH
    if specialization_hits >= breadth_hits + 2:
        return BreadthPreference.SPECIALIZATION
    if breadth_hits or specialization_hits:
        return BreadthPreference.BALANCED
    return BreadthPreference.UNKNOWN


def _likely_success_shape(
    *,
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
    emphasis: IntentEmphasisProfile,
    breadth_preference: BreadthPreference,
) -> str | None:
    if emphasis.architecture >= emphasis.execution and emphasis.architecture >= 0.65:
        return "Shows architecture ownership that improves system reliability and delivery at team scale."
    if emphasis.leadership >= 0.65 and emphasis.collaboration >= 0.55:
        return "Leads cross-team execution, mentors others, and aligns stakeholders to deliver results."
    if breadth_preference is BreadthPreference.BREADTH:
        return "Demonstrates broad ownership across functions, tools, and delivery contexts."
    if deterministic.requirement_markers:
        return "Matches explicit requirements with concrete shipped outcomes and credible execution depth."
    if role_axes.organizational_role_mode.value != "unknown":
        return f"Fits a {role_axes.organizational_role_mode.value.replace('_', ' ')} story supported by the JD cues."
    return None


def _intent_confidence(
    *,
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
    emphasis: IntentEmphasisProfile,
) -> float:
    signal_count = (
        len(deterministic.requirement_markers)
        + len(deterministic.scope_indicator_findings)
        + len(deterministic.leadership_findings)
        + len(deterministic.domain_findings)
    )
    role_confidence = max(
        role_axes.family_inference.confidence,
        role_axes.organizational_inference.confidence,
    )
    emphasis_strength = max(
        emphasis.architecture,
        emphasis.execution,
        emphasis.collaboration,
        emphasis.leadership,
    )
    return clamp_score(0.28 + (min(signal_count, 6) * 0.08) + (role_confidence * 0.2) + (emphasis_strength * 0.12))


def _intent_notes(
    *,
    deterministic: DeterministicJobDescriptionExtraction,
    breadth_preference: BreadthPreference,
    evidence_types: list[PersuasiveEvidenceType],
    confidence: float,
) -> list[str]:
    notes: list[str] = []
    if confidence < 0.55:
        notes.append("Recruiter-intent remains weakly grounded because the JD is structurally sparse.")
    if breadth_preference is BreadthPreference.BREADTH:
        notes.append("Signals point toward a broad candidate story rather than narrow specialization.")
    elif breadth_preference is BreadthPreference.SPECIALIZATION:
        notes.append("Signals point toward depth in a focused domain or technical area.")
    if PersuasiveEvidenceType.DOMAIN_DEPTH in evidence_types and not deterministic.domain_findings:
        notes.append("Domain-depth persuasion is inferred from broader wording rather than explicit domain labels.")
    return stable_unique(notes)
