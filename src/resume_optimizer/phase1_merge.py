"""Phase 1 merge pipeline combining deterministic and LLM-enriched outputs."""

from __future__ import annotations

from typing import Any

from .normalization import normalize_title_taxonomy
from .phase1_deterministic_models import (
    DeterministicJobDescriptionExtraction,
    RequirementStrength,
)
from .phase1_jd_quality import score_job_description_quality
from .phase1_merge_confidence import (
    confidence_for_item,
    score_job_title_confidence,
    score_overall_parser_confidence,
    score_requirement_confidence,
    score_role_axis_confidence,
)
from .phase1_merge_normalization import (
    clamp_score,
    coerce_string_list,
    comparable_scalar_match,
    filter_grounded_behavior_values,
    filter_grounded_explicit_values,
    fold_key,
    is_grounded_explicit_value,
    stable_unique,
)
from .phase1_models import (
    DeliveryScopeLevel,
    DeliveryScopeRequirement,
    EducationLevel,
    EducationRequirement,
    JDQualityBreakdown,
    JobSeniorityLevel,
    LeadershipRequirement,
    LeadershipScope,
    Phase1JobAnalysis,
    PrioritizedRequirement,
    PrioritizedRequirementTier,
    RequirementConfidenceItem,
    RequirementConfidenceItemType,
    RecruiterIntentProfile,
)
from .phase1_recruiter_intent import infer_recruiter_intent_profile
from .phase1_role_modeling import InferredRoleAxes, infer_role_axes


def merge_phase1_deterministic_and_llm(
    deterministic: DeterministicJobDescriptionExtraction,
    llm_payload: dict[str, Any],
) -> Phase1JobAnalysis:
    """Merge deterministic extraction with LLM enrichment into final Phase 1 output."""

    merged_payload = merge_phase1_deterministic_and_llm_payload(
        deterministic=deterministic,
        llm_payload=llm_payload,
    )
    return Phase1JobAnalysis.model_validate(merged_payload)


def merge_phase1_deterministic_and_llm_payload(
    *,
    deterministic: DeterministicJobDescriptionExtraction,
    llm_payload: dict[str, Any],
) -> dict[str, Any]:
    """Return the inspectable merged payload before final model validation."""

    baseline, role_axes = build_phase1_deterministic_baseline(deterministic)
    merged = _merge_deterministic_baseline(
        payload=llm_payload,
        deterministic=deterministic,
        baseline=baseline,
    )
    repaired = _repair_phase1_payload(merged, deterministic)
    repaired = _apply_merge_scoring_and_notes(
        payload=repaired,
        llm_payload=llm_payload,
        deterministic=deterministic,
        role_axes=role_axes,
        baseline=baseline,
    )
    return repaired


def build_phase1_deterministic_baseline(
    deterministic: DeterministicJobDescriptionExtraction,
) -> tuple[dict[str, Any], InferredRoleAxes]:
    """Build the deterministic baseline that anchors the merge pipeline."""

    title = (
        deterministic.title_candidates[0].canonical_value
        if deterministic.title_candidates
        else None
    )
    role_axes = infer_role_axes(
        job_title=title,
        raw_job_text=deterministic.raw_job_text,
    )
    title_normalization = normalize_title_taxonomy(title) if title is not None else None
    years = [
        item.years
        for item in deterministic.years_experience_findings
        if item.minimum_like
    ]
    industry_domain = (
        deterministic.domain_findings[0].canonical_value
        if deterministic.domain_findings
        else None
    )
    recruiter_intent = infer_recruiter_intent_profile(deterministic, role_axes)
    jd_quality_breakdown, jd_quality_score = score_job_description_quality(deterministic)

    return (
        {
            "raw_job_text": deterministic.raw_job_text,
            "job_title": title,
            "company_name": (
                deterministic.company_name_candidates[0].canonical_value
                if deterministic.company_name_candidates
                else None
            ),
            "functional_role_family": role_axes.functional_role_family.value,
            "organizational_role_mode": role_axes.organizational_role_mode.value,
            "seniority_level": _safe_seniority_value(
                title_normalization.seniority_hint
                if title_normalization is not None
                else None
            ),
            "primary_responsibility_clusters": _responsibility_clusters_from_deterministic(
                deterministic
            ),
            "must_have_skills": [],
            "nice_to_have_skills": [],
            "required_tools_platforms": stable_unique(
                [item.canonical_value for item in deterministic.tool_platform_findings]
            ),
            "required_domains": stable_unique(
                [item.canonical_value for item in deterministic.domain_findings]
            ),
            "must_have_behaviors": stable_unique(
                [
                    item.canonical_value.replace("_", " ")
                    for item in deterministic.leadership_findings
                    if item.canonical_value
                    in {
                        "mentorship",
                        "technical_leadership",
                        "cross_functional_leadership",
                        "mentor",
                        "coach",
                        "lead",
                        "manage",
                        "stakeholder",
                    }
                ]
            ),
            "business_goal_signals": [],
            "impact_signals": [],
            "years_experience_requirement": min(years) if years else None,
            "education_requirement": _education_requirement_from_deterministic(deterministic),
            "leadership_requirement": _leadership_requirement_from_deterministic(
                deterministic
            ),
            "delivery_scope_requirement": _delivery_scope_requirement_from_deterministic(
                deterministic
            ),
            "constraint_signals": [],
            "work_model_signals": stable_unique(
                [item.canonical_value for item in deterministic.work_model_findings]
            ),
            "industry_domain": industry_domain,
            "key_action_verbs": stable_unique(
                [item.canonical_value for item in deterministic.action_verb_findings]
            ),
            "recruiter_intent": recruiter_intent.model_dump(mode="json"),
            "jd_quality_breakdown": jd_quality_breakdown.model_dump(mode="json"),
            "jd_quality_score": jd_quality_score,
            "parser_confidence": _deterministic_parser_confidence(deterministic),
            "requirement_confidence_by_item": _confidence_items_from_deterministic(
                deterministic,
                role_axes,
                title,
            ),
            "extraction_notes": list(deterministic.extraction_notes),
            "normalized_keywords": _normalized_keywords_from_deterministic(deterministic),
            "prioritized_requirements": _prioritized_requirements_from_deterministic(
                deterministic
            ),
        },
        role_axes,
    )


