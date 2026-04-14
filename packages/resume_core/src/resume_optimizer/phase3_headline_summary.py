"""Headline and summary guidance for Phase 3 structured generation.

These fields are high-value but also high-risk. This module keeps their prompting
and lightweight safety checks separate from bullet rewriting so later phases can
extend them without tangling the broader generator flow.
"""

from __future__ import annotations

import re
from collections import Counter
from enum import StrEnum

from pydantic import Field

from .models import NonEmptyStr, ScoreValue, StrictModel
from .phase3_models import Phase3GenerationPayload, Phase3GenerationResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+#/%-]*")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_TOOL_TERMS = {
    "aws",
    "azure",
    "docker",
    "gcp",
    "github",
    "graphql",
    "java",
    "javascript",
    "kafka",
    "kubernetes",
    "mysql",
    "node",
    "node.js",
    "postgres",
    "postgresql",
    "python",
    "react",
    "redis",
    "terraform",
    "typescript",
}
_GENERIC_FLAIR_PHRASES = {
    "results-driven",
    "dynamic professional",
    "passionate professional",
    "proven track record",
    "strategic thinker",
    "world-class",
}
_EXPERTISE_TERMS = {
    "authority",
    "expert",
    "expertise",
    "mastery",
    "specialist",
}
_LEADERSHIP_TERMS = {
    "director",
    "head",
    "lead",
    "leader",
    "leadership",
    "managed",
    "manager",
    "mentored",
    "owned",
    "ownership",
    "spearheaded",
    "vp",
}
_INDUSTRY_DEPTH_TERMS = {
    "deep",
    "depth",
    "specialized",
    "specialist",
}
_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "the",
    "to",
    "with",
}
_SENIORITY_ORDER = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "staff": 4,
    "principal": 5,
    "lead": 5,
    "manager": 6,
    "director": 7,
    "executive": 8,
    "vp": 8,
}


class HeadlineSummaryField(StrEnum):
    """Supported generated profile-copy fields."""

    HEADLINE = "headline"
    SUMMARY = "summary"


class HeadlineSummaryIssueType(StrEnum):
    """Stable issue taxonomy for later verification and analytics."""

    FILLER_LANGUAGE = "filler_language"
    INSERTED_METRIC = "inserted_metric"
    UNSUPPORTED_TOOL = "unsupported_tool"
    SENIORITY_INFLATION = "seniority_inflation"
    LEADERSHIP_INFLATION = "leadership_inflation"
    UNSUPPORTED_EXPERTISE = "unsupported_expertise"
    DOMAIN_DEPTH_INFLATION = "domain_depth_inflation"
    KEYWORD_STUFFING = "keyword_stuffing"
    OVERLONG = "overlong"
    WEAK_ALIGNMENT = "weak_alignment"


class HeadlineSummaryIssueSeverity(StrEnum):
    """Relative severity for headline/summary issues."""

    WARNING = "warning"
    ERROR = "error"


class HeadlineSummaryLengthGuidance(StrictModel):
    """Configurable length guidance for headline and summary generation."""

    headline_max_words: int = Field(default=12, ge=3, le=24)
    summary_max_sentences: int = Field(default=3, ge=1, le=5)
    summary_max_words: int = Field(default=60, ge=20, le=120)


class HeadlineSummaryIssue(StrictModel):
    """One detected issue in generated headline or summary copy."""

    issue_type: HeadlineSummaryIssueType
    severity: HeadlineSummaryIssueSeverity
    message: NonEmptyStr
    matched_terms: list[NonEmptyStr] = Field(default_factory=list)


class HeadlineSummaryAssessment(StrictModel):
    """Compact assessment of generated headline or summary quality/safety."""

    field_name: HeadlineSummaryField
    text: NonEmptyStr
    quality_score: ScoreValue
    hard_fail: bool = False
    issues: list[HeadlineSummaryIssue] = Field(default_factory=list)


