"""Deterministic role-axis modeling for Phase 1 job understanding.

This module separates the technical/functional role family from the
organizational role mode so downstream phases do not need to infer semantics
from an overloaded `role_type` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from pydantic import Field

from .models import NonEmptyStr, ScoreValue, StrictModel

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class FunctionalRoleFamily(StrEnum):
    """Primary technical or business discipline the job belongs to."""

    FRONTEND = "frontend"
    BACKEND = "backend"
    FULLSTACK = "fullstack"
    DEVOPS = "devops"
    PLATFORM = "platform"
    SECURITY = "security"
    DATA = "data"
    ANALYTICS = "analytics"
    ML = "ml"
    MOBILE = "mobile"
    PRODUCT = "product"
    DESIGN = "design"
    QA = "qa"
    SUPPORT = "support"
    OTHER = "other"


class OrganizationalRoleMode(StrEnum):
    """How the role operates in the organization independent of function."""

    INDIVIDUAL_CONTRIBUTOR = "individual_contributor"
    SENIOR_INDIVIDUAL_CONTRIBUTOR = "senior_individual_contributor"
    TECH_LEAD = "tech_lead"
    PEOPLE_MANAGER = "people_manager"
    DIRECTOR_OR_HEAD = "director_or_head"
    FOUNDER_OR_GENERALIST = "founder_or_generalist"
    CONSULTANT = "consultant"
    RESEARCHER = "researcher"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RoleInferenceRule:
    """One deterministic rule used for role-axis inference.

    The rule design is intentionally explicit so product code can add or
    override signals later without rewriting the core inference algorithm.
    """

    canonical: str
    positive_phrases: tuple[str, ...]
    title_weight: int
    text_weight: int
    required_phrases: tuple[str, ...] = ()
    negative_phrases: tuple[str, ...] = ()


class RoleAxisInferenceResult(StrictModel):
    """Inference result for one role axis plus debugging metadata."""

    value: NonEmptyStr
    confidence: ScoreValue
    matched_title_signals: list[NonEmptyStr] = Field(default_factory=list)
    matched_text_signals: list[NonEmptyStr] = Field(default_factory=list)
    notes: list[NonEmptyStr] = Field(default_factory=list)


class InferredRoleAxes(StrictModel):
    """Independent functional and organizational interpretations of a JD."""

    functional_role_family: FunctionalRoleFamily
    organizational_role_mode: OrganizationalRoleMode
    family_inference: RoleAxisInferenceResult
    organizational_inference: RoleAxisInferenceResult


_FUNCTIONAL_ROLE_RULES: tuple[RoleInferenceRule, ...] = (
    RoleInferenceRule("frontend", ("frontend", "front-end", "front end", "ui engineer", "react", "web ui"), 4, 2),
    RoleInferenceRule("backend", ("backend", "back-end", "back end", "api", "server-side", "microservices"), 4, 2),
    RoleInferenceRule("fullstack", ("fullstack", "full-stack", "full stack"), 5, 2),
    RoleInferenceRule("devops", ("devops", "site reliability", "sre", "ci/cd", "infrastructure automation"), 4, 2),
    RoleInferenceRule("platform", ("platform", "developer infrastructure", "internal tooling", "infrastructure platform"), 5, 3),
    RoleInferenceRule("security", ("security", "application security", "cybersecurity", "security engineering"), 5, 2),
    RoleInferenceRule("data", ("data engineer", "data engineering", "data platform", "etl", "warehousing"), 5, 2),
    RoleInferenceRule("analytics", ("analytics", "business intelligence", "bi", "reporting", "insights"), 4, 2),
    RoleInferenceRule("ml", ("machine learning", "ml", "ai engineer", "ml engineer", "data scientist"), 5, 2),
    RoleInferenceRule("mobile", ("mobile", "ios", "android", "react native", "swift", "kotlin"), 5, 2),
    RoleInferenceRule("product", ("product manager", "product management", "roadmap", "product strategy"), 5, 2),
    RoleInferenceRule("design", ("designer", "design", "ux", "ui/ux", "product design"), 4, 2),
    RoleInferenceRule("qa", ("qa", "quality assurance", "test automation", "sdet"), 5, 2),
    RoleInferenceRule("support", ("support engineer", "technical support", "customer support", "support"), 5, 2),
)

_ORG_ROLE_MODE_RULES: tuple[RoleInferenceRule, ...] = (
    RoleInferenceRule("director_or_head", ("director", "head of", "vp", "vice president"), 6, 2),
    RoleInferenceRule(
        "people_manager",
        ("engineering manager", "people manager", "manage a team", "manage engineers", "direct reports"),
        5,
        3,
    ),
    RoleInferenceRule(
        "tech_lead",
        ("tech lead", "technical lead", "lead", "lead engineer", "staff engineer leading", "mentor engineers", "mentoring"),
        5,
        3,
    ),
    RoleInferenceRule("founder_or_generalist", ("founding", "founder", "early-stage", "startup generalist"), 6, 2),
    RoleInferenceRule("consultant", ("consultant", "consulting", "client engagements"), 5, 2),
    RoleInferenceRule("researcher", ("research scientist", "research engineer", "researcher"), 5, 2),
    RoleInferenceRule("senior_individual_contributor", ("senior", "staff", "principal", "senior engineer", "staff engineer", "principal engineer"), 4, 1),
    RoleInferenceRule("individual_contributor", ("engineer", "developer", "individual contributor", "product manager", "designer", "data scientist"), 2, 1),
)

_FAMILY_ENUM_BY_VALUE = {item.value: item for item in FunctionalRoleFamily}
_MODE_ENUM_BY_VALUE = {item.value: item for item in OrganizationalRoleMode}


def infer_role_axes(
    *,
    job_title: str | None,
    raw_job_text: str,
    additional_family_rules: tuple[RoleInferenceRule, ...] = (),
    additional_org_mode_rules: tuple[RoleInferenceRule, ...] = (),
) -> InferredRoleAxes:
    """Infer functional family and organizational role mode independently.

    The algorithm uses weighted phrase matches from both title and JD body.
    Title hits are weighted more heavily than general body matches, and ties
    fall back to deterministic precedence order rather than arbitrary string
    ordering.
    """

    title = job_title or ""
    family_result = _infer_axis(
        title=title,
        text=raw_job_text,
        rules=(*additional_family_rules, *_FUNCTIONAL_ROLE_RULES),
        fallback="other",
    )
    org_result = _infer_axis(
        title=title,
        text=raw_job_text,
        rules=(*additional_org_mode_rules, *_ORG_ROLE_MODE_RULES),
        fallback="unknown",
    )

    return InferredRoleAxes(
        functional_role_family=_FAMILY_ENUM_BY_VALUE[family_result.value],
        organizational_role_mode=_MODE_ENUM_BY_VALUE[org_result.value],
        family_inference=family_result,
        organizational_inference=org_result,
    )


def infer_functional_role_family(
    *,
    job_title: str | None,
    raw_job_text: str,
    additional_rules: tuple[RoleInferenceRule, ...] = (),
) -> RoleAxisInferenceResult:
    """Infer only the functional role family from title plus JD body."""

    return _infer_axis(
        title=job_title or "",
        text=raw_job_text,
        rules=(*additional_rules, *_FUNCTIONAL_ROLE_RULES),
        fallback="other",
    )


def infer_organizational_role_mode(
    *,
    job_title: str | None,
    raw_job_text: str,
    additional_rules: tuple[RoleInferenceRule, ...] = (),
) -> RoleAxisInferenceResult:
    """Infer only the organizational role mode from title plus JD body."""

    return _infer_axis(
        title=job_title or "",
        text=raw_job_text,
        rules=(*additional_rules, *_ORG_ROLE_MODE_RULES),
        fallback="unknown",
    )


def compatibility_role_type_value(
    *,
    functional_role_family: FunctionalRoleFamily | str,
    organizational_role_mode: OrganizationalRoleMode | str,
) -> str:
    """Return the best legacy `role_type`-style comparable value.

    Old code paths still expect a single ambiguous string. This function keeps
    them alive while new Phase 1 code uses both independent axes.
    """

    if isinstance(functional_role_family, str):
        functional_role_family = _FAMILY_ENUM_BY_VALUE.get(
            functional_role_family, FunctionalRoleFamily.OTHER
        )
    if isinstance(organizational_role_mode, str):
        organizational_role_mode = _MODE_ENUM_BY_VALUE.get(
            organizational_role_mode, OrganizationalRoleMode.UNKNOWN
        )

    if organizational_role_mode in {
        OrganizationalRoleMode.PEOPLE_MANAGER,
        OrganizationalRoleMode.DIRECTOR_OR_HEAD,
    }:
        return "management"
    if organizational_role_mode == OrganizationalRoleMode.TECH_LEAD:
        return "leadership"
    if organizational_role_mode == OrganizationalRoleMode.FOUNDER_OR_GENERALIST:
        return "founder"
    if organizational_role_mode == OrganizationalRoleMode.CONSULTANT:
        return "consultant"
    if organizational_role_mode == OrganizationalRoleMode.RESEARCHER:
        return "researcher"
    if functional_role_family != FunctionalRoleFamily.OTHER:
        return functional_role_family.value
    if organizational_role_mode in {
        OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
        OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
    }:
        return "individual_contributor"
    return "individual_contributor"


def _infer_axis(
    *,
    title: str,
    text: str,
    rules: tuple[RoleInferenceRule, ...],
    fallback: str,
) -> RoleAxisInferenceResult:
    title_tokens = _tokenize(title)
    text_tokens = _tokenize(text)
    best_rule: RoleInferenceRule | None = None
    best_score = 0
    best_title_hits: list[str] = []
    best_text_hits: list[str] = []

    for rule in rules:
        title_hits = _matching_phrases(rule.positive_phrases, title_tokens)
        text_hits = _matching_phrases(rule.positive_phrases, text_tokens)
        if rule.required_phrases and not _all_required_present(rule.required_phrases, title_tokens, text_tokens):
            continue
        if _matching_phrases(rule.negative_phrases, title_tokens) or _matching_phrases(rule.negative_phrases, text_tokens):
            continue
        score = len(title_hits) * rule.title_weight + len(text_hits) * rule.text_weight
        if score > best_score:
            best_rule = rule
            best_score = score
            best_title_hits = title_hits
            best_text_hits = text_hits

    if best_rule is None or best_score == 0:
        return RoleAxisInferenceResult(
            value=fallback,
            confidence=0.35,
            notes=["No strong deterministic signals were found for this axis."],
        )

    confidence = min(0.99, 0.45 + min(best_score, 10) * 0.05)
    notes: list[str] = []
    if best_title_hits:
        notes.append("Title signals dominated the inferred classification.")
    elif len(best_text_hits) > 1:
        notes.append("Multiple JD body signals supported the inferred classification.")

    return RoleAxisInferenceResult(
        value=best_rule.canonical,
        confidence=confidence,
        matched_title_signals=best_title_hits,
        matched_text_signals=best_text_hits,
        notes=notes,
    )


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())


def _matching_phrases(phrases: tuple[str, ...], tokens: list[str]) -> list[str]:
    matches: list[str] = []
    for phrase in phrases:
        phrase_tokens = _tokenize(phrase)
        if _token_sequence_present(phrase_tokens, tokens):
            matches.append(phrase)
    return matches


def _all_required_present(
    phrases: tuple[str, ...], title_tokens: list[str], text_tokens: list[str]
) -> bool:
    for phrase in phrases:
        phrase_tokens = _tokenize(phrase)
        if _token_sequence_present(phrase_tokens, title_tokens):
            continue
        if _token_sequence_present(phrase_tokens, text_tokens):
            continue
        return False
    return True


def _token_sequence_present(needle: list[str], haystack: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            return True
    return False
    if isinstance(functional_role_family, str):
        functional_role_family = _FAMILY_ENUM_BY_VALUE.get(
            functional_role_family, FunctionalRoleFamily.OTHER
        )
    if isinstance(organizational_role_mode, str):
        organizational_role_mode = _MODE_ENUM_BY_VALUE.get(
            organizational_role_mode, OrganizationalRoleMode.UNKNOWN
        )
