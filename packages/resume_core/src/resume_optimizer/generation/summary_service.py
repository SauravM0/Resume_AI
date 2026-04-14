"""Dedicated bounded summary generator for Phase 5."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from json import JSONDecodeError
import re
from typing import TYPE_CHECKING, Any

from pydantic import Field, ValidationError, model_validator

from ..config import DEFAULT_SETTINGS, Settings
from ..models import NonEmptyStr, ScoreValue, StableId, StrictModel
from ..openai_client import build_openai_client, create_json_response_text
from ..phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from ..prompt_loader import load_phase5_summary_generation_prompt
from .contracts import (
    GenerationQualitySignals,
    GenerationStyleMode,
    PolicyReasonCode,
    PolicySignalSeverity,
    QualitySignal,
    QualitySignalSeverity,
    SummaryGenerationInput,
    SummaryGenerationOutput,
)
from .role_style_policy import resolve_role_style_policy
from .quality_validator import merge_quality_signals, validate_summary_quality
from .rewrite_policy import RewritePolicyContext, RewritePolicyTarget, evaluate_rewrite_policy

if TYPE_CHECKING:
    from google.genai.client import Client as GeminiClient

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+#/%-]*")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_WEAK_PHRASES = {
    "results-driven",
    "dynamic professional",
    "passionate",
    "highly motivated",
    "proven track record",
    "cutting-edge",
}
_LEADERSHIP_TERMS = {
    "lead",
    "leader",
    "leadership",
    "managed",
    "manager",
    "mentored",
    "owned",
    "ownership",
    "headed",
    "directed",
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
_ROLE_LABELS = {
    FunctionalRoleFamily.BACKEND: "backend engineer",
    FunctionalRoleFamily.FRONTEND: "frontend engineer",
    FunctionalRoleFamily.FULLSTACK: "full-stack engineer",
    FunctionalRoleFamily.DATA: "data engineer",
    FunctionalRoleFamily.ANALYTICS: "analytics professional",
    FunctionalRoleFamily.ML: "machine learning engineer",
    FunctionalRoleFamily.PLATFORM: "platform engineer",
    FunctionalRoleFamily.DEVOPS: "devops engineer",
    FunctionalRoleFamily.SECURITY: "security engineer",
    FunctionalRoleFamily.MOBILE: "mobile engineer",
    FunctionalRoleFamily.PRODUCT: "product professional",
    FunctionalRoleFamily.DESIGN: "product designer",
    FunctionalRoleFamily.QA: "quality engineer",
    FunctionalRoleFamily.SUPPORT: "support engineer",
    FunctionalRoleFamily.OTHER: "engineer",
}


class SummaryGenerationError(RuntimeError):
    """Raised when bounded summary generation cannot complete safely."""


class MalformedSummaryGenerationResponseError(SummaryGenerationError):
    """Raised when the summary generator returns malformed JSON."""


class SummaryGenerationResponse(StrictModel):
    """Strict JSON response expected from the summary model."""

    summary_text: NonEmptyStr
    evidence_ids_used: list[StableId] = Field(default_factory=list)
    themes_used: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_minimal_shape(self) -> "SummaryGenerationResponse":
        if not self.evidence_ids_used:
            raise ValueError("evidence_ids_used must contain at least one bounded evidence id")
        return self


@dataclass(frozen=True, slots=True)
class SummarySignalBundle:
    """Deterministically extracted supported summary signals."""

    source_item_ids: list[str]
    source_bullet_ids: list[str]
    evidence_ids: list[str]
    supported_tools: list[str]
    supported_themes: list[str]
    supported_domain_phrases: list[str]
    leadership_supported: bool
    source_text: str


class SummaryGenerationService:
    """Generate short role-specific summaries from bounded structured inputs only."""

    def __init__(
        self,
        *,
        client: GeminiClient | None = None,
        model: str | None = None,
        settings: Settings = DEFAULT_SETTINGS,
        prompt_template: str | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._settings = settings
        self._prompt_template = prompt_template

    def generate(self, summary_input: SummaryGenerationInput) -> SummaryGenerationOutput:
        """Generate one bounded summary and attach deterministic QA signals."""

        bundle = self._build_signal_bundle(summary_input)
        precheck_signals = self._precheck(summary_input, bundle)
        prompt = self.build_prompt(summary_input, bundle)

        warnings = [signal.message for signal in precheck_signals.warnings]
        response: SummaryGenerationResponse | None = None
        try:
            response = self._run_generation(prompt)
            summary_text = response.summary_text
            evidence_ids_used = self._validated_evidence_ids(response.evidence_ids_used, bundle)
            themes_used = self._validated_themes(response.themes_used, bundle)
        except SummaryGenerationError as exc:
            warnings.append(str(exc))
            summary_text = self._build_fallback_summary(summary_input, bundle)
            evidence_ids_used = list(bundle.evidence_ids)
            themes_used = list(bundle.supported_themes[:2])

        postcheck_signals = self._postcheck(
            summary_input,
            bundle,
            summary_text,
            evidence_ids_used=evidence_ids_used,
            themes_used=themes_used,
        )
        final_warnings = warnings + [signal.message for signal in postcheck_signals.warnings]
        final_signal_warnings = [*precheck_signals.warnings, *postcheck_signals.warnings]
        final_signal_hard_failures = list(postcheck_signals.hard_failures)
        final_provenance_score = postcheck_signals.provenance_coverage_score
        final_style_score = postcheck_signals.style_alignment_score
        if postcheck_signals.hard_failures:
            final_warnings.append("summary output failed deterministic QA and was replaced with a bounded fallback")
            summary_text = self._build_fallback_summary(summary_input, bundle)
            evidence_ids_used = list(bundle.evidence_ids)
            themes_used = list(bundle.supported_themes[:2])
            fallback_signals = self._postcheck(
                summary_input,
                bundle,
                summary_text,
                evidence_ids_used=evidence_ids_used,
                themes_used=themes_used,
            )
            final_signal_warnings = [*final_signal_warnings, *fallback_signals.warnings]
            final_signal_hard_failures = [*final_signal_hard_failures, *fallback_signals.hard_failures]
            final_provenance_score = fallback_signals.provenance_coverage_score
            final_style_score = fallback_signals.style_alignment_score

        result = SummaryGenerationOutput(
            section_id=summary_input.section_id,
            summary_text=summary_text,
            source_item_ids=list(bundle.source_item_ids),
            source_bullet_ids=list(bundle.source_bullet_ids),
            evidence_ids_used=evidence_ids_used,
            themes_used=themes_used,
            warnings=final_warnings,
            quality_signals=GenerationQualitySignals(
                hard_failures=final_signal_hard_failures,
                warnings=final_signal_warnings,
                provenance_coverage_score=final_provenance_score,
                style_alignment_score=final_style_score,
            ),
            role_family=summary_input.parsed_job_output.functional_role_family,
            organizational_role_mode=summary_input.parsed_job_output.organizational_role_mode,
            style_mode=summary_input.style_policy.style_mode,
        )
        return result.model_copy(
            update={
                "quality_signals": merge_quality_signals(
                    result.quality_signals,
                    validate_summary_quality(result),
                )
            }
        )

    def build_prompt(
        self,
        summary_input: SummaryGenerationInput,
        bundle: SummarySignalBundle,
    ) -> str:
        """Build the dedicated summary prompt from only bounded supported signals."""

        role_style_policy = resolve_role_style_policy(
            role_family=summary_input.parsed_job_output.functional_role_family,
            organizational_role_mode=summary_input.parsed_job_output.organizational_role_mode,
        )
        payload = {
            "role_context": {
                "target_role_title": summary_input.parsed_job_output.target_role_title,
                "functional_role_family": summary_input.parsed_job_output.functional_role_family.value,
                "organizational_role_mode": summary_input.parsed_job_output.organizational_role_mode.value,
                "industry_domain": summary_input.parsed_job_output.industry_domain,
            },
            "story_strategy": {
                "focus_mode": summary_input.story_strategy.focus_mode.value,
                "narrative_anchor": summary_input.story_strategy.narrative_anchor,
                "summary_themes": bundle.supported_themes,
            },
            "style_policy": {
                "style_mode": summary_input.style_policy.style_mode.value,
                "forbid_first_person": summary_input.style_policy.forbid_first_person,
                "banned_phrases": sorted({*summary_input.style_policy.banned_phrases, *_WEAK_PHRASES}),
                "role_style_policy": role_style_policy.model_dump(mode="json"),
            },
            "length_constraints": {
                "max_sentences": summary_input.page_constraints.max_summary_sentences,
                "max_words": _max_summary_words(summary_input.page_constraints.max_summary_sentences),
            },
            "supported_signals": {
                "role_label": _role_label(
                    summary_input.parsed_job_output.functional_role_family,
                    summary_input.parsed_job_output.organizational_role_mode,
                ),
                "supported_tools": bundle.supported_tools,
                "supported_domain_phrases": bundle.supported_domain_phrases,
                "leadership_supported": bundle.leadership_supported,
                "evidence_ids": bundle.evidence_ids,
                "source_item_ids": bundle.source_item_ids,
            },
        }
        return (
            f"{self._load_prompt_template()}\n\n"
            f"INPUT:\n{json.dumps(payload, indent=2, sort_keys=True)}"
        )

    def _run_generation(self, prompt: str) -> SummaryGenerationResponse:
        client = self._client or build_openai_client()
        model = self._model or self._settings.phase3_generation_model
        raw_text = create_json_response_text(
            client=client,
            model=model,
            input_payload=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        )
        return self._parse_response(raw_text)

    def _parse_response(self, raw_text: str) -> SummaryGenerationResponse:
        try:
            payload = json.loads(raw_text)
        except JSONDecodeError as exc:
            raise MalformedSummaryGenerationResponseError(
                "summary generator returned malformed JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise MalformedSummaryGenerationResponseError(
                "summary generator response must be a JSON object"
            )
        try:
            return SummaryGenerationResponse.model_validate(payload)
        except ValidationError as exc:
            raise MalformedSummaryGenerationResponseError(
                "summary generator response failed schema validation"
            ) from exc

    def _precheck(
        self,
        summary_input: SummaryGenerationInput,
        bundle: SummarySignalBundle,
    ) -> GenerationQualitySignals:
        warnings: list[QualitySignal] = []
        if not bundle.supported_tools:
            warnings.append(
                QualitySignal(
                    signal_id=f"quality.summary.tools_missing.{summary_input.section_id}",
                    severity=QualitySignalSeverity.WARNING,
                    message="no strongly supported tools/platforms were available for summary emphasis",
                    section_id=summary_input.section_id,
                )
            )
        if not bundle.supported_themes:
            warnings.append(
                QualitySignal(
                    signal_id=f"quality.summary.themes_missing.{summary_input.section_id}",
                    severity=QualitySignalSeverity.WARNING,
                    message="story strategy themes were weakly supported and will be minimized",
                    section_id=summary_input.section_id,
                )
            )
        return GenerationQualitySignals(
            warnings=warnings,
            provenance_coverage_score=_coverage_score(bundle),
        )

    def _postcheck(
        self,
        summary_input: SummaryGenerationInput,
        bundle: SummarySignalBundle,
        summary_text: str,
        *,
        evidence_ids_used: list[str],
        themes_used: list[str],
    ) -> GenerationQualitySignals:
        hard_failures: list[QualitySignal] = []
        warnings: list[QualitySignal] = []
        text = summary_text.strip()
        text_lower = text.casefold()
        tokens = _tokenize(text)

        weak_phrases = sorted(phrase for phrase in _WEAK_PHRASES if phrase in text_lower)
        if weak_phrases:
            hard_failures.append(
                QualitySignal(
                    signal_id=f"quality.summary.weak_phrases.{summary_input.section_id}",
                    severity=QualitySignalSeverity.ERROR,
                    message="summary used blocked weak phrases: " + ", ".join(weak_phrases),
                    section_id=summary_input.section_id,
                )
            )

        if summary_input.style_policy.forbid_first_person and any(token in {"i", "me", "my", "mine"} for token in tokens):
            hard_failures.append(
                QualitySignal(
                    signal_id=f"quality.summary.first_person.{summary_input.section_id}",
                    severity=QualitySignalSeverity.ERROR,
                    message="summary used first-person language",
                    section_id=summary_input.section_id,
                )
            )

        policy_failures, policy_warnings = evaluate_rewrite_policy(
            RewritePolicyContext(
                target=RewritePolicyTarget.SUMMARY,
                section_id=summary_input.section_id,
                source_bullet_ids=list(bundle.source_bullet_ids),
                source_text=bundle.source_text,
                candidate_text=text,
                allowed_tools=list(bundle.supported_tools),
                supported_domain_phrases=list(bundle.supported_domain_phrases),
                leadership_supported=bundle.leadership_supported,
                organizational_role_mode=summary_input.parsed_job_output.organizational_role_mode,
            )
        ).to_quality_signals()
        hard_failures.extend(policy_failures)
        warnings.extend(policy_warnings)

        unsupported_tools = [
            tool
            for tool in _extract_supported_term_mentions(
                text,
                bundle.supported_tools
                + summary_input.parsed_job_output.must_have_skills
                + summary_input.parsed_job_output.preferred_skills,
            )
            if tool not in {value.casefold() for value in bundle.supported_tools}
        ]
        if unsupported_tools:
            hard_failures.append(
                QualitySignal(
                    signal_id=f"quality.summary.unsupported_tools.{summary_input.section_id}",
                    severity=QualitySignalSeverity.ERROR,
                    message="summary referenced unsupported tools or JD terms: " + ", ".join(sorted(set(unsupported_tools))),
                    reason_code=PolicyReasonCode.UNSUPPORTED_TOOL,
                    policy_severity=PolicySignalSeverity.REQUIRES_REGENERATION,
                    section_id=summary_input.section_id,
                )
            )

        sentence_count = _sentence_count(text)
        if sentence_count > summary_input.page_constraints.max_summary_sentences:
            hard_failures.append(
                QualitySignal(
                    signal_id=f"quality.summary.length.{summary_input.section_id}",
                    severity=QualitySignalSeverity.ERROR,
                    message="summary exceeded sentence limit",
                    section_id=summary_input.section_id,
                )
            )

        if len(tokens) > _max_summary_words(summary_input.page_constraints.max_summary_sentences):
            warnings.append(
                QualitySignal(
                    signal_id=f"quality.summary.word_count.{summary_input.section_id}",
                    severity=QualitySignalSeverity.WARNING,
                    message="summary is longer than the preferred concise word budget",
                    section_id=summary_input.section_id,
                )
            )

        role_tokens = set(_tokenize(_role_label(
            summary_input.parsed_job_output.functional_role_family,
            summary_input.parsed_job_output.organizational_role_mode,
        )))
        target_tokens = set(_tokenize(summary_input.parsed_job_output.target_role_title or ""))
        if not (role_tokens.intersection(tokens) or target_tokens.intersection(tokens)):
            warnings.append(
                QualitySignal(
                    signal_id=f"quality.summary.role_specificity.{summary_input.section_id}",
                    severity=QualitySignalSeverity.WARNING,
                    message="summary may be underspecified for the target role family",
                    section_id=summary_input.section_id,
                )
            )

        invalid_evidence_ids = [evidence_id for evidence_id in evidence_ids_used if evidence_id not in bundle.evidence_ids]
        if invalid_evidence_ids:
            hard_failures.append(
                QualitySignal(
                    signal_id=f"quality.summary.evidence_ids.{summary_input.section_id}",
                    severity=QualitySignalSeverity.ERROR,
                    message="summary referenced evidence ids outside the bounded input: " + ", ".join(invalid_evidence_ids),
                    section_id=summary_input.section_id,
                )
            )

        invalid_themes = [theme for theme in themes_used if theme not in bundle.supported_themes]
        if invalid_themes:
            warnings.append(
                QualitySignal(
                    signal_id=f"quality.summary.themes.{summary_input.section_id}",
                    severity=QualitySignalSeverity.WARNING,
                    message="summary used unsupported or weakly supported themes: " + ", ".join(invalid_themes),
                    section_id=summary_input.section_id,
                )
            )

        return GenerationQualitySignals(
            hard_failures=hard_failures,
            warnings=warnings,
            provenance_coverage_score=_coverage_score(bundle),
            style_alignment_score=_style_alignment_score(summary_input.style_policy.style_mode, hard_failures, warnings),
        )

    def _build_signal_bundle(self, summary_input: SummaryGenerationInput) -> SummarySignalBundle:
        experiences = sorted(summary_input.experiences, key=lambda item: item.relevance_score, reverse=True)
        projects = sorted(summary_input.projects, key=lambda item: item.relevance_score, reverse=True)
        skills = sorted(summary_input.skills, key=lambda item: item.relevance_score, reverse=True)

        source_item_ids = [item.source_item_id for item in [*experiences, *projects, *skills]]
        source_bullet_ids = [
            bullet.bullet_id
            for item in [*experiences, *projects]
            for bullet in item.bullets
        ]
        evidence_ids = list(_stable_unique([
            evidence_id
            for item in [*experiences, *projects, *skills]
            for evidence_id in item.evidence_unit_ids
        ]))

        tool_counter: Counter[str] = Counter()
        for item in experiences:
            tool_counter.update(tool.casefold() for tool in item.tools)
            for bullet in item.bullets:
                tool_counter.update(tool.casefold() for tool in bullet.tools)
        for item in projects:
            tool_counter.update(tool.casefold() for tool in item.tools)
            for bullet in item.bullets:
                tool_counter.update(tool.casefold() for tool in bullet.tools)
        for item in skills:
            tool_counter.update([item.skill_name.casefold()])

        supported_tools = [tool for tool, _count in tool_counter.most_common(4)]
        source_text_fragments = [
            item.title for item in experiences
        ] + [
            bullet.text for item in experiences for bullet in item.bullets
        ] + [
            item.role or item.name for item in projects
        ] + [
            item.summary or "" for item in projects
        ] + [
            bullet.text for item in projects for bullet in item.bullets
        ] + [
            item.skill_name for item in skills
        ]
        source_text = " ".join(fragment for fragment in source_text_fragments if fragment).strip()
        source_tokens = set(_tokenize(source_text))

        supported_themes = []
        for theme in summary_input.story_strategy.summary_themes:
            if _tokens_supported(theme, source_tokens):
                supported_themes.append(theme)
        if not supported_themes:
            requirement_candidates = [
                *summary_input.parsed_job_output.must_have_requirements,
                *summary_input.parsed_job_output.preferred_requirements,
            ]
            supported_themes = [theme for theme in requirement_candidates[:3] if _tokens_supported(theme, source_tokens)]

        supported_domain_phrases: list[str] = []
        if summary_input.parsed_job_output.industry_domain and _tokens_supported(
            summary_input.parsed_job_output.industry_domain,
            source_tokens,
        ):
            supported_domain_phrases.append(summary_input.parsed_job_output.industry_domain)

        leadership_supported = any(term in source_tokens for term in _LEADERSHIP_TERMS) or (
            summary_input.parsed_job_output.organizational_role_mode
            in {
                OrganizationalRoleMode.TECH_LEAD,
                OrganizationalRoleMode.PEOPLE_MANAGER,
                OrganizationalRoleMode.DIRECTOR_OR_HEAD,
            }
            and any(term in source_tokens for term in {"lead", "manager", "mentored", "managed"})
        )

        return SummarySignalBundle(
            source_item_ids=list(_stable_unique(source_item_ids)),
            source_bullet_ids=list(_stable_unique(source_bullet_ids)),
            evidence_ids=evidence_ids,
            supported_tools=supported_tools,
            supported_themes=supported_themes[:3],
            supported_domain_phrases=supported_domain_phrases[:1],
            leadership_supported=leadership_supported,
            source_text=source_text,
        )

    def _validated_evidence_ids(self, evidence_ids: list[str], bundle: SummarySignalBundle) -> list[str]:
        allowed = set(bundle.evidence_ids)
        valid = [evidence_id for evidence_id in evidence_ids if evidence_id in allowed]
        if not valid:
            raise SummaryGenerationError("summary generator did not return any valid bounded evidence ids")
        return valid

    def _validated_themes(self, themes: list[str], bundle: SummarySignalBundle) -> list[str]:
        allowed = set(bundle.supported_themes)
        if not allowed:
            return []
        return [theme for theme in themes if theme in allowed][:3]

    def _build_fallback_summary(
        self,
        summary_input: SummaryGenerationInput,
        bundle: SummarySignalBundle,
    ) -> str:
        role_phrase = _role_label(
            summary_input.parsed_job_output.functional_role_family,
            summary_input.parsed_job_output.organizational_role_mode,
        )
        supported_tools = bundle.supported_tools[:3]
        supported_themes = bundle.supported_themes[:2]
        clauses = [role_phrase.capitalize()]
        if supported_tools:
            clauses.append("with experience in " + ", ".join(supported_tools))
        if supported_themes:
            clauses.append("focused on " + " and ".join(theme.casefold() for theme in supported_themes))
        elif bundle.supported_domain_phrases:
            clauses.append("working in " + bundle.supported_domain_phrases[0].casefold())
        if (
            summary_input.parsed_job_output.organizational_role_mode
            in {OrganizationalRoleMode.TECH_LEAD, OrganizationalRoleMode.PEOPLE_MANAGER, OrganizationalRoleMode.DIRECTOR_OR_HEAD}
            and bundle.leadership_supported
        ):
            clauses.append("with supported leadership experience")
        return " ".join(clauses).strip().rstrip(".") + "."

    def _load_prompt_template(self) -> str:
        if self._prompt_template is not None:
            return self._prompt_template
        return load_phase5_summary_generation_prompt().strip()


def _role_label(
    role_family: FunctionalRoleFamily,
    organizational_role_mode: OrganizationalRoleMode,
) -> str:
    base = _ROLE_LABELS.get(role_family, "engineer")
    if organizational_role_mode == OrganizationalRoleMode.TECH_LEAD:
        return f"{base} lead"
    if organizational_role_mode == OrganizationalRoleMode.PEOPLE_MANAGER:
        return "engineering manager"
    if organizational_role_mode == OrganizationalRoleMode.DIRECTOR_OR_HEAD:
        return "engineering leader"
    return base


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())


def _tokens_supported(value: str, source_tokens: set[str]) -> bool:
    tokens = [token for token in _tokenize(value) if token not in _STOPWORDS]
    return bool(tokens) and all(token in source_tokens for token in tokens)


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"[.!?]+", text) if part.strip()])


def _max_summary_words(max_sentences: int) -> int:
    return max(18, min(60, max_sentences * 18))


def _extract_supported_term_mentions(text: str, candidate_terms: list[str]) -> list[str]:
    normalized_text = text.casefold()
    return [term.casefold() for term in candidate_terms if term.casefold() in normalized_text]


def _coverage_score(bundle: SummarySignalBundle) -> float:
    coverage = 0.0
    if bundle.evidence_ids:
        coverage += 0.4
    if bundle.supported_themes:
        coverage += 0.3
    if bundle.supported_tools:
        coverage += 0.2
    if bundle.supported_domain_phrases or bundle.leadership_supported:
        coverage += 0.1
    return round(min(1.0, coverage), 4)


def _style_alignment_score(
    style_mode: GenerationStyleMode,
    hard_failures: list[QualitySignal],
    warnings: list[QualitySignal],
) -> float:
    base = {
        GenerationStyleMode.ATS_BALANCED: 0.95,
        GenerationStyleMode.DIRECT: 0.9,
        GenerationStyleMode.CONSERVATIVE: 0.92,
    }[style_mode]
    score = base - (0.25 * len(hard_failures)) - (0.08 * len(warnings))
    return round(max(0.0, min(1.0, score)), 4)