def build_headline_summary_prompt_lines(
    payload: Phase3GenerationPayload,
) -> list[str]:
    """Build focused prompt lines for headline and summary generation only."""

    guidance = resolve_headline_summary_length_guidance(payload)
    target_title = payload.role_context.target_role_title or payload.headline_hint
    summary_themes = ", ".join(hint.theme for hint in payload.summary_hints[:3]) or "none"
    must_have_skills = ", ".join(payload.role_context.must_have_skills[:5]) or "none"
    preferred_skills = ", ".join(payload.role_context.preferred_skills[:5]) or "none"

    lines = [
        "Headline and summary rules:",
        "- Generate a believable headline aligned to the target role or role family without inflating seniority.",
        "- Generate a concise professional summary grounded entirely in the provided evidence.",
        "- Emphasize the most relevant supported themes for the target role.",
        "- Avoid filler phrases, generic corporate language, awkward title stacking, and keyword stuffing.",
        "- Do not claim unsupported years, scale, leadership, domain depth, tools, or expertise.",
        f"- Keep the headline to at most {guidance.headline_max_words} words.",
        (
            f"- Keep the summary to at most {guidance.summary_max_sentences} sentences "
            f"and about {guidance.summary_max_words} words."
        ),
        f"- Preferred role title hint: {target_title or 'none'}.",
        f"- Must-have skill emphasis: {must_have_skills}.",
        f"- Preferred skill emphasis: {preferred_skills}.",
        f"- Summary theme hints: {summary_themes}.",
    ]
    return lines


def resolve_headline_summary_length_guidance(
    payload: Phase3GenerationPayload,
) -> HeadlineSummaryLengthGuidance:
    """Resolve headline/summary length settings from the assembled payload."""

    constraints = payload.length_constraints
    summary_max_sentences = constraints.summary_max_sentences if constraints else None
    headline_max_words = constraints.headline_max_words if constraints else None
    return HeadlineSummaryLengthGuidance(
        headline_max_words=headline_max_words or 12,
        summary_max_sentences=summary_max_sentences or 3,
        summary_max_words=max(30, (summary_max_sentences or 3) * 20),
    )


def assess_headline(
    payload: Phase3GenerationPayload,
    text: str,
) -> HeadlineSummaryAssessment:
    """Assess a generated headline for inflation, alignment, and fluff."""

    guidance = resolve_headline_summary_length_guidance(payload)
    source_context = _build_source_context(payload)
    tokens = _tokenize(text)
    issues: list[HeadlineSummaryIssue] = []

    issues.extend(_detect_filler_language(text))
    issues.extend(_detect_inserted_numbers(source_context["source_text"], text))
    issues.extend(_detect_unsupported_tools(source_context["supported_tools"], text))
    issues.extend(
        _detect_seniority_or_leadership_inflation(
            source_context["max_supported_seniority"],
            source_context["leadership_supported"],
            text,
        )
    )
    issues.extend(_detect_keyword_stuffing(tokens))
    issues.extend(
        _detect_overlong(
            field_name=HeadlineSummaryField.HEADLINE,
            word_count=len(tokens),
            max_words=guidance.headline_max_words,
        )
    )
    issues.extend(_detect_headline_alignment(payload, text))

    return HeadlineSummaryAssessment(
        field_name=HeadlineSummaryField.HEADLINE,
        text=text.strip(),
        quality_score=_score_headline_summary(issues),
        hard_fail=any(issue.severity == HeadlineSummaryIssueSeverity.ERROR for issue in issues),
        issues=issues,
    )


def assess_summary(
    payload: Phase3GenerationPayload,
    text: str,
) -> HeadlineSummaryAssessment:
    """Assess a generated summary for unsupported claims and generic phrasing."""

    guidance = resolve_headline_summary_length_guidance(payload)
    source_context = _build_source_context(payload)
    tokens = _tokenize(text)
    issues: list[HeadlineSummaryIssue] = []

    issues.extend(_detect_filler_language(text))
    issues.extend(_detect_inserted_numbers(source_context["source_text"], text))
    issues.extend(_detect_unsupported_tools(source_context["supported_tools"], text))
    issues.extend(
        _detect_seniority_or_leadership_inflation(
            source_context["max_supported_seniority"],
            source_context["leadership_supported"],
            text,
        )
    )
    issues.extend(_detect_unsupported_expertise(source_context["source_tokens"], text))
    issues.extend(_detect_domain_depth_inflation(payload, source_context["source_tokens"], text))
    issues.extend(_detect_keyword_stuffing(tokens))
    issues.extend(
        _detect_overlong(
            field_name=HeadlineSummaryField.SUMMARY,
            word_count=len(tokens),
            max_words=guidance.summary_max_words,
        )
    )

    sentence_count = len([part for part in re.split(r"[.!?]+", text) if part.strip()])
    if sentence_count > guidance.summary_max_sentences:
        issues.append(
            HeadlineSummaryIssue(
                issue_type=HeadlineSummaryIssueType.OVERLONG,
                severity=HeadlineSummaryIssueSeverity.WARNING,
                message="Summary exceeds the configured sentence guidance.",
            )
        )

    return HeadlineSummaryAssessment(
        field_name=HeadlineSummaryField.SUMMARY,
        text=text.strip(),
        quality_score=_score_headline_summary(issues),
        hard_fail=any(issue.severity == HeadlineSummaryIssueSeverity.ERROR for issue in issues),
        issues=issues,
    )


