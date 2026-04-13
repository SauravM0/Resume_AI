"""Dedicated bounded bullet rewrite service for Phase 5."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from json import JSONDecodeError
import re
from typing import TYPE_CHECKING

from pydantic import Field, ValidationError, model_validator

from ..config import DEFAULT_SETTINGS, Settings
from ..models import NonEmptyStr, StableId, StrictModel
from ..openai_client import build_openai_client, create_json_response_text
from ..phase3_models import BulletRewriteStrategy
from ..phase3_rewrite_policy import evaluate_bullet_rewrite
from ..prompt_loader import load_phase5_bullet_rewrite_prompt
from .contracts import (
    BulletRewriteInput,
    BulletRewriteOutput,
    GenerationQualitySignals,
    GenerationStyleMode,
    QualitySignal,
    QualitySignalSeverity,
    SelectedBulletEvidence,
)
from .quality_validator import merge_quality_signals, validate_bullet_outputs_quality
from .role_style_policy import resolve_role_style_policy
from .rewrite_policy import RewritePolicyContext, RewritePolicyTarget, evaluate_rewrite_policy

if TYPE_CHECKING:
    from google.genai.client import Client as GeminiClient

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+#/%-]*")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_OWNERSHIP_RISK_PAIRS = {
    "supported": {"owned", "led", "managed", "architected"},
    "contributed": {"led", "owned", "managed"},
    "helped": {"led", "owned", "managed"},
    "assisted": {"led", "owned", "managed"},
}
_LEADERSHIP_TERMS = {"led", "managed", "owned", "directed", "architected", "mentored", "headed"}
_SCOPE_RISK_TERMS = {"platform-wide", "cross-functional", "organization-wide", "company-wide", "global"}
_ROLE_PHRASE_HINTS = {
    "backend": {"api", "service", "reliability", "backend"},
    "frontend": {"ui", "ux", "frontend", "design system", "react"},
    "devops": {"infrastructure", "deployment", "ci/cd", "terraform"},
    "platform": {"platform", "internal tooling", "developer workflow"},
    "data": {"pipeline", "etl", "warehouse", "data"},
    "analytics": {"analysis", "insights", "experimentation", "reporting"},
    "fullstack": {"frontend", "backend", "integration", "full-stack"},
    "product": {"roadmap", "prioritization", "outcomes", "cross-functional"},
}


class BulletRewriteError(RuntimeError):
    """Raised when bounded bullet rewriting cannot complete safely."""


class MalformedBulletRewriteResponseError(BulletRewriteError):
    """Raised when the bullet rewrite model returns malformed JSON."""


class BulletRewriteResponse(StrictModel):
    """Strict JSON response expected from the bullet rewrite model."""

    rewritten_text: NonEmptyStr
    evidence_ids_used: list[StableId] = Field(default_factory=list)
    rewrite_strategy: BulletRewriteStrategy

    @model_validator(mode="after")
    def validate_shape(self) -> "BulletRewriteResponse":
        if not self.evidence_ids_used:
            raise ValueError("evidence_ids_used must contain at least one bounded evidence id")
        return self


@dataclass(frozen=True, slots=True)
class BulletSupportBundle:
    """Deterministically extracted source support for one bullet."""

    source_bullet_id: str
    source_text: str
    source_tokens: set[str]
    source_numbers: set[str]
    source_tools: set[str]
    evidence_ids: list[str]


class BulletRewriteService:
    """Rewrite bounded bullets conservatively with deterministic safety checks."""

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

    def rewrite(self, rewrite_input: BulletRewriteInput) -> list[BulletRewriteOutput]:
        """Rewrite each bounded source bullet independently."""

        outputs: list[BulletRewriteOutput] = []
        for source_bullet in rewrite_input.source_bullets[: rewrite_input.requested_bullet_count]:
            outputs.append(self.rewrite_single_bullet(rewrite_input, source_bullet))
        return outputs

    def rewrite_single_bullet(
        self,
        rewrite_input: BulletRewriteInput,
        source_bullet: SelectedBulletEvidence,
    ) -> BulletRewriteOutput:
        """Rewrite one bounded source bullet and attach deterministic QA signals."""

        bundle = _build_support_bundle(source_bullet, rewrite_input.evidence_unit_ids)
        precheck_signals = self._precheck(rewrite_input, source_bullet, bundle)
        warnings = [signal.message for signal in precheck_signals.warnings]

        if not source_bullet.rewrite_allowed:
            warnings.append("rewrite not allowed for this bullet; source text was preserved")
            rewritten_text = _normalize_source_text(source_bullet.text)
            evidence_ids_used = list(bundle.evidence_ids)
            rewrite_strategy = BulletRewriteStrategy.LIGHT_REWRITE
        else:
            try:
                response = self._run_generation(self.build_prompt(rewrite_input, source_bullet, bundle))
                rewritten_text = response.rewritten_text
                evidence_ids_used = _validated_evidence_ids(response.evidence_ids_used, bundle)
                rewrite_strategy = response.rewrite_strategy
            except BulletRewriteError as exc:
                warnings.append(str(exc))
                rewritten_text = _normalize_source_text(source_bullet.text)
                evidence_ids_used = list(bundle.evidence_ids)
                rewrite_strategy = BulletRewriteStrategy.LIGHT_REWRITE

        postcheck_signals = self._postcheck(
            rewrite_input,
            source_bullet,
            bundle,
            rewritten_text=rewritten_text,
            evidence_ids_used=evidence_ids_used,
        )
        final_warnings = warnings + [signal.message for signal in postcheck_signals.warnings]
        final_signal_warnings = [*precheck_signals.warnings, *postcheck_signals.warnings]
        final_signal_hard_failures = list(postcheck_signals.hard_failures)
        final_provenance_score = postcheck_signals.provenance_coverage_score
        final_style_score = postcheck_signals.style_alignment_score

        if postcheck_signals.hard_failures:
            final_warnings.append("rewrite failed deterministic QA and was replaced with normalized source text")
            rewritten_text = _normalize_source_text(source_bullet.text)
            evidence_ids_used = list(bundle.evidence_ids)
            rewrite_strategy = BulletRewriteStrategy.LIGHT_REWRITE
            fallback_signals = self._postcheck(
                rewrite_input,
                source_bullet,
                bundle,
                rewritten_text=rewritten_text,
                evidence_ids_used=evidence_ids_used,
            )
            final_signal_warnings = [*final_signal_warnings, *fallback_signals.warnings]
            final_signal_hard_failures = [*final_signal_hard_failures, *fallback_signals.hard_failures]
            final_provenance_score = fallback_signals.provenance_coverage_score
            final_style_score = fallback_signals.style_alignment_score

        result = BulletRewriteOutput(
            section_id=rewrite_input.section_id,
            source_item_id=rewrite_input.source_item_id,
            source_item_type=rewrite_input.source_item_type,
            source_bullet_id=source_bullet.bullet_id,
            rewritten_text=rewritten_text,
            evidence_ids_used=evidence_ids_used,
            warnings=final_warnings,
            rewrite_quality_signals=GenerationQualitySignals(
                hard_failures=final_signal_hard_failures,
                warnings=final_signal_warnings,
                provenance_coverage_score=final_provenance_score,
                style_alignment_score=final_style_score,
            ),
            rewrite_strategy=rewrite_strategy,
            role_family=rewrite_input.role_family,
            organizational_role_mode=rewrite_input.organizational_role_mode,
            style_mode=rewrite_input.style_policy.style_mode,
        )
        return result.model_copy(
            update={
                "rewrite_quality_signals": merge_quality_signals(
                    result.rewrite_quality_signals,
                    validate_bullet_outputs_quality(rewrite_input.section_id, [result]),
                )
            }
        )

    def build_prompt(
        self,
        rewrite_input: BulletRewriteInput,
        source_bullet: SelectedBulletEvidence,
        bundle: BulletSupportBundle,
    ) -> str:
        """Build the dedicated bounded prompt for one source bullet."""

        role_style_policy = resolve_role_style_policy(
            role_family=rewrite_input.role_family,
            organizational_role_mode=rewrite_input.organizational_role_mode,
        )
        payload = {
            "role_context": {
                "role_family": rewrite_input.role_family.value,
                "organizational_role_mode": rewrite_input.organizational_role_mode.value,
                "role_phrase_hints": sorted(
                    _ROLE_PHRASE_HINTS.get(rewrite_input.role_family.value, set())
                ),
            },
            "style_policy": {
                "style_mode": rewrite_input.style_policy.style_mode.value,
                "require_action_verb_bullets": rewrite_input.style_policy.require_action_verb_bullets,
                "role_style_policy": role_style_policy.model_dump(mode="json"),
            },
            "source_bullet": {
                "source_bullet_id": source_bullet.bullet_id,
                "text": source_bullet.text,
                "tools": list(source_bullet.tools),
                "evidence_ids": bundle.evidence_ids,
            },
            "bounded_rules": {
                "must_preserve_numbers": sorted(bundle.source_numbers),
                "must_preserve_tools": sorted(bundle.source_tools),
                "must_not_upgrade_ownership": True,
                "must_not_upgrade_scope": True,
            },
        }
        return f"{self._load_prompt_template()}\n\nINPUT:\n{json.dumps(payload, indent=2, sort_keys=True)}"

    def _run_generation(self, prompt: str) -> BulletRewriteResponse:
        client = self._client or build_openai_client()
        model = self._model or self._settings.phase3_generation_model
        raw_text = create_json_response_text(
            client=client,
            model=model,
            input_payload=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        )
        return self._parse_response(raw_text)

    def _parse_response(self, raw_text: str) -> BulletRewriteResponse:
        try:
            payload = json.loads(raw_text)
        except JSONDecodeError as exc:
            raise MalformedBulletRewriteResponseError("bullet rewrite generator returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise MalformedBulletRewriteResponseError("bullet rewrite response must be a JSON object")
        try:
            return BulletRewriteResponse.model_validate(payload)
        except ValidationError as exc:
            raise MalformedBulletRewriteResponseError("bullet rewrite response failed schema validation") from exc

    def _precheck(
        self,
        rewrite_input: BulletRewriteInput,
        source_bullet: SelectedBulletEvidence,
        bundle: BulletSupportBundle,
    ) -> GenerationQualitySignals:
        warnings: list[QualitySignal] = []
        if not bundle.source_numbers and rewrite_input.style_policy.emphasize_metrics:
            warnings.append(
                QualitySignal(
                    signal_id=f"quality.rewrite.no_metrics.{source_bullet.bullet_id}",
                    severity=QualitySignalSeverity.WARNING,
                    message="source bullet has no explicit metric; rewrite must stay conservative",
                    section_id=rewrite_input.section_id,
                    source_item_id=rewrite_input.source_item_id,
                    source_bullet_ids=[source_bullet.bullet_id],
                )
            )
        return GenerationQualitySignals(
            warnings=warnings,
            provenance_coverage_score=1.0 if bundle.evidence_ids else 0.0,
        )

    def _postcheck(
        self,
        rewrite_input: BulletRewriteInput,
        source_bullet: SelectedBulletEvidence,
        bundle: BulletSupportBundle,
        *,
        rewritten_text: str,
        evidence_ids_used: list[str],
    ) -> GenerationQualitySignals:
        hard_failures: list[QualitySignal] = []
        warnings: list[QualitySignal] = []

        if rewritten_text.strip() == source_bullet.text.strip():
            warnings.append(
                QualitySignal(
                    signal_id=f"quality.rewrite.no_change.{source_bullet.bullet_id}",
                    severity=QualitySignalSeverity.WARNING,
                    message="rewrite stayed very close to source text",
                    section_id=rewrite_input.section_id,
                    source_item_id=rewrite_input.source_item_id,
                    source_bullet_ids=[source_bullet.bullet_id],
                )
            )

        policy_failures, policy_warnings = evaluate_rewrite_policy(
            RewritePolicyContext(
                target=RewritePolicyTarget.BULLET,
                section_id=rewrite_input.section_id,
                source_item_id=rewrite_input.source_item_id,
                source_bullet_ids=[source_bullet.bullet_id],
                source_text=bundle.source_text,
                candidate_text=rewritten_text,
                allowed_tools=sorted(bundle.source_tools),
                leadership_supported=any(term in bundle.source_tokens for term in _LEADERSHIP_TERMS),
                organizational_role_mode=rewrite_input.organizational_role_mode,
            )
        ).to_quality_signals()
        hard_failures.extend(policy_failures)
        warnings.extend(policy_warnings)

        metric_failure = _metric_preservation_failure(bundle, rewritten_text)
        if metric_failure:
            hard_failures.append(_signal("metrics", metric_failure, rewrite_input, source_bullet))

        tool_failure = _tool_preservation_failure(bundle, rewritten_text)
        if tool_failure:
            hard_failures.append(_signal("tools", tool_failure, rewrite_input, source_bullet))

        inflation_failures = _ownership_scope_inflation_failures(bundle, rewritten_text)
        hard_failures.extend(
            _signal("inflation", message, rewrite_input, source_bullet)
            for message in inflation_failures
        )

        evidence_failures = [evidence_id for evidence_id in evidence_ids_used if evidence_id not in bundle.evidence_ids]
        if evidence_failures:
            hard_failures.append(
                _signal(
                    "evidence_ids",
                    "rewrite referenced evidence ids outside the bounded input: " + ", ".join(evidence_failures),
                    rewrite_input,
                    source_bullet,
                )
            )

        assessment = evaluate_bullet_rewrite(
            [
                _Phase3CompatBullet(
                    id=source_bullet.bullet_id,
                    text=source_bullet.text,
                    tools=list(source_bullet.tools),
                )
            ],
            rewritten_text,
        )
        for violation in assessment.violations:
            signal = _signal(
                f"rewrite_policy_{violation.violation_type.value}",
                violation.message,
                rewrite_input,
                source_bullet,
                severity=QualitySignalSeverity.ERROR if violation.severity.value == "error" else QualitySignalSeverity.WARNING,
            )
            if violation.severity.value == "error":
                hard_failures.append(signal)
            else:
                warnings.append(signal)

        if _word_count(rewritten_text) > max(8, _word_count(source_bullet.text) + 3):
            warnings.append(
                _signal(
                    "length_growth",
                    "rewrite is not materially shorter than the source bullet",
                    rewrite_input,
                    source_bullet,
                    severity=QualitySignalSeverity.WARNING,
                )
            )

        return GenerationQualitySignals(
            hard_failures=hard_failures,
            warnings=warnings,
            provenance_coverage_score=1.0 if bundle.evidence_ids else 0.0,
            style_alignment_score=_style_alignment_score(rewrite_input.style_policy.style_mode, hard_failures, warnings),
        )

    def _load_prompt_template(self) -> str:
        if self._prompt_template is not None:
            return self._prompt_template
        return load_phase5_bullet_rewrite_prompt().strip()


class _Phase3CompatBullet(StrictModel):
    """Minimal compatibility model for reuse of existing rewrite heuristics."""

    id: StableId
    text: NonEmptyStr
    tools: list[NonEmptyStr] = Field(default_factory=list)


def _build_support_bundle(source_bullet: SelectedBulletEvidence, fallback_evidence_ids: list[str]) -> BulletSupportBundle:
    evidence_ids = list(_stable_unique([*source_bullet.evidence_unit_ids, *fallback_evidence_ids]))
    return BulletSupportBundle(
        source_bullet_id=source_bullet.bullet_id,
        source_text=source_bullet.text,
        source_tokens=set(_tokenize(source_bullet.text)),
        source_numbers=set(_NUMBER_PATTERN.findall(source_bullet.text)),
        source_tools={tool.casefold() for tool in source_bullet.tools},
        evidence_ids=evidence_ids,
    )


def _validated_evidence_ids(evidence_ids: list[str], bundle: BulletSupportBundle) -> list[str]:
    valid = [evidence_id for evidence_id in evidence_ids if evidence_id in bundle.evidence_ids]
    if not valid:
        raise BulletRewriteError("bullet rewrite generator did not return any valid bounded evidence ids")
    return valid


def _normalize_source_text(text: str) -> str:
    stripped = re.sub(r"\s+", " ", text.strip())
    return stripped.rstrip(".") + "."


def _metric_preservation_failure(bundle: BulletSupportBundle, rewritten_text: str) -> str | None:
    rewritten_numbers = set(_NUMBER_PATTERN.findall(rewritten_text))
    if rewritten_numbers != bundle.source_numbers:
        missing = sorted(bundle.source_numbers - rewritten_numbers)
        inserted = sorted(rewritten_numbers - bundle.source_numbers)
        parts: list[str] = []
        if missing:
            parts.append("missing source metrics: " + ", ".join(missing))
        if inserted:
            parts.append("inserted unsupported metrics: " + ", ".join(inserted))
        return "; ".join(parts)
    return None


def _tool_preservation_failure(bundle: BulletSupportBundle, rewritten_text: str) -> str | None:
    rewritten_lower = rewritten_text.casefold()
    missing = [tool for tool in bundle.source_tools if tool not in rewritten_lower]
    mentioned = {tool for tool in bundle.source_tools if tool in rewritten_lower}
    inserted = [
        tool
        for tool in {"aws", "azure", "docker", "gcp", "graphql", "kubernetes", "python", "react", "snowflake", "terraform", "typescript"}
        if tool in rewritten_lower and tool not in bundle.source_tools
    ]
    if missing or inserted:
        parts: list[str] = []
        if missing:
            parts.append("missing source tools: " + ", ".join(sorted(missing)))
        if inserted:
            parts.append("inserted unsupported tools: " + ", ".join(sorted(inserted)))
        return "; ".join(parts)
    if bundle.source_tools and not mentioned:
        return "rewrite dropped all supported source tools"
    return None


def _ownership_scope_inflation_failures(bundle: BulletSupportBundle, rewritten_text: str) -> list[str]:
    failures: list[str] = []
    rewritten_tokens = set(_tokenize(rewritten_text))

    for source_term, blocked_terms in _OWNERSHIP_RISK_PAIRS.items():
        if source_term in bundle.source_tokens:
            inserted = sorted(term for term in blocked_terms if term in rewritten_tokens and term not in bundle.source_tokens)
            if inserted:
                failures.append(
                    f"rewrite upgraded ownership language from {source_term} to " + ", ".join(inserted)
                )

    if not any(term in bundle.source_tokens for term in _LEADERSHIP_TERMS):
        inserted_leadership = sorted(term for term in _LEADERSHIP_TERMS if term in rewritten_tokens and term not in bundle.source_tokens)
        if inserted_leadership:
            failures.append("rewrite introduced unsupported leadership terms: " + ", ".join(inserted_leadership))

    inserted_scope = sorted(term for term in _SCOPE_RISK_TERMS if term in rewritten_text.casefold() and term not in bundle.source_text.casefold())
    if inserted_scope:
        failures.append("rewrite introduced unsupported scope terms: " + ", ".join(inserted_scope))

    if "architecture" in rewritten_tokens and "architecture" not in bundle.source_tokens and "architect" not in bundle.source_tokens:
        failures.append("rewrite implied architecture ownership not supported by the source bullet")

    return failures


def _signal(
    code: str,
    message: str,
    rewrite_input: BulletRewriteInput,
    source_bullet: SelectedBulletEvidence,
    *,
    severity: QualitySignalSeverity = QualitySignalSeverity.ERROR,
) -> QualitySignal:
    return QualitySignal(
        signal_id=f"quality.rewrite.{code}.{source_bullet.bullet_id}",
        severity=severity,
        message=message,
        section_id=rewrite_input.section_id,
        source_item_id=rewrite_input.source_item_id,
        source_bullet_ids=[source_bullet.bullet_id],
    )


def _tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())


def _word_count(text: str) -> int:
    return len(_tokenize(text))


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _style_alignment_score(
    style_mode: GenerationStyleMode,
    hard_failures: list[QualitySignal],
    warnings: list[QualitySignal],
) -> float:
    base = {
        GenerationStyleMode.ATS_BALANCED: 0.95,
        GenerationStyleMode.DIRECT: 0.92,
        GenerationStyleMode.CONSERVATIVE: 0.94,
    }[style_mode]
    score = base - (0.25 * len(hard_failures)) - (0.07 * len(warnings))
    return round(max(0.0, min(1.0, score)), 4)