def _merge_deterministic_baseline(
    *,
    payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    merged = {**baseline, **payload}
    merged["raw_job_text"] = deterministic.raw_job_text

    for nested_field in (
        "education_requirement",
        "leadership_requirement",
        "delivery_scope_requirement",
        "recruiter_intent",
        "jd_quality_breakdown",
    ):
        merged[nested_field] = {
            **baseline.get(nested_field, {}),
            **(payload.get(nested_field) or {}),
        }

    for list_field in (
        "primary_responsibility_clusters",
        "must_have_skills",
        "nice_to_have_skills",
        "required_tools_platforms",
        "required_domains",
        "must_have_behaviors",
        "business_goal_signals",
        "impact_signals",
        "constraint_signals",
        "work_model_signals",
        "key_action_verbs",
        "extraction_notes",
        "normalized_keywords",
        "requirement_confidence_by_item",
        "prioritized_requirements",
    ):
        if list_field == "prioritized_requirements":
            payload_items = (
                payload.get(list_field)
                if isinstance(payload.get(list_field), list)
                else []
            )
            merged[list_field] = payload_items or (baseline.get(list_field) or [])
            continue
        if list_field == "requirement_confidence_by_item":
            merged[list_field] = [
                *(baseline.get(list_field) or []),
                *(
                    payload.get(list_field)
                    if isinstance(payload.get(list_field), list)
                    else []
                ),
            ]
            continue
        merged[list_field] = stable_unique(
            [
                *coerce_string_list(payload.get(list_field)),
                *coerce_string_list(baseline.get(list_field)),
            ]
        )

    for scalar_field in (
        "job_title",
        "company_name",
        "industry_domain",
        "years_experience_requirement",
    ):
        merged[scalar_field] = _prefer_explicit_deterministic_scalar(
            deterministic_value=baseline.get(scalar_field),
            llm_value=payload.get(scalar_field),
            payload=payload,
            item_type=_confidence_type_for_scalar_field(scalar_field),
        )

    return merged


def _repair_phase1_payload(
    payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
) -> dict[str, Any]:
    repaired = dict(payload)
    repaired["jd_quality_score"] = clamp_score(repaired.get("jd_quality_score"))
    repaired["parser_confidence"] = clamp_score(repaired.get("parser_confidence"))

    for field_name in (
        "primary_responsibility_clusters",
        "must_have_skills",
        "nice_to_have_skills",
        "required_tools_platforms",
        "required_domains",
        "must_have_behaviors",
        "business_goal_signals",
        "impact_signals",
        "constraint_signals",
        "work_model_signals",
        "key_action_verbs",
        "extraction_notes",
        "normalized_keywords",
    ):
        repaired[field_name] = stable_unique(
            coerce_string_list(repaired.get(field_name))
        )

    repaired["must_have_skills"] = filter_grounded_explicit_values(
        repaired.get("must_have_skills", []),
        deterministic,
    )
    repaired["nice_to_have_skills"] = [
        value
        for value in filter_grounded_explicit_values(
            repaired.get("nice_to_have_skills", []),
            deterministic,
        )
        if value.casefold() not in {item.casefold() for item in repaired["must_have_skills"]}
    ]
    repaired["required_tools_platforms"] = filter_grounded_explicit_values(
        repaired.get("required_tools_platforms", []),
        deterministic,
    )
    repaired["required_domains"] = filter_grounded_explicit_values(
        repaired.get("required_domains", []),
        deterministic,
    )
    repaired["work_model_signals"] = filter_grounded_explicit_values(
        repaired.get("work_model_signals", []),
        deterministic,
    )
    repaired["key_action_verbs"] = filter_grounded_explicit_values(
        repaired.get("key_action_verbs", []),
        deterministic,
    )
    repaired["must_have_behaviors"] = filter_grounded_behavior_values(
        repaired.get("must_have_behaviors", []),
        deterministic,
    )

    repaired["prioritized_requirements"] = _repair_prioritized_requirements(
        repaired.get("prioritized_requirements", []),
        repaired,
        deterministic,
    )
    repaired["recruiter_intent"] = _repair_recruiter_intent(
        repaired.get("recruiter_intent", {}),
    )
    repaired["jd_quality_breakdown"] = _repair_jd_quality_breakdown(
        repaired.get("jd_quality_breakdown", {}),
    )
    repaired["requirement_confidence_by_item"] = _repair_requirement_confidence_items(
        repaired.get("requirement_confidence_by_item", []),
        repaired,
    )

    if repaired["parser_confidence"] < 0.35 and not repaired["extraction_notes"]:
        repaired["extraction_notes"] = [
            "Low-confidence Phase 1 enrichment required conservative repair."
        ]

    return repaired


def _apply_merge_scoring_and_notes(
    *,
    payload: dict[str, Any],
    llm_payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    payload["recruiter_intent"] = _merge_recruiter_intent(
        payload=payload.get("recruiter_intent", {}),
        llm_payload=llm_payload.get("recruiter_intent") or {},
        deterministic=deterministic,
        role_axes=role_axes,
    )
    payload["jd_quality_breakdown"] = _merge_jd_quality_breakdown(
        payload.get("jd_quality_breakdown", {}),
        deterministic,
    )
    jd_quality_score = _merge_jd_quality_score(
        deterministic_score=baseline["jd_quality_score"],
        llm_score=payload.get("jd_quality_score"),
        jd_quality_breakdown=payload["jd_quality_breakdown"],
    )
    payload["jd_quality_score"] = jd_quality_score

    extraction_notes = stable_unique(
        [
            *coerce_string_list(payload.get("extraction_notes")),
            *_conflict_notes(payload, llm_payload, baseline),
            *_ambiguity_notes(payload, deterministic, role_axes),
        ]
    )
    payload["extraction_notes"] = extraction_notes

    payload["prioritized_requirements"] = _ensure_prioritized_requirements(
        payload,
        deterministic,
    )
    payload["requirement_confidence_by_item"] = _build_requirement_confidence_items(
        payload=payload,
        llm_payload=llm_payload,
        deterministic=deterministic,
        baseline=baseline,
        role_axes=role_axes,
        jd_quality_score=jd_quality_score,
    )

    ambiguity_count = sum(1 for note in extraction_notes if "Ambiguity:" in note)
    conflict_count = sum(1 for note in extraction_notes if "Conflict:" in note)
    inferred_item_count = sum(
        1
        for item in payload["requirement_confidence_by_item"]
        if any("inferred" in note.casefold() for note in item.get("notes", []))
    )
    payload["parser_confidence"] = score_overall_parser_confidence(
        deterministic_parser_confidence=baseline["parser_confidence"],
        llm_parser_confidence=(
            clamp_score(llm_payload.get("parser_confidence"))
            if llm_payload.get("parser_confidence") is not None
            else None
        ),
        jd_quality_score=jd_quality_score,
        ambiguity_count=ambiguity_count,
        conflict_count=conflict_count,
        inferred_item_count=inferred_item_count
        + (1 if payload["recruiter_intent"].get("confidence", 0.0) < 0.6 else 0),
    )
    if payload["parser_confidence"] < 0.35 and not payload["extraction_notes"]:
        payload["extraction_notes"] = [
            "Low-confidence merged Phase 1 output remains ambiguous."
        ]

    payload["normalized_keywords"] = stable_unique(
        [
            *payload.get("normalized_keywords", []),
            payload["recruiter_intent"].get("breadth_preference"),
            *payload["recruiter_intent"].get("domain_specific_emphasis", []),
            *payload["recruiter_intent"].get("pace_environment_signals", []),
            *(item.get("item_value") for item in payload["requirement_confidence_by_item"]),
        ]
    )
    return payload


def _build_requirement_confidence_items(
    *,
    payload: dict[str, Any],
    llm_payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
    baseline: dict[str, Any],
    role_axes: InferredRoleAxes,
    jd_quality_score: float,
) -> list[dict[str, Any]]:
    items: list[RequirementConfidenceItem] = []

    title_confidence = score_job_title_confidence(
        title=payload.get("job_title"),
        deterministic_title=baseline.get("job_title"),
        deterministic_confidence=(
            deterministic.title_candidates[0].confidence if deterministic.title_candidates else 0.0
        ),
        llm_confidence=confidence_for_item(
            llm_payload.get("requirement_confidence_by_item", []),
            RequirementConfidenceItemType.JOB_TITLE,
            payload.get("job_title"),
        ),
        deterministic=deterministic,
        jd_quality_score=jd_quality_score,
    )
    if payload.get("job_title"):
        items.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType.JOB_TITLE,
                item_value=payload["job_title"],
                confidence=title_confidence,
                notes=_inference_notes_for_scalar(
                    final_value=payload["job_title"],
                    deterministic_value=baseline.get("job_title"),
                    explicit=True,
                ),
            )
        )

    if payload.get("company_name"):
        company_confidence = score_requirement_confidence(
            value=payload["company_name"],
            deterministic=deterministic,
            llm_confidence=confidence_for_item(
                llm_payload.get("requirement_confidence_by_item", []),
                RequirementConfidenceItemType.COMPANY_NAME,
                payload["company_name"],
            ),
            explicit_grounded=True,
            jd_quality_score=jd_quality_score,
        )
        items.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType.COMPANY_NAME,
                item_value=payload["company_name"],
                confidence=company_confidence,
                notes=_inference_notes_for_scalar(
                    final_value=payload["company_name"],
                    deterministic_value=baseline.get("company_name"),
                    explicit=True,
                ),
            )
        )

    items.append(
        RequirementConfidenceItem(
            item_type=RequirementConfidenceItemType.FUNCTIONAL_ROLE_FAMILY,
            item_value=payload["functional_role_family"],
            confidence=score_role_axis_confidence(
                final_value=payload["functional_role_family"],
                deterministic_value=baseline["functional_role_family"],
                deterministic_confidence=role_axes.family_inference.confidence,
                llm_confidence=confidence_for_item(
                    llm_payload.get("requirement_confidence_by_item", []),
                    RequirementConfidenceItemType.FUNCTIONAL_ROLE_FAMILY,
                    payload["functional_role_family"],
                ),
                jd_quality_score=jd_quality_score,
                deterministic=deterministic,
            ),
            notes=_role_axis_notes(
                final_value=payload["functional_role_family"],
                deterministic_value=baseline["functional_role_family"],
                inference_notes=role_axes.family_inference.notes,
            ),
        )
    )
    items.append(
        RequirementConfidenceItem(
            item_type=RequirementConfidenceItemType.ORGANIZATIONAL_ROLE_MODE,
            item_value=payload["organizational_role_mode"],
            confidence=score_role_axis_confidence(
                final_value=payload["organizational_role_mode"],
                deterministic_value=baseline["organizational_role_mode"],
                deterministic_confidence=role_axes.organizational_inference.confidence,
                llm_confidence=confidence_for_item(
                    llm_payload.get("requirement_confidence_by_item", []),
                    RequirementConfidenceItemType.ORGANIZATIONAL_ROLE_MODE,
                    payload["organizational_role_mode"],
                ),
                jd_quality_score=jd_quality_score,
                deterministic=deterministic,
            ),
            notes=_role_axis_notes(
                final_value=payload["organizational_role_mode"],
                deterministic_value=baseline["organizational_role_mode"],
                inference_notes=role_axes.organizational_inference.notes,
            ),
        )
    )

    if payload.get("seniority_level"):
        items.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType.SENIORITY_LEVEL,
                item_value=payload["seniority_level"],
                confidence=score_requirement_confidence(
                    value=payload["seniority_level"],
                    deterministic=deterministic,
                    llm_confidence=confidence_for_item(
                        llm_payload.get("requirement_confidence_by_item", []),
                        RequirementConfidenceItemType.SENIORITY_LEVEL,
                        payload["seniority_level"],
                    ),
                    explicit_grounded=is_grounded_explicit_value(
                        payload["seniority_level"], deterministic
                    ),
                    jd_quality_score=jd_quality_score,
                    inferred=not is_grounded_explicit_value(
                        payload["seniority_level"], deterministic
                    ),
                ),
                notes=[
                    "Merged seniority remains inferred from title/body cues."
                ]
                if not is_grounded_explicit_value(payload["seniority_level"], deterministic)
                else [],
            )
        )

    for prioritized in payload.get("prioritized_requirements", []):
        item_type = RequirementConfidenceItemType(prioritized["requirement_type"])
        item_value = prioritized["requirement_text"]
        if any(
            existing.item_type == item_type and fold_key(existing.item_value) == fold_key(item_value)
            for existing in items
        ):
            continue
        explicit_grounded = is_grounded_explicit_value(item_value, deterministic)
        inferred = (
            item_type == RequirementConfidenceItemType.BUSINESS_GOAL_SIGNAL
            and not explicit_grounded
        )
        llm_confidence = confidence_for_item(
            llm_payload.get("requirement_confidence_by_item", []),
            item_type,
            item_value,
        )
        if (
            item_type == RequirementConfidenceItemType.BUSINESS_GOAL_SIGNAL
            and llm_confidence == 0.0
        ):
            llm_confidence = clamp_score(llm_payload.get("parser_confidence"))
        items.append(
            RequirementConfidenceItem(
                item_type=item_type,
                item_value=item_value,
                confidence=score_requirement_confidence(
                    value=item_value,
                    deterministic=deterministic,
                    llm_confidence=max(
                        llm_confidence,
                        clamp_score(prioritized.get("confidence")),
                    ),
                    explicit_grounded=explicit_grounded,
                    jd_quality_score=jd_quality_score,
                    inferred=inferred,
                ),
                notes=_item_notes(
                    item_type=item_type,
                    explicit_grounded=explicit_grounded,
                    inferred=inferred,
                ),
            )
        )

    return [item.model_dump(mode="json", exclude_none=True) for item in stable_unique(items)]


