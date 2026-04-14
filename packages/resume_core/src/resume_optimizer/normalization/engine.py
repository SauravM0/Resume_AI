"""Taxonomy-backed normalization helpers for comparable job and profile terms."""

from __future__ import annotations

import re

from ..phase1_role_modeling import (
    compatibility_role_type_value,
    infer_functional_role_family,
    infer_organizational_role_mode,
)
from .models import (
    EvidenceNormalizationBundle,
    NormalizationStatus,
    NormalizedTerm,
    TitleNormalization,
)
from .taxonomy import load_taxonomy, load_title_taxonomy

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_PRESERVE_UPPER = {"AI", "API", "AWS", "BI", "GCP", "ML", "SQL", "UI", "UX"}
_PRESERVE_MIXED = {
    "FastAPI",
    "GitHub",
    "GitHub Actions",
    "JavaScript",
    "Kubernetes",
    "LaTeX",
    "Node.js",
    "PostgreSQL",
    "TypeScript",
}


def normalize_skill(value: str) -> NormalizedTerm:
    """Normalize a raw skill into a canonical comparable skill term."""

    return _normalize_with_taxonomy(value, taxonomy_name="skill", config_name="skills")


def normalize_tool(value: str) -> NormalizedTerm:
    """Normalize a raw tool or framework into a canonical comparable term."""

    return _normalize_with_taxonomy(value, taxonomy_name="tool", config_name="skills")


def normalize_tool_platform(value: str) -> NormalizedTerm:
    """Normalize a raw tool or platform term into a canonical term."""

    return _normalize_with_taxonomy(value, taxonomy_name="tool_platform", config_name="tool_platforms")


def normalize_cloud_service(value: str) -> NormalizedTerm:
    """Normalize a raw cloud service or provider term into a canonical term."""

    return _normalize_with_taxonomy(value, taxonomy_name="cloud_service", config_name="cloud_services")


def normalize_framework(value: str) -> NormalizedTerm:
    """Normalize a raw framework or library term into a canonical term."""

    return _normalize_with_taxonomy(value, taxonomy_name="framework", config_name="frameworks")


def normalize_programming_language(value: str) -> NormalizedTerm:
    """Normalize a raw programming language term into a canonical term."""

    return _normalize_with_taxonomy(value, taxonomy_name="programming_language", config_name="programming_languages")


def normalize_domain(value: str) -> NormalizedTerm:
    """Normalize a raw domain or specialty area into a canonical domain term."""

    result = _normalize_with_taxonomy(value, taxonomy_name="domain", config_name="domains")
    if result.status == NormalizationStatus.PASSTHROUGH:
        slug = result.canonical.casefold().replace(" ", "-")
        return result.model_copy(update={"canonical": slug, "matched_by": "slug"})
    return result


def normalize_action_verb(value: str) -> NormalizedTerm:
    """Normalize a raw action verb into a canonical explainability token."""

    result = _normalize_with_taxonomy(value, taxonomy_name="action_verb", config_name="action_verbs")
    if result.status == NormalizationStatus.PASSTHROUGH:
        return result.model_copy(update={"canonical": result.canonical.casefold(), "matched_by": "lemma"})
    return result


def normalize_leadership_phrase(value: str) -> NormalizedTerm:
    """Normalize a raw leadership phrase into a canonical comparable token."""

    return _normalize_with_taxonomy(
        value,
        taxonomy_name="leadership_phrase",
        config_name="leadership_phrases",
    )


def normalize_ownership_phrase(value: str) -> NormalizedTerm:
    """Normalize a raw ownership phrase into a canonical comparable token."""

    return _normalize_with_taxonomy(
        value,
        taxonomy_name="ownership_phrase",
        config_name="ownership_phrases",
    )


def normalize_delivery_scope_phrase(value: str) -> NormalizedTerm:
    """Normalize a raw delivery-scope phrase into a canonical comparable token."""

    return _normalize_with_taxonomy(
        value,
        taxonomy_name="delivery_scope_phrase",
        config_name="delivery_scope_phrases",
    )


def normalize_stakeholder_phrase(value: str) -> NormalizedTerm:
    """Normalize a raw stakeholder phrase into a canonical comparable token."""

    return _normalize_with_taxonomy(
        value,
        taxonomy_name="stakeholder_phrase",
        config_name="stakeholder_phrases",
    )


