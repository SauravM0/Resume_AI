"""Adapter for Phase 1 job parsing and normalization."""

from __future__ import annotations

from collections.abc import Callable

from backend.app.cache.codecs import deserialize_parse_job_description_output, serialize_model
from backend.app.cache.keys import build_cache_key, stable_code_hash, stable_text_hash
from backend.app.cache.storage import get_or_compute
from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.adapters.phase1_contract_adapter import (
    build_parse_job_description_output,
)
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.pipeline_models import ParseJobDescriptionInput, ParseJobDescriptionOutput
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.ai_service import JobAnalysisError, parse_job_description
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.phase1_models import Phase1ParseResult

PARSE_JOB_CACHE_NAMESPACE = "parse_job_description"
PARSE_JOB_CACHE_TTL_SECONDS = 12 * 60 * 60


class JobParserAdapter:
    """Wrap existing Phase 1 job analysis modules."""

    stage_name = StageName.PARSE_JOB_DESCRIPTION

    def __init__(
        self,
        *,
        parse_func: Callable[[str], Phase1ParseResult] = parse_job_description,
    ) -> None:
        self._parse_func = parse_func

    def execute(
        self,
        stage_input: ParseJobDescriptionInput,
        context: StageExecutionContext,
    ) -> ParseJobDescriptionOutput:
        """Parse raw JD text and normalize it to the Phase 1 contract."""

        cache_key = build_cache_key(
            PARSE_JOB_CACHE_NAMESPACE,
            {
                "job_description_hash": stable_text_hash(stage_input.request.job_description_text),
                "parser_config_hash": stable_text_hash(DEFAULT_SETTINGS.phase1_job_analysis_model),
                "parser_code_hash": stable_code_hash(self._parse_func, build_parse_job_description_output),
            },
        )
        try:
            cached, _ = get_or_compute(
                namespace=PARSE_JOB_CACHE_NAMESPACE,
                key=cache_key,
                compute=lambda: build_parse_job_description_output(
                    self._parse_func(stage_input.request.job_description_text)
                ),
                serialize=serialize_model,
                deserialize=deserialize_parse_job_description_output,
                ttl_seconds=PARSE_JOB_CACHE_TTL_SECONDS,
                metadata={"stage_name": self.stage_name.value},
            )
            return cached
        except JobAnalysisError as exc:
            raise StageExecutionError(
                str(exc),
                failure_type=OrchestrationFailureType.JOB_DESCRIPTION_PARSE,
                stage_name=self.stage_name,
                retryable=True,
                http_status_code=502,
            ) from exc
        except Exception as exc:
            raise StageExecutionError(
                f"job description parsing failed: {exc}",
                failure_type=OrchestrationFailureType.JOB_DESCRIPTION_PARSE,
                stage_name=self.stage_name,
                retryable=True,
                http_status_code=502,
            ) from exc

    def extract_artifacts(
        self,
        stage_output: ParseJobDescriptionOutput,
        context: StageExecutionContext,
    ) -> list[PipelineArtifactRef]:
        return []