def validate_headline_and_summary(
    payload: Phase3GenerationPayload,
    result: Phase3GenerationResult,
) -> list[HeadlineSummaryAssessment]:
    """Assess generated headline and summary fields and return their evaluations."""

    assessments: list[HeadlineSummaryAssessment] = []
    if result.headline is not None:
        assessments.append(assess_headline(payload, result.headline.text))
    if result.summary is not None:
        assessments.append(assess_summary(payload, result.summary.text))
    return assessments


def _build_source_context(payload: Phase3GenerationPayload) -> dict[str, object]:
    source_text_fragments = [
        bullet.text
        for section in [*payload.selected_experiences, *payload.selected_projects]
        for bullet in section.bullets
    ]
    source_titles = [entry.title for entry in payload.selected_experiences]
    source_titles.extend(
        project.role or project.name for project in payload.selected_projects
    )
    source_tools = {
        tool.casefold()
        for tool in (
            [tool for section in payload.selected_experiences for tool in section.tools]
            + [tool for section in payload.selected_projects for tool in section.tools]
            + [skill.skill_name for skill in payload.matched_skills]
        )
    }
    source_text = " ".join([*source_titles, *source_text_fragments])
    source_tokens = set(_tokenize(source_text))

    max_supported_seniority = 0
    for value in [payload.role_context.target_seniority or "", *source_titles]:
        for token in _tokenize(value):
            max_supported_seniority = max(
                max_supported_seniority,
                _SENIORITY_ORDER.get(token, 0),
            )

    leadership_supported = any(
        token in source_tokens for token in _LEADERSHIP_TERMS
    )
    return {
        "source_text": source_text,
        "source_tokens": source_tokens,
        "supported_tools": source_tools,
        "max_supported_seniority": max_supported_seniority,
        "leadership_supported": leadership_supported,
    }


def _detect_filler_language(text: str) -> list[HeadlineSummaryIssue]:
    text_normalized = text.casefold()
    matched = sorted(phrase for phrase in _GENERIC_FLAIR_PHRASES if phrase in text_normalized)
    if not matched:
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.FILLER_LANGUAGE,
            severity=HeadlineSummaryIssueSeverity.WARNING,
            message="Generated copy uses filler or generic corporate language.",
            matched_terms=matched,
        )
    ]


def _detect_inserted_numbers(source_text: str, text: str) -> list[HeadlineSummaryIssue]:
    source_numbers = set(_NUMBER_PATTERN.findall(source_text))
    rewritten_numbers = set(_NUMBER_PATTERN.findall(text))
    inserted = sorted(rewritten_numbers - source_numbers)
    if not inserted:
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.INSERTED_METRIC,
            severity=HeadlineSummaryIssueSeverity.ERROR,
            message="Generated copy introduced unsupported numeric detail.",
            matched_terms=inserted,
        )
    ]


def _detect_unsupported_tools(
    supported_tools: set[str],
    text: str,
) -> list[HeadlineSummaryIssue]:
    text_normalized = text.casefold()
    inserted = sorted(
        tool for tool in _TOOL_TERMS if tool in text_normalized and tool not in supported_tools
    )
    if not inserted:
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.UNSUPPORTED_TOOL,
            severity=HeadlineSummaryIssueSeverity.ERROR,
            message="Generated copy introduced unsupported tools or technologies.",
            matched_terms=inserted,
        )
    ]