def _ensure_prioritized_requirements(
    payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[dict[str, Any]]:
    existing = list(payload.get("prioritized_requirements", []))
    seen = {
        (item.get("requirement_type"), fold_key(str(item.get("requirement_text", ""))))
        for item in existing
        if isinstance(item, dict)
    }
    rank = len(existing) + 1
    should_backfill = len(existing) < 2

    if should_backfill:
        for value in payload.get("must_have_skills", []):
            key = (
                RequirementConfidenceItemType.MUST_HAVE_SKILL.value,
                fold_key(value),
            )
            if key in seen:
                continue
            existing.append(
                PrioritizedRequirement(
                    requirement_text=value,
                    requirement_type=RequirementConfidenceItemType.MUST_HAVE_SKILL,
                    priority_rank=rank,
                    priority_tier=PrioritizedRequirementTier.MUST_HAVE,
                    confidence=0.72 if is_grounded_explicit_value(value, deterministic) else 0.45,
                    rationale="Backfilled from merged must-have skill list.",
                ).model_dump(mode="json", exclude_none=True)
            )
            seen.add(key)
            rank += 1

        for value in payload.get("required_tools_platforms", []):
            key = (
                RequirementConfidenceItemType.REQUIRED_TOOL_PLATFORM.value,
                fold_key(value),
            )
            if key in seen:
                continue
            existing.append(
                PrioritizedRequirement(
                    requirement_text=value,
                    requirement_type=RequirementConfidenceItemType.REQUIRED_TOOL_PLATFORM,
                    priority_rank=rank,
                    priority_tier=PrioritizedRequirementTier.IMPORTANT,
                    confidence=0.68 if is_grounded_explicit_value(value, deterministic) else 0.42,
                    rationale="Backfilled from merged required tools/platforms.",
                ).model_dump(mode="json", exclude_none=True)
            )
            seen.add(key)
            rank += 1

        for value in payload.get("business_goal_signals", []):
            key = (
                RequirementConfidenceItemType.BUSINESS_GOAL_SIGNAL.value,
                fold_key(value),
            )
            if key in seen:
                continue
            existing.append(
                PrioritizedRequirement(
                    requirement_text=value,
                    requirement_type=RequirementConfidenceItemType.BUSINESS_GOAL_SIGNAL,
                    priority_rank=rank,
                    priority_tier=PrioritizedRequirementTier.IMPORTANT,
                    confidence=0.58 if is_grounded_explicit_value(value, deterministic) else 0.46,
                    rationale="Backfilled recruiter-intent signal for downstream ranking.",
                ).model_dump(mode="json", exclude_none=True)
            )
            seen.add(key)
            rank += 1

    return _repair_prioritized_requirements(existing, payload, deterministic)


def _merge_jd_quality_score(
    *,
    deterministic_score: float,
    llm_score: Any,
    jd_quality_breakdown: dict[str, Any],
) -> float:
    llm_component = clamp_score(llm_score)
    breakdown_score = clamp_score(
        (
            jd_quality_breakdown.get("completeness_score", 0.0) * 0.3
            + jd_quality_breakdown.get("specificity_score", 0.0) * 0.26
            + jd_quality_breakdown.get("consistency_score", 0.0) * 0.24
            + (1.0 - jd_quality_breakdown.get("ambiguity_score", 0.0)) * 0.2
        )
        - (jd_quality_breakdown.get("downstream_risk_score", 0.0) * 0.08)
        + 0.04
    )
    return max(clamp_score(deterministic_score), breakdown_score, llm_component)


def _merge_jd_quality_breakdown(
    payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
) -> dict[str, Any]:
    deterministic_breakdown, _ = score_job_description_quality(deterministic)
    merged = {
        **deterministic_breakdown.model_dump(mode="json"),
        **(payload or {}),
    }
    return _repair_jd_quality_breakdown(merged)


def _merge_recruiter_intent(
    *,
    payload: dict[str, Any],
    llm_payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
) -> dict[str, Any]:
    deterministic_intent = infer_recruiter_intent_profile(
        deterministic,
        role_axes,
    ).model_dump(mode="json")
    merged = {**deterministic_intent, **(payload or {})}

    llm_confidence = clamp_score(
        (llm_payload or {}).get("confidence", merged.get("confidence"))
    )
    deterministic_confidence = clamp_score(deterministic_intent.get("confidence"))
    if (
        llm_payload.get("likely_success_shape")
        and llm_confidence >= deterministic_confidence + 0.08
    ):
        merged["likely_success_shape"] = llm_payload["likely_success_shape"]
    else:
        merged["likely_success_shape"] = deterministic_intent.get("likely_success_shape")

    merged["notes"] = stable_unique(
        [
            *coerce_string_list(deterministic_intent.get("notes")),
            *coerce_string_list((payload or {}).get("notes")),
        ]
    )
    merged["confidence"] = max(deterministic_confidence, llm_confidence * 0.92)
    return _repair_recruiter_intent(merged)


def _repair_recruiter_intent(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    emphasis = raw.get("emphasis_profile") if isinstance(raw.get("emphasis_profile"), dict) else {}
    likely_success_shape = raw.get("likely_success_shape")
    repaired = RecruiterIntentProfile(
        likely_success_shape=(
            str(likely_success_shape).strip() if likely_success_shape not in {None, ""} else None
        ),
        emphasis_profile={
            "architecture": clamp_score(emphasis.get("architecture")),
            "execution": clamp_score(emphasis.get("execution")),
            "collaboration": clamp_score(emphasis.get("collaboration")),
            "leadership": clamp_score(emphasis.get("leadership")),
        },
        persuasive_evidence_types=list(raw.get("persuasive_evidence_types") or []),
        pace_environment_signals=stable_unique(coerce_string_list(raw.get("pace_environment_signals"))),
        domain_specific_emphasis=stable_unique(coerce_string_list(raw.get("domain_specific_emphasis"))),
        breadth_preference=raw.get("breadth_preference") or "unknown",
        confidence=clamp_score(raw.get("confidence")),
        notes=stable_unique(coerce_string_list(raw.get("notes"))),
    )
    return repaired.model_dump(mode="json")


def _repair_jd_quality_breakdown(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    repaired = JDQualityBreakdown(
        completeness_score=clamp_score(raw.get("completeness_score")),
        specificity_score=clamp_score(raw.get("specificity_score")),
        ambiguity_score=clamp_score(raw.get("ambiguity_score")),
        consistency_score=clamp_score(raw.get("consistency_score")),
        downstream_risk_score=clamp_score(raw.get("downstream_risk_score")),
        notes=stable_unique(coerce_string_list(raw.get("notes"))),
    )
    return repaired.model_dump(mode="json")


def _conflict_notes(
    payload: dict[str, Any],
    llm_payload: dict[str, Any],
    baseline: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    for field_name, label in (
        ("job_title", "title"),
        ("company_name", "company"),
        ("industry_domain", "industry domain"),
        ("years_experience_requirement", "years-of-experience"),
    ):
        deterministic_value = baseline.get(field_name)
        llm_value = llm_payload.get(field_name)
        final_value = payload.get(field_name)
        if (
            deterministic_value is None
            or llm_value is None
            or llm_value == ""
            or llm_value == []
        ):
            continue
        if comparable_scalar_match(str(deterministic_value), str(llm_value)):
            continue
        notes.append(
            f"Conflict: deterministic {label} '{deterministic_value}' outranked conflicting LLM value '{llm_value}'; final value is '{final_value}'."
        )
    return notes


def _ambiguity_notes(
    payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
) -> list[str]:
    notes: list[str] = []
    if role_axes.family_inference.confidence < 0.55:
        notes.append(
            f"Ambiguity: functional role family remains weakly signaled; using '{payload['functional_role_family']}'."
        )
    if role_axes.organizational_inference.confidence < 0.55:
        notes.append(
            f"Ambiguity: organizational role mode remains weakly signaled; using '{payload['organizational_role_mode']}'."
        )
    if payload.get("business_goal_signals"):
        for value in payload["business_goal_signals"]:
            if not is_grounded_explicit_value(value, deterministic):
                notes.append(
                    f"Ambiguity: recruiter-intent signal '{value}' is inferred rather than explicit."
                )
    return notes


def _inference_notes_for_scalar(
    *,
    final_value: str,
    deterministic_value: str | None,
    explicit: bool,
) -> list[str]:
    notes: list[str] = []
    if explicit:
        notes.append("Explicit JD fact retained in merge.")
    if deterministic_value and fold_key(final_value) != fold_key(deterministic_value):
        notes.append(
            "Final value differs from the strongest deterministic candidate."
        )
    return notes


def _role_axis_notes(
    *,
    final_value: str,
    deterministic_value: str,
    inference_notes: list[str],
) -> list[str]:
    notes = list(inference_notes)
    notes.append("Role axis is inferred from JD cues rather than explicit labels.")
    if fold_key(final_value) != fold_key(deterministic_value):
        notes.append("LLM enrichment changed the deterministic role-axis guess.")
    return stable_unique(notes)


def _item_notes(
    *,
    item_type: RequirementConfidenceItemType,
    explicit_grounded: bool,
    inferred: bool,
) -> list[str]:
    notes: list[str] = []
    if explicit_grounded:
        notes.append("Explicit JD signal.")
    if inferred:
        notes.append("LLM-only inferred signal; not explicit in JD wording.")
    if item_type == RequirementConfidenceItemType.BUSINESS_GOAL_SIGNAL:
        notes.append("Recruiter-intent signal for downstream ranking.")
    return stable_unique(notes)


def _education_requirement_from_deterministic(
    deterministic: DeterministicJobDescriptionExtraction,
) -> dict[str, Any]:
    levels = {item.canonical_value for item in deterministic.education_requirement_findings}
    minimum_level = None
    preferred_level = None
    for candidate in ("doctorate", "masters", "bachelors"):
        if candidate in levels:
            minimum_level = candidate
            break
    if minimum_level == "bachelors" and "masters" in levels:
        preferred_level = "masters"
    return EducationRequirement(
        minimum_level=EducationLevel(minimum_level) if minimum_level in EducationLevel._value2member_map_ else None,
        preferred_level=EducationLevel(preferred_level) if preferred_level in EducationLevel._value2member_map_ else None,
        fields_of_study=stable_unique(
            [
                item.canonical_value.replace("_", " ").title()
                for item in deterministic.education_requirement_findings
                if item.canonical_value in {"computer_science", "software_engineering"}
            ]
        ),
        certifications=[],
        required=minimum_level is not None,
    ).model_dump(mode="json", exclude_none=True)


def _leadership_requirement_from_deterministic(
    deterministic: DeterministicJobDescriptionExtraction,
) -> dict[str, Any]:
    values = {item.canonical_value for item in deterministic.leadership_findings}
    scope = None
    if any(value in values for value in {"people_management", "manage"}):
        scope = LeadershipScope.PEOPLE_MANAGEMENT
    elif any(
        value in values
        for value in {"technical_leadership", "lead", "mentor", "mentorship"}
    ):
        scope = LeadershipScope.TECHNICAL_LEADERSHIP
    elif "coach" in values:
        scope = LeadershipScope.MENTORSHIP
    return LeadershipRequirement(
        scope=scope,
        people_management_required=any(
            value in values for value in {"people_management", "manage"}
        ),
        mentoring_expected=any(
            value in values for value in {"mentor", "mentorship", "coach"}
        ),
        strategy_ownership_expected=any(
            value in values for value in {"strategy", "roadmap", "stakeholder"}
        ),
        notes=[],
    ).model_dump(mode="json", exclude_none=True)


def _delivery_scope_requirement_from_deterministic(
    deterministic: DeterministicJobDescriptionExtraction,
) -> dict[str, Any]:
    values = {item.canonical_value for item in deterministic.scope_indicator_findings}
    level = None
    if any("organization" in value for value in values):
        level = DeliveryScopeLevel.ORGANIZATION
    elif any(
        value in values
        for value in {
            "multi_team",
            "cross_functional",
            "cross_functional_leadership",
            "work_across",
        }
    ):
        level = DeliveryScopeLevel.MULTI_TEAM
    elif any(value in values for value in {"platform", "architecture"}):
        level = DeliveryScopeLevel.PLATFORM
    return DeliveryScopeRequirement(
        scope_level=level,
        cross_functional_coordination_required=any(
            value in values
            for value in {"cross_functional", "stakeholder", "work_across"}
        ),
        roadmap_ownership_expected=any(
            value in values for value in {"roadmap", "strategy"}
        ),
        notes=[],
    ).model_dump(mode="json", exclude_none=True)


def _deterministic_jd_quality_score(
    deterministic: DeterministicJobDescriptionExtraction,
) -> float:
    score = 0.4
    score += min(len(deterministic.sections), 5) * 0.07
    score += min(len(deterministic.requirement_markers), 5) * 0.05
    score += 0.06 if deterministic.title_candidates else 0.0
    score += 0.06 if deterministic.years_experience_findings else 0.0
    score += 0.04 if deterministic.tool_platform_findings else 0.0
    return min(score, 0.95)


def _deterministic_parser_confidence(
    deterministic: DeterministicJobDescriptionExtraction,
) -> float:
    score = 0.42
    if deterministic.title_candidates:
        score += 0.08
    if deterministic.company_name_candidates:
        score += 0.06
    score += min(len(deterministic.requirement_markers), 4) * 0.05
    score += min(len(deterministic.tool_platform_findings), 4) * 0.03
    score += min(len(deterministic.domain_findings), 3) * 0.03
    return min(score, 0.9)


def _confidence_items_from_deterministic(
    deterministic: DeterministicJobDescriptionExtraction,
    role_axes: InferredRoleAxes,
    title: str | None,
) -> list[dict[str, Any]]:
    items: list[RequirementConfidenceItem] = []
    if title is not None and deterministic.title_candidates:
        items.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType.JOB_TITLE,
                item_value=title,
                confidence=deterministic.title_candidates[0].confidence,
                notes=["Explicit JD fact retained in deterministic baseline."],
            )
        )
    if deterministic.company_name_candidates:
        items.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType.COMPANY_NAME,
                item_value=deterministic.company_name_candidates[0].canonical_value,
                confidence=deterministic.company_name_candidates[0].confidence,
                notes=["Explicit JD fact retained in deterministic baseline."],
            )
        )
    items.append(
        RequirementConfidenceItem(
            item_type=RequirementConfidenceItemType.FUNCTIONAL_ROLE_FAMILY,
            item_value=role_axes.functional_role_family.value,
            confidence=role_axes.family_inference.confidence,
            notes=stable_unique(
                [
                    *role_axes.family_inference.notes,
                    "Role axis is inferred from JD cues rather than explicit labels.",
                ]
            ),
        )
    )
    items.append(
        RequirementConfidenceItem(
            item_type=RequirementConfidenceItemType.ORGANIZATIONAL_ROLE_MODE,
            item_value=role_axes.organizational_role_mode.value,
            confidence=role_axes.organizational_inference.confidence,
            notes=stable_unique(
                [
                    *role_axes.organizational_inference.notes,
                    "Role axis is inferred from JD cues rather than explicit labels.",
                ]
            ),
        )
    )
    for item in deterministic.tool_platform_findings[:5]:
        items.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType.REQUIRED_TOOL_PLATFORM,
                item_value=item.canonical_value,
                confidence=item.confidence,
                notes=["Explicit JD signal."],
            )
        )
    for item in deterministic.domain_findings[:5]:
        items.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType.REQUIRED_DOMAIN,
                item_value=item.canonical_value,
                confidence=item.confidence,
                notes=["Explicit JD signal."],
            )
        )
    return [item.model_dump(mode="json", exclude_none=True) for item in items]


