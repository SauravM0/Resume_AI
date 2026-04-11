"""Deterministic-first Phase 1 parser with LLM enrichment."""

from __future__ import annotations

from json import JSONDecodeError
import json
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .config import DEFAULT_SETTINGS
from .job_models import RawJobDescriptionRequest
from .openai_client import build_openai_client, create_json_response_text
from .phase1_deterministic_extractors import (
    extract_deterministic_job_description_artifacts,
)
from .phase1_merge import merge_phase1_deterministic_and_llm
from .phase1_models import Phase1ParseResult
from .prompt_loader import format_phase1_job_enrichment_prompt

if TYPE_CHECKING:
    from openai import OpenAI


class Phase1ParserError(RuntimeError):
    """Raised when the rebuilt Phase 1 parser cannot return valid structured output."""


class MalformedPhase1ParserJSONError(Phase1ParserError):
    """Raised when the Phase 1 enrichment model response is not valid JSON."""


def parse_job_description_with_llm_enrichment(
    job_description_text: str,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> Phase1ParseResult:
    """Parse a JD deterministically first, then enrich it with a strict LLM pass."""

    try:
        request = RawJobDescriptionRequest(job_description_text=job_description_text)
    except ValidationError as exc:
        raise Phase1ParserError(
            "Phase 1 parser requires a non-empty raw job description."
        ) from exc

    deterministic = extract_deterministic_job_description_artifacts(
        request.job_description_text
    )
    prompt = format_phase1_job_enrichment_prompt(request, deterministic)
    resolved_client = client or build_openai_client()
    resolved_model = model or DEFAULT_SETTINGS.phase1_job_analysis_model

    response_text = _run_phase1_enrichment_call(
        client=resolved_client,
        model=resolved_model,
        prompt=prompt,
    )

    try:
        payload = _parse_json_object(response_text)
    except MalformedPhase1ParserJSONError:
        retry_text = _run_phase1_enrichment_call(
            client=resolved_client,
            model=resolved_model,
            prompt=(
                f"{prompt}\n\n"
                "Your previous output was not valid JSON. "
                "Return valid JSON only with a single top-level object."
            ),
        )
        try:
            payload = _parse_json_object(retry_text)
        except MalformedPhase1ParserJSONError as exc:
            raise Phase1ParserError(
                "Phase 1 enrichment returned malformed JSON twice."
            ) from exc

    try:
        enriched = _validate_or_repair_phase1_payload(payload, deterministic)
    except ValidationError as exc:
        retry_text = _run_phase1_enrichment_call(
            client=resolved_client,
            model=resolved_model,
            prompt=(
                f"{prompt}\n\n"
                "Your previous JSON failed validation. "
                "Correct the schema issues and return valid JSON only.\n"
                f"Validation summary: {_condense_validation_errors(exc)}"
            ),
        )
        try:
            retry_payload = _parse_json_object(retry_text)
            enriched = _validate_or_repair_phase1_payload(retry_payload, deterministic)
        except (ValidationError, MalformedPhase1ParserJSONError) as retry_exc:
            raise Phase1ParserError(
                "Phase 1 enrichment returned JSON that could not be repaired safely."
            ) from retry_exc

    return Phase1ParseResult(
        deterministic_extraction=deterministic,
        llm_enrichment_payload=payload,
        enriched_analysis=enriched,
        merged_analysis=enriched,
    )


def _run_phase1_enrichment_call(*, client: OpenAI, model: str, prompt: str) -> str:
    try:
        return create_json_response_text(
            client=client,
            model=model,
            input_payload=prompt,
        )
    except RuntimeError as exc:
        raise Phase1ParserError("Phase 1 enrichment returned an empty response.") from exc


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_text)
    except JSONDecodeError as exc:
        raise MalformedPhase1ParserJSONError(
            f"Phase 1 enrichment returned malformed JSON at line {exc.lineno}, column {exc.colno}."
        ) from exc
    if not isinstance(payload, dict):
        raise Phase1ParserError("Phase 1 enrichment must return a top-level JSON object.")
    return payload


def _validate_or_repair_phase1_payload(
    payload: dict[str, Any],
    deterministic,
) -> Any:
    return merge_phase1_deterministic_and_llm(
        deterministic=deterministic,
        llm_payload=payload,
    )


def _condense_validation_errors(exc: ValidationError) -> str:
    errors: list[str] = []
    for issue in exc.errors():
        location = ".".join(str(part) for part in issue.get("loc", []))
        message = issue.get("msg", "invalid value")
        errors.append(f"{location}: {message}")
    return "; ".join(errors[:8])