def _detect_seniority_or_leadership_inflation(
    max_supported_seniority: int,
    leadership_supported: bool,
    text: str,
) -> list[HeadlineSummaryIssue]:
    issues: list[HeadlineSummaryIssue] = []
    tokens = _tokenize(text)
    detected_seniority = max((_SENIORITY_ORDER.get(token, 0) for token in tokens), default=0)
    if detected_seniority > max_supported_seniority:
        issues.append(
            HeadlineSummaryIssue(
                issue_type=HeadlineSummaryIssueType.SENIORITY_INFLATION,
                severity=HeadlineSummaryIssueSeverity.ERROR,
                message="Generated copy appears to inflate seniority beyond supported evidence.",
            )
        )
    if not leadership_supported:
        inserted_leadership = sorted(token for token in _LEADERSHIP_TERMS if token in tokens)
        if inserted_leadership:
            issues.append(
                HeadlineSummaryIssue(
                    issue_type=HeadlineSummaryIssueType.LEADERSHIP_INFLATION,
                    severity=HeadlineSummaryIssueSeverity.ERROR,
                    message="Generated copy introduced unsupported leadership or ownership language.",
                    matched_terms=inserted_leadership,
                )
            )
    return issues


def _detect_unsupported_expertise(
    source_tokens: set[str],
    text: str,
) -> list[HeadlineSummaryIssue]:
    inserted = sorted(term for term in _EXPERTISE_TERMS if term in _tokenize(text) and term not in source_tokens)
    if not inserted:
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.UNSUPPORTED_EXPERTISE,
            severity=HeadlineSummaryIssueSeverity.ERROR,
            message="Generated copy claims expertise that is not explicitly supported.",
            matched_terms=inserted,
        )
    ]


def _detect_domain_depth_inflation(
    payload: Phase3GenerationPayload,
    source_tokens: set[str],
    text: str,
) -> list[HeadlineSummaryIssue]:
    role_domain_tokens = set(_tokenize(payload.role_context.target_industry_domain or ""))
    text_tokens = set(_tokenize(text))
    matched_depth_terms = sorted(term for term in _INDUSTRY_DEPTH_TERMS if term in text_tokens)
    if not matched_depth_terms:
        return []
    if role_domain_tokens and role_domain_tokens.issubset(source_tokens):
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.DOMAIN_DEPTH_INFLATION,
            severity=HeadlineSummaryIssueSeverity.ERROR,
            message="Generated summary claims domain depth not supported by the selected evidence.",
            matched_terms=matched_depth_terms,
        )
    ]


def _detect_keyword_stuffing(tokens: list[str]) -> list[HeadlineSummaryIssue]:
    counts = Counter(token for token in tokens if len(token) > 2 and token not in _STOPWORDS)
    repeated = sorted(token for token, count in counts.items() if count > 2)
    if not repeated:
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.KEYWORD_STUFFING,
            severity=HeadlineSummaryIssueSeverity.WARNING,
            message="Generated copy repeats the same keywords too often.",
            matched_terms=repeated,
        )
    ]


def _detect_overlong(
    *,
    field_name: HeadlineSummaryField,
    word_count: int,
    max_words: int,
) -> list[HeadlineSummaryIssue]:
    if word_count <= max_words:
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.OVERLONG,
            severity=(
                HeadlineSummaryIssueSeverity.ERROR
                if field_name == HeadlineSummaryField.HEADLINE
                else HeadlineSummaryIssueSeverity.WARNING
            ),
            message=f"{field_name.value.title()} is longer than the configured guidance.",
        )
    ]


def _detect_headline_alignment(
    payload: Phase3GenerationPayload,
    text: str,
) -> list[HeadlineSummaryIssue]:
    reference_tokens = set(
        _tokenize(payload.role_context.target_role_title or payload.headline_hint or "")
    ) | set(_tokenize(payload.role_context.target_role_type or ""))
    if not reference_tokens:
        return []

    text_tokens = set(_tokenize(text))
    if reference_tokens.intersection(text_tokens):
        return []
    return [
        HeadlineSummaryIssue(
            issue_type=HeadlineSummaryIssueType.WEAK_ALIGNMENT,
            severity=HeadlineSummaryIssueSeverity.WARNING,
            message="Headline does not appear to align closely with the target role context.",
        )
    ]


def _score_headline_summary(issues: list[HeadlineSummaryIssue]) -> float:
    score = 1.0
    for issue in issues:
        score -= 0.25 if issue.severity == HeadlineSummaryIssueSeverity.ERROR else 0.1
    return max(0.0, min(1.0, round(score, 4)))


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())
