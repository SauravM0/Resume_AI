"""Semantic faithfulness validator for the Phase 6 verification gate.

This service performs constrained AI judgment after deterministic provenance is
available. It does not generate or rewrite resume content; it only classifies
whether generated text remains faithful to source-supported evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field, ValidationError, model_validator

from backend.app.schemas.verification import VerificationIssue
from backend.app.services.verification.provenance_service import ProvenanceMatch
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
)
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.models import NonEmptyStr, ScoreValue, StableId, StrictModel
from resume_optimizer.gemini_client import build_gemini_client

PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "ai"
    / "prompts"
    / "verification_semantic_check.txt"
)


class SemanticVerdict(StrEnum):
    """Allowed verdicts from the semantic faithfulness checker."""

    PASS = "pass"
    WEAK_SUPPORT = "weak_support"
    FAIL = "fail"


class OverclaimDimension(StrEnum):
    """Semantic overclaim dimensions evaluated by the verifier."""

    OWNERSHIP_INFLATION = "ownership_inflation"
    LEADERSHIP_INFLATION = "leadership_inflation"
    ARCHITECTURE_INFLATION = "architecture_inflation"
    CAUSALITY_INFLATION = "causality_inflation"
    EXPERTISE_INFLATION = "expertise_inflation"
    SUMMARY_OVERREACH = "summary_overreach"
    UNSUPPORTED_DOMAIN_DEPTH = "unsupported_domain_depth"


class SemanticCheckResponse(StrictModel):
    """Strict JSON response schema for semantic verification model output."""

    verdict: SemanticVerdict
    confidence: ScoreValue
    issue_category: IssueCategory | None = None
    explanation: NonEmptyStr
    overclaim_dimensions: list[OverclaimDimension] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_verdict_shape(self) -> "SemanticCheckResponse":
        """Keep pass/fail response fields coherent for downstream issue mapping."""

        if self.verdict == SemanticVerdict.PASS and self.overclaim_dimensions:
            raise ValueError("pass verdict must not include overclaim_dimensions")
        if self.verdict == SemanticVerdict.FAIL and not self.overclaim_dimensions:
            raise ValueError("fail verdict requires at least one overclaim dimension")
        return self


class SemanticValidationResult(StrictModel):
    """Structured semantic validation outcome consumable by orchestration code."""

    item_id: StableId
    response: SemanticCheckResponse
    issues: list[VerificationIssue] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SemanticValidationInput:
    """Input for one semantic faithfulness check."""

    item_id: str
    item_type: str
    generated_text: str
    provenance_matches: Sequence[ProvenanceMatch]


class ResponsesClientProtocol(Protocol):
    """Subset of the OpenAI Responses API client used by this service."""

    responses: Any


class SemanticValidationError(RuntimeError):
    """Raised when semantic verification cannot produce a valid judgment."""


class MalformedSemanticResponseError(SemanticValidationError):
    """Raised when the semantic verifier returns malformed JSON or schema."""


class SemanticValidatorService:
    """Run semantic faithfulness checks with strict JSON parsing and retry."""

    def __init__(
        self,
        *,
        client: ResponsesClientProtocol | None = None,
        model: str | None = None,
        max_attempts: int = 2,
        prompt_template: str | None = None,
    ) -> None:
        """Create a semantic verifier with an injectable model client."""

        self._client = client
        self._model = (
            model
            or getattr(DEFAULT_SETTINGS, "phase6_semantic_model", None)
            or DEFAULT_SETTINGS.phase3_generation_model
        )
        self._max_attempts = max(1, max_attempts)
        self._prompt_template = prompt_template

    def validate_item(self, validation_input: SemanticValidationInput) -> SemanticValidationResult:
        """Validate one generated item and return semantic issues, if any."""

        response = self._run_with_retry(validation_input)
        issues = self._issues_from_response(validation_input, response)
        return SemanticValidationResult(
            item_id=validation_input.item_id,
            response=response,
            issues=issues,
        )

    def build_prompt(self, validation_input: SemanticValidationInput) -> str:
        """Package generated text, provenance evidence, instructions, and schema."""

        evidence = [
            {
                "source_entity_type": match.source_entity_type.value,
                "source_entity_id": match.source_entity_id,
                "source_bullet_id": match.source_bullet_id,
                "relation_type": match.relation_type.value,
                "evidence_strength": match.evidence_strength.value,
                "source_span": match.source_span_json,
                "matched_tokens": list(match.matched_tokens),
            }
            for match in validation_input.provenance_matches
        ]
        payload = {
            "verifier_instructions": {
                "judge_only": True,
                "must_not_rewrite": True,
                "must_not_suggest_inflated_language": True,
                "must_only_judge_support": True,
            },
            "generated_item": {
                "item_id": validation_input.item_id,
                "item_type": validation_input.item_type,
                "text": validation_input.generated_text,
            },
            "provenance_linked_source_evidence": evidence,
            "output_schema": SemanticCheckResponse.model_json_schema(),
        }
        return f"{self._load_prompt_template()}\n\nINPUT:\n{json.dumps(payload, indent=2, sort_keys=True)}"

    def _run_with_retry(self, validation_input: SemanticValidationInput) -> SemanticCheckResponse:
        """Call the model and retry once when JSON/schema parsing fails."""

        prompt = self.build_prompt(validation_input)
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            attempt_prompt = prompt
            if attempt > 1:
                attempt_prompt = (
                    f"{prompt}\n\nYour previous response was malformed. "
                    "Return exactly one valid JSON object matching the schema. "
                    "No markdown, commentary, rewrites, or suggestions."
                )
            raw_text = self._call_model(attempt_prompt)
            try:
                return self.parse_response(raw_text)
            except MalformedSemanticResponseError as exc:
                last_error = exc
        raise SemanticValidationError("Semantic verifier returned malformed JSON/schema repeatedly.") from last_error

    def _call_model(self, prompt: str) -> str:
        """Execute one low-temperature JSON-only semantic verification call."""

        client = self._client or build_gemini_client()
        input_messages = [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ]
        try:
            response = client.responses.create(
                model=self._model,
                input=input_messages,
                text={"format": {"type": "json_object"}},
                temperature=0,
            )
        except TypeError:
            response = client.responses.create(
                model=self._model,
                input=input_messages,
                text={"format": {"type": "json_object"}},
            )
        response_text = getattr(response, "output_text", "")
        if not response_text.strip():
            raise SemanticValidationError("Semantic verifier returned an empty response.")
        return response_text

    def parse_response(self, raw_text: str) -> SemanticCheckResponse:
        """Parse and strictly validate the model JSON response."""

        try:
            payload = json.loads(raw_text)
        except JSONDecodeError as exc:
            raise MalformedSemanticResponseError("Semantic verifier returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise MalformedSemanticResponseError("Semantic verifier response must be a JSON object.")
        try:
            return SemanticCheckResponse.model_validate(payload)
        except ValidationError as exc:
            raise MalformedSemanticResponseError("Semantic verifier response failed schema validation.") from exc

    def _issues_from_response(
        self,
        validation_input: SemanticValidationInput,
        response: SemanticCheckResponse,
    ) -> list[VerificationIssue]:
        """Map semantic verdicts to structured verification issues."""

        if response.verdict == SemanticVerdict.PASS:
            return []
        severity = (
            IssueSeverity.MEDIUM
            if response.verdict == SemanticVerdict.WEAK_SUPPORT
            else IssueSeverity.HIGH
        )
        category = response.issue_category or (
            IssueCategory.PROVENANCE_WEAK
            if response.verdict == SemanticVerdict.WEAK_SUPPORT
            else IssueCategory.UNSUPPORTED_CLAIM
        )
        return [
            VerificationIssue(
                id=f"issue.semantic_faithfulness.{validation_input.item_id}",
                category=category,
                severity=severity,
                message=response.explanation,
                generated_item_id=validation_input.item_id,
                source_item_ids=sorted(
                    {match.source_entity_id for match in validation_input.provenance_matches}
                ),
                source_bullet_ids=sorted(
                    {
                        match.source_bullet_id
                        for match in validation_input.provenance_matches
                        if match.source_bullet_id is not None
                    }
                ),
                evidence_strength=EvidenceStrength.WEAK
                if response.verdict == SemanticVerdict.WEAK_SUPPORT
                else EvidenceStrength.NONE,
                suggested_fallback=FallbackAction.REQUIRE_HUMAN_REVIEW,
                validator_name="semantic_faithfulness_validator",
            )
        ]

    def _load_prompt_template(self) -> str:
        """Load verifier instructions from disk unless injected for tests."""

        if self._prompt_template is not None:
            return self._prompt_template
        try:
            return PROMPT_PATH.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SemanticValidationError(f"Unable to load semantic verification prompt: {PROMPT_PATH}") from exc
