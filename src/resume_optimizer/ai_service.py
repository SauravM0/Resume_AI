"""Compatibility wrappers for AI-backed Phase 1 parsing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from .job_models import ParsedJobAnalysisResponse, RawJobDescriptionRequest
from .phase1_legacy_adapter import adapt_phase1_analysis_to_legacy_job_analysis
from .phase1_parser import (
    MalformedPhase1ParserJSONError,
    Phase1ParseResult,
    Phase1ParserError,
    parse_job_description_with_llm_enrichment,
)
from .phase1_role_modeling import compatibility_role_type_value

if TYPE_CHECKING:
    from openai import OpenAI


class JobAnalysisError(RuntimeError):
    """Raised when compatibility Phase 1 parsing cannot produce valid structured data."""


class MalformedJobAnalysisJSONError(JobAnalysisError):
    """Raised when the Phase 1 enrichment parser returns malformed JSON."""


def analyze_job_description(
    job_description_text: str,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> ParsedJobAnalysisResponse:
    """Compatibility wrapper that adapts the rebuilt parser to the legacy raw schema."""

    try:
        parsed = parse_job_description_with_llm_enrichment(
            job_description_text,
            client=client,
            model=model,
        )
    except MalformedPhase1ParserJSONError as exc:
        raise MalformedJobAnalysisJSONError(str(exc)) from exc
    except Phase1ParserError as exc:
        raise JobAnalysisError(str(exc)) from exc

    return adapt_phase1_result_to_legacy_raw_response(parsed)


def parse_job_description(
    job_description_text: str,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> Phase1ParseResult:
    """Public rebuilt Phase 1 parser entrypoint preserving deterministic artifacts."""

    try:
        RawJobDescriptionRequest(job_description_text=job_description_text)
    except ValidationError as exc:
        raise JobAnalysisError(
            "Phase 1 parser requires a non-empty raw job description."
        ) from exc
    try:
        return parse_job_description_with_llm_enrichment(
            job_description_text,
            client=client,
            model=model,
        )
    except Phase1ParserError as exc:
        raise JobAnalysisError(str(exc)) from exc


def adapt_phase1_result_to_legacy_raw_response(
    result: Phase1ParseResult,
) -> ParsedJobAnalysisResponse:
    """Adapt rebuilt Phase 1 output into the legacy raw Phase 1 response schema."""

    merged_analysis = result.merged_analysis or result.enriched_analysis
    legacy = adapt_phase1_analysis_to_legacy_job_analysis(merged_analysis)
    role_type = compatibility_role_type_value(
        functional_role_family=merged_analysis.functional_role_family,
        organizational_role_mode=merged_analysis.organizational_role_mode,
    )
    return ParsedJobAnalysisResponse(
        technical_skills=legacy.technical_skills,
        soft_skills=legacy.soft_skills,
        seniority_level=(
            merged_analysis.seniority_level.value
            if merged_analysis.seniority_level is not None
            else None
        ),
        role_type=role_type,
        industry_domain=merged_analysis.industry_domain,
        key_action_verbs=legacy.key_action_verbs,
        must_have_requirements=legacy.must_have_requirements,
        nice_to_have_requirements=legacy.nice_to_have_requirements,
        company_culture_signals=legacy.company_culture_signals,
    )