def normalize_role_taxonomy(value: str) -> NormalizedTerm:
    """Normalize a raw role-type label into the shared role taxonomy."""

    return _normalize_with_taxonomy(value, taxonomy_name="role_type", config_name="role_types")


def normalize_seniority_taxonomy(value: str) -> NormalizedTerm:
    """Normalize a raw seniority label into the shared seniority taxonomy."""

    return _normalize_with_taxonomy(value, taxonomy_name="seniority", config_name="seniority")


def normalize_title_taxonomy(value: str) -> TitleNormalization:
    """Normalize a raw title and derive independent functional and org hints."""

    cleaned = _normalize_text(value)
    taxonomy = load_title_taxonomy()

    if not cleaned:
        raise ValueError("title must not be empty")

    expanded = " ".join(
        taxonomy.aliases.get(_fold_key(part), part)
        for part in cleaned.split()
    )
    folded_expanded = _fold_key(expanded)

    for canonical, aliases in taxonomy.canonical_titles.items():
        alias_keys = {_fold_key(alias) for alias in aliases}
        canonical_key = _fold_key(canonical)
        if folded_expanded == canonical_key:
            return _build_title_result(
                raw=cleaned,
                canonical=canonical,
                status=NormalizationStatus.EXACT,
                confidence=1.0,
                matched_by="canonical",
            )
        if folded_expanded in alias_keys:
            return _build_title_result(
                raw=cleaned,
                canonical=canonical,
                status=NormalizationStatus.ALIAS,
                confidence=0.95,
                matched_by="alias",
            )

    smart_title = _smart_title(expanded)
    seniority_hint = _infer_seniority(expanded)
    functional_hint = infer_functional_role_family(job_title=expanded, raw_job_text=expanded)
    org_mode_hint = infer_organizational_role_mode(job_title=expanded, raw_job_text=expanded)
    role_type_hint = compatibility_role_type_value(
        functional_role_family=functional_hint.value,
        organizational_role_mode=org_mode_hint.value,
    )
    role_family = _infer_role_family(functional_hint.value, org_mode_hint.value, smart_title)
    status = (
        NormalizationStatus.INFERRED
        if seniority_hint or functional_hint.value != "other" or org_mode_hint.value != "unknown"
        else NormalizationStatus.PASSTHROUGH
    )
    confidence = 0.72 if status == NormalizationStatus.INFERRED else 0.35

    return TitleNormalization(
        raw=cleaned,
        canonical=smart_title,
        taxonomy="title",
        status=status,
        confidence=confidence,
        matched_by="inference" if status == NormalizationStatus.INFERRED else "passthrough",
        role_family=role_family,
        seniority_hint=seniority_hint,
        functional_role_family_hint=functional_hint.value,
        organizational_role_mode_hint=org_mode_hint.value,
        role_type_hint=role_type_hint,
    )


def normalize_skill_list(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate a list of skills while preserving order."""

    return _normalize_term_list(values, normalize_skill)


def normalize_tool_list(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate a list of tools while preserving order."""

    return _normalize_term_list(values, normalize_tool)


def normalize_tool_platform_list(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate tool/platform terms while preserving order."""

    return _normalize_term_list(values, normalize_tool_platform)


def normalize_cloud_services(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate cloud-service terms while preserving order."""

    return _normalize_term_list(values, normalize_cloud_service)


def normalize_frameworks(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate framework/library terms while preserving order."""

    return _normalize_term_list(values, normalize_framework)


def normalize_programming_languages(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate programming-language terms while preserving order."""

    return _normalize_term_list(values, normalize_programming_language)


def normalize_domains(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate a list of domains while preserving order."""

    return _normalize_term_list(values, normalize_domain)


def normalize_action_verbs(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate a list of action verbs while preserving order."""

    return _normalize_term_list(values, normalize_action_verb)


def normalize_leadership_phrases(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate leadership-phrase terms while preserving order."""

    return _normalize_term_list(values, normalize_leadership_phrase)


def normalize_ownership_phrases(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate ownership-phrase terms while preserving order."""

    return _normalize_term_list(values, normalize_ownership_phrase)


def normalize_delivery_scope_phrases(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate delivery-scope phrase terms while preserving order."""

    return _normalize_term_list(values, normalize_delivery_scope_phrase)


def normalize_stakeholder_phrases(values: list[str]) -> list[NormalizedTerm]:
    """Normalize and deduplicate stakeholder-phrase terms while preserving order."""

    return _normalize_term_list(values, normalize_stakeholder_phrase)


def infer_domains_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical domain labels from free-text inputs using domain aliases."""

    return infer_terms_from_text(values, taxonomy_name="domain", config_name="domains")


def infer_tool_platforms_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical tool/platform tags from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="tool_platform", config_name="tool_platforms")


def infer_cloud_services_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical cloud-service tags from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="cloud_service", config_name="cloud_services")


def infer_frameworks_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical framework/library tags from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="framework", config_name="frameworks")


def infer_programming_languages_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical programming-language tags from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="programming_language", config_name="programming_languages")


def infer_action_verbs_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical action/impact verbs from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="action_verb", config_name="action_verbs")


def infer_leadership_phrases_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical leadership phrases from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="leadership_phrase", config_name="leadership_phrases")