def _normalized_keywords_from_deterministic(
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[str]:
    return stable_unique(
        [
            *[item.keyword for item in deterministic.repeated_keyword_findings[:15]],
            *[item.canonical_value for item in deterministic.tool_platform_findings[:10]],
            *[item.canonical_value for item in deterministic.domain_findings[:5]],
            *[item.canonical_value for item in deterministic.action_verb_findings[:8]],
        ]
    )


def _prioritized_requirements_from_deterministic(
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[dict[str, Any]]:
    items: list[PrioritizedRequirement] = []
    rank = 1
    for item in deterministic.requirement_markers[:10]:
        tier = {
            RequirementStrength.MUST_HAVE: PrioritizedRequirementTier.MUST_HAVE,
            RequirementStrength.PREFERRED: PrioritizedRequirementTier.IMPORTANT,
            RequirementStrength.BONUS: PrioritizedRequirementTier.NICE_TO_HAVE,
        }[item.strength]
        items.append(
            PrioritizedRequirement(
                requirement_text=item.canonical_text,
                requirement_type=RequirementConfidenceItemType.REQUIREMENT_MARKER,
                priority_rank=rank,
                priority_tier=tier,
                confidence=item.confidence,
                rationale=f"Derived from deterministic {item.strength.value} marker.",
            )
        )
        rank += 1
    return [item.model_dump(mode="json", exclude_none=True) for item in items]


def _responsibility_clusters_from_deterministic(
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[str]:
    clusters: list[str] = []
    for section in deterministic.sections:
        if section.kind.value != "responsibilities":
            continue
        lines = (
            section.text.splitlines()[1:]
            if section.heading
            else section.text.splitlines()
        )
        clusters.extend(line for line in lines if line)
    return stable_unique(clusters[:6])


def _safe_seniority_value(value: str | None) -> str | None:
    if value is None:
        return None
    if value in JobSeniorityLevel._value2member_map_:
        return value
    if value == "lead":
        return JobSeniorityLevel.SENIOR.value
    return None


def _prefer_explicit_deterministic_scalar(
    *,
    deterministic_value: Any,
    llm_value: Any,
    payload: dict[str, Any],
    item_type: RequirementConfidenceItemType | None,
) -> Any:
    if deterministic_value is None or deterministic_value == "" or deterministic_value == []:
        return llm_value
    if llm_value is None or llm_value == "" or llm_value == []:
        return deterministic_value
    llm_confidence = confidence_for_item(
        payload.get("requirement_confidence_by_item", []),
        item_type,
        llm_value,
    )
    if llm_confidence >= 0.95:
        return llm_value
    return deterministic_value


def _confidence_type_for_scalar_field(
    field_name: str,
) -> RequirementConfidenceItemType | None:
    return {
        "job_title": RequirementConfidenceItemType.JOB_TITLE,
        "company_name": RequirementConfidenceItemType.COMPANY_NAME,
        "industry_domain": RequirementConfidenceItemType.INDUSTRY_DOMAIN,
    }.get(field_name)


def _repair_requirement_confidence_items(
    values: list[dict[str, Any]],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    allowed_scalar_values = {
        RequirementConfidenceItemType.JOB_TITLE.value: {payload.get("job_title")},
        RequirementConfidenceItemType.COMPANY_NAME.value: {payload.get("company_name")},
        RequirementConfidenceItemType.FUNCTIONAL_ROLE_FAMILY.value: {
            payload.get("functional_role_family")
        },
        RequirementConfidenceItemType.ORGANIZATIONAL_ROLE_MODE.value: {
            payload.get("organizational_role_mode")
        },
        RequirementConfidenceItemType.SENIORITY_LEVEL.value: {
            payload.get("seniority_level")
        },
        RequirementConfidenceItemType.INDUSTRY_DOMAIN.value: {
            payload.get("industry_domain")
        },
    }
    allowed_prioritized = {
        (
            fold_key(str(item.get("requirement_text", ""))),
            str(item.get("requirement_type", "")),
        )
        for item in payload.get("prioritized_requirements", [])
    }
    for raw_item in values:
        if not isinstance(raw_item, dict):
            continue
        item_type = str(raw_item.get("item_type", "")).strip()
        item_value = str(raw_item.get("item_value", "")).strip()
        if not item_type or not item_value:
            continue
        key = (item_type, fold_key(item_value))
        if key in seen:
            continue
        if item_type in allowed_scalar_values:
            if item_value not in {value for value in allowed_scalar_values[item_type] if value}:
                continue
        elif (fold_key(item_value), item_type) not in allowed_prioritized:
            continue
        seen.add(key)
        repaired.append(
            RequirementConfidenceItem(
                item_type=RequirementConfidenceItemType(item_type),
                item_value=item_value,
                confidence=clamp_score(raw_item.get("confidence")),
                notes=coerce_string_list(raw_item.get("notes")),
            ).model_dump(mode="json", exclude_none=True)
        )
    return repaired


def _repair_prioritized_requirements(
    values: list[dict[str, Any]],
    payload: dict[str, Any],
    deterministic: DeterministicJobDescriptionExtraction,
) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    rank = 1
    seen: set[tuple[str, str]] = set()
    for raw_item in values:
        if not isinstance(raw_item, dict):
            continue
        requirement_text = str(raw_item.get("requirement_text", "")).strip()
        requirement_type = str(raw_item.get("requirement_type", "")).strip()
        if not requirement_text or not requirement_type:
            continue
        if (
            requirement_type == RequirementConfidenceItemType.MUST_HAVE_SKILL.value
            and not is_grounded_explicit_value(requirement_text, deterministic)
        ):
            continue
        key = (requirement_type, fold_key(requirement_text))
        if key in seen:
            continue
        seen.add(key)
        tier_value = str(
            raw_item.get(
                "priority_tier",
                PrioritizedRequirementTier.IMPORTANT.value,
            )
        )
        confidence = clamp_score(raw_item.get("confidence"))
        if tier_value == PrioritizedRequirementTier.CRITICAL.value and confidence < 0.5:
            tier_value = PrioritizedRequirementTier.MUST_HAVE.value
        repaired.append(
            PrioritizedRequirement(
                requirement_text=requirement_text,
                requirement_type=RequirementConfidenceItemType(requirement_type),
                priority_rank=rank,
                priority_tier=PrioritizedRequirementTier(tier_value),
                confidence=confidence,
                rationale=str(raw_item.get("rationale")).strip() or None,
            ).model_dump(mode="json", exclude_none=True)
        )
        rank += 1
    if not repaired:
        return payload.get("prioritized_requirements", [])
    return repaired
