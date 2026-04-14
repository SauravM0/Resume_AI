"""Adapter for Phase 3 structured resume generation."""

from __future__ import annotations

from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.pipeline_models import (
    GenerateStructuredContentInput,
    GenerateStructuredContentOutput,
)
from backend.app.orchestration.types import PipelineArtifactRef
from resume_optimizer.phase3_generation_service import Phase3GenerationError
from resume_optimizer.services.phase3_service import DEFAULT_PHASE3_SERVICE, Phase3Service


class GeneratorAdapter:
    """Wrap Phase 3 service without changing prompt behavior."""

    stage_name = StageName.GENERATE_STRUCTURED_CONTENT

    def __init__(self, *, phase3_service: Phase3Service = DEFAULT_PHASE3_SERVICE) -> None:
        self._phase3_service = phase3_service

    def execute(
        self,
        stage_input: GenerateStructuredContentInput,
        context: StageExecutionContext,
    ) -> GenerateStructuredContentOutput:
        """Generate structured resume content from Phase 2 artifacts."""

        try:
            result = self._phase3_service.run(
                stage_input.job_analysis,
                phase1_final_analysis=getattr(stage_input, "phase1_final_analysis", None),
                phase2_selection=stage_input.phase2_selection,
                phase2_ranking=stage_input.phase2_ranking,
                source_profile=stage_input.source_profile,
                generation_preferences=stage_input.generation_preferences,
            )
        except Phase3GenerationError as exc:
            raise StageExecutionError(
                str(exc),
                failure_type=OrchestrationFailureType.GENERATION_PROVIDER,
                stage_name=self.stage_name,
                retryable=True,
                fallback_eligible=True,
                http_status_code=502,
            ) from exc
        except Exception as exc:
            raise StageExecutionError(
                f"structured generation failed: {exc}",
                failure_type=OrchestrationFailureType.GENERATION_SCHEMA,
                stage_name=self.stage_name,
                retryable=True,
                fallback_eligible=True,
                http_status_code=502,
            ) from exc
        return GenerateStructuredContentOutput(
            request=result.request,
            generation_payload=result.generation_payload,
            section_plan=result.section_plan,
            phase3_result=result.phase3_result,
            validation_report=result.validation_report,
            bounded_generation_context=result.bounded_generation_context,
            bounded_generation_artifacts=result.bounded_generation_artifacts,
        )

    def extract_artifacts(
        self,
        stage_output: GenerateStructuredContentOutput,
        context: StageExecutionContext,
    ) -> list[PipelineArtifactRef]:
        return []