def infer_ownership_phrases_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical ownership phrases from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="ownership_phrase", config_name="ownership_phrases")


def infer_delivery_scope_phrases_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical delivery-scope phrases from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="delivery_scope_phrase", config_name="delivery_scope_phrases")


def infer_stakeholder_phrases_from_text(values: list[str]) -> list[NormalizedTerm]:
    """Infer canonical stakeholder/cross-functional phrases from free-text inputs."""

    return infer_terms_from_text(values, taxonomy_name="stakeholder_phrase", config_name="stakeholder_phrases")


def normalize_evidence_text(
    raw_text: str,
    *,
    title: str | None = None,
) -> EvidenceNormalizationBundle:
    """Return a deterministic normalization bundle for one raw evidence text."""

    cleaned = _normalize_text(raw_text)
    if not cleaned:
        raise ValueError("evidence text must not be empty")

    return EvidenceNormalizationBundle(
        raw_text=cleaned,
        tool_platforms=infer_tool_platforms_from_text([cleaned]),
        cloud_services=infer_cloud_services_from_text([cleaned]),
        frameworks_libraries=infer_frameworks_from_text([cleaned]),
        programming_languages=infer_programming_languages_from_text([cleaned]),
        domains_industries=infer_domains_from_text([cleaned]),
        action_verbs=infer_action_verbs_from_text([cleaned]),
        leadership_phrases=infer_leadership_phrases_from_text([cleaned]),
        ownership_phrases=infer_ownership_phrases_from_text([cleaned]),
        delivery_scope_phrases=infer_delivery_scope_phrases_from_text([cleaned]),
        stakeholder_phrases=infer_stakeholder_phrases_from_text([cleaned]),
        title=normalize_title_taxonomy(title) if title and _normalize_text(title) else None,
    )


def infer_terms_from_text(
    values: list[str],
    *,
    taxonomy_name: str,
    config_name: str,
) -> list[NormalizedTerm]:
    """Infer all matching canonical terms from free text using exact alias phrase matching."""

    config = load_taxonomy(config_name)
    token_streams = [_tokenize(value) for value in values if _normalize_text(value)]
    matches: list[NormalizedTerm] = []

    for canonical, aliases in config.canonical_terms.items():
        all_aliases = [canonical, *aliases]
        for alias in all_aliases:
            alias_tokens = _tokenize(alias)
            if not alias_tokens:
                continue
            if any(_token_sequence_present(alias_tokens, tokens) for tokens in token_streams):
                matches.append(
                    NormalizedTerm(
                        raw=alias,
                        canonical=canonical,
                        taxonomy=taxonomy_name,
                        status=NormalizationStatus.INFERRED,
                        confidence=0.7 if len(alias_tokens) == 1 else 0.78,
                        matched_by="text_inference",
                    )
                )
                break
    return _dedupe_results(matches)


def _normalize_with_taxonomy(
    value: str,
    *,
    taxonomy_name: str,
    config_name: str,
) -> NormalizedTerm:
    cleaned = _normalize_text(value)
    if not cleaned:
        raise ValueError(f"{taxonomy_name} term must not be empty")

    config = load_taxonomy(config_name)
    folded = _fold_key(cleaned)

    for canonical, aliases in config.canonical_terms.items():
        canonical_key = _fold_key(canonical)
        alias_keys = {_fold_key(alias) for alias in aliases}
        if folded == canonical_key:
            return NormalizedTerm(
                raw=cleaned,
                canonical=canonical,
                taxonomy=taxonomy_name,
                status=NormalizationStatus.EXACT,
                confidence=1.0,
                matched_by="canonical",
            )
        if folded in alias_keys:
            return NormalizedTerm(
                raw=cleaned,
                canonical=canonical,
                taxonomy=taxonomy_name,
                status=NormalizationStatus.ALIAS,
                confidence=0.95,
                matched_by="alias",
            )

    return NormalizedTerm(
        raw=cleaned,
        canonical=_smart_title(cleaned),
        taxonomy=taxonomy_name,
        status=NormalizationStatus.PASSTHROUGH,
        confidence=0.3,
        matched_by="passthrough",
    )


