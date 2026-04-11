"""Explicit adapters between rebuilt Phase 1 output and pipeline contracts."""

from __future__ import annotations

from backend.app.orchestration.pipeline_models import ParseJobDescriptionOutput
from resume_optimizer.ai_service import adapt_phase1_result_to_legacy_raw_response
from resume_optimizer.phase1_legacy_adapter import (
    adapt_phase1_analysis_to_legacy_job_analysis,
)
from resume_optimizer.phase1_models import Phase1ParseResult


def build_parse_job_description_output(
    result: Phase1ParseResult,
) -> ParseJobDescriptionOutput:
    """Project rebuilt Phase 1 output into the pipeline's dual rich+legacy contract."""

    merged_analysis = result.merged_analysis or result.enriched_analysis
    return ParseJobDescriptionOutput(
        raw_analysis=adapt_phase1_result_to_legacy_raw_response(result),
        normalized_analysis=adapt_phase1_analysis_to_legacy_job_analysis(merged_analysis),
        phase1_result=result,
        deterministic_extraction=result.deterministic_extraction,
        llm_enrichment_payload=result.llm_enrichment_payload,
        final_analysis=merged_analysis,
    )
