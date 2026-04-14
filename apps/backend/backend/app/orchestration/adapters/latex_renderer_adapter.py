"""Adapter for Phase 5 deterministic LaTeX rendering."""

from __future__ import annotations

from collections.abc import Callable

from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.pipeline_models import (
    RenderDeterministicLatexInput,
    RenderDeterministicLatexOutput,
)
from backend.app.orchestration.types import PipelineArtifactRef
from backend.app.services.render_input_adapter import (
    RenderInputAdapterError,
    build_render_input_from_verified_output,
)
from backend.app.services.render_service import DEFAULT_RENDER_LATEX_SERVICE, RenderLatexService


class LatexRendererAdapter:
    """Wrap verified-output-to-LaTeX rendering services."""

    stage_name = StageName.RENDER_DETERMINISTIC_LATEX

    def __init__(
        self,
        *,
        render_service: RenderLatexService = DEFAULT_RENDER_LATEX_SERVICE,
        render_input_builder: Callable[..., object] = build_render_input_from_verified_output,
    ) -> None:
        self._render_service = render_service
        self._render_input_builder = render_input_builder

    def execute(
        self,
        stage_input: RenderDeterministicLatexInput,
        context: StageExecutionContext,
    ) -> RenderDeterministicLatexOutput:
        """Convert verified Phase 4 output to assembled LaTeX."""

        try:
            render_input = self._render_input_builder(
                source_profile=stage_input.source_profile,
                rendering_output=stage_input.rendering_output,
                template_id=stage_input.template_id,
                render_job_id=stage_input.render_job_id,
            )
            result = self._render_service.render_latex(render_input)
        except RenderInputAdapterError as exc:
            raise StageExecutionError(
                str(exc),
                failure_type=OrchestrationFailureType.RENDER_CONTRACT,
                stage_name=self.stage_name,
            ) from exc
        except Exception as exc:
            raise StageExecutionError(
                f"LaTeX rendering failed: {exc}",
                failure_type=OrchestrationFailureType.LATEX_RENDER,
                stage_name=self.stage_name,
            ) from exc
        return RenderDeterministicLatexOutput(
            render_input=result.render_input,
            assembled_document=result.assembled_document,
            render_output=result.render_output,
        )

    def extract_artifacts(
        self,
        stage_output: RenderDeterministicLatexOutput,
        context: StageExecutionContext,
    ) -> list[PipelineArtifactRef]:
        return []