def _normalize_term_list(
    values: list[str],
    normalizer: callable,
) -> list[NormalizedTerm]:
    results: list[NormalizedTerm] = []
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = _normalize_text(value)
        if not cleaned:
            continue
        results.append(normalizer(cleaned))
    return _dedupe_results(results)


def _dedupe_results(values: list[NormalizedTerm]) -> list[NormalizedTerm]:
    deduped: list[NormalizedTerm] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        key = (value.taxonomy, _fold_key(value.canonical))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _build_title_result(
    *,
    raw: str,
    canonical: str,
    status: NormalizationStatus,
    confidence: float,
    matched_by: str,
) -> TitleNormalization:
    functional_hint = infer_functional_role_family(job_title=canonical, raw_job_text=canonical)
    org_mode_hint = infer_organizational_role_mode(job_title=canonical, raw_job_text=canonical)
    return TitleNormalization(
        raw=raw,
        canonical=canonical,
        taxonomy="title",
        status=status,
        confidence=confidence,
        matched_by=matched_by,
        role_family=_infer_role_family(functional_hint.value, org_mode_hint.value, canonical),
        seniority_hint=_infer_seniority(canonical),
        functional_role_family_hint=functional_hint.value,
        organizational_role_mode_hint=org_mode_hint.value,
        role_type_hint=compatibility_role_type_value(
            functional_role_family=functional_hint.value,
            organizational_role_mode=org_mode_hint.value,
        ),
    )


def _infer_seniority(value: str) -> str | None:
    tokens = set(_tokenize(value))
    for canonical, aliases in load_taxonomy("seniority").canonical_terms.items():
        all_values = [canonical, *aliases]
        alias_tokens = {_fold_key(alias) for alias in all_values}
        if any(alias in _fold_key(value) for alias in alias_tokens):
            return canonical
    if "lead" in tokens:
        return "lead"
    return None


def _infer_role_type(value: str) -> str | None:
    functional_hint = infer_functional_role_family(job_title=value, raw_job_text=value)
    org_mode_hint = infer_organizational_role_mode(job_title=value, raw_job_text=value)
    compatibility = compatibility_role_type_value(
        functional_role_family=functional_hint.value,
        organizational_role_mode=org_mode_hint.value,
    )
    return compatibility or None


def _infer_role_family(
    functional_role_family_hint: str | None,
    organizational_role_mode_hint: str | None,
    canonical_title: str,
) -> str | None:
    taxonomy = load_title_taxonomy()
    if canonical_title in taxonomy.role_family_hints:
        return taxonomy.role_family_hints[canonical_title]
    if functional_role_family_hint in {
        "frontend",
        "backend",
        "fullstack",
        "devops",
        "platform",
        "security",
        "data",
        "analytics",
        "ml",
        "mobile",
        "qa",
        "support",
    }:
        return "engineering"
    if organizational_role_mode_hint in {"people_manager", "director_or_head"}:
        return "management"
    if functional_role_family_hint in {"product", "design"}:
        return functional_role_family_hint
    return None


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _fold_key(value: str) -> str:
    return " ".join(_tokenize(value))


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())


def _token_sequence_present(needle: list[str], haystack: list[str]) -> bool:
    if not needle or not haystack or len(needle) > len(haystack):
        return False

    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            return True
    return False


def _smart_title(value: str) -> str:
    words = re.split(r"(\s+|/|-)", value)
    normalized: list[str] = []

    for token in words:
        if token.isspace() or token in {"/", "-"}:
            normalized.append(token)
            continue
        if not token:
            continue
        if token in _PRESERVE_MIXED:
            normalized.append(token)
            continue
        upper_token = token.upper()
        if upper_token in _PRESERVE_UPPER:
            normalized.append(upper_token)
            continue
        normalized.append(token.capitalize())

    return "".join(normalized)
