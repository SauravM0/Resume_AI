"""Registry and dispatcher for Phase 6 stage adapters."""

from __future__ import annotations

from backend.app.orchestration.adapters.base import StageAdapter, StageExecutionContext
from backend.app.orchestration.adapters.generator_adapter import GeneratorAdapter
from backend.app.orchestration.adapters.job_parser_adapter import JobParserAdapter
from backend.app.orchestration.adapters.latex_renderer_adapter import LatexRendererAdapter
from backend.app.orchestration.adapters.pdf_compile_adapter import PdfCompileAdapter
from backend.app.orchestration.adapters.ranker_adapter import RankerAdapter
from backend.app.orchestration.adapters.verifier_adapter import VerifierAdapter
from backend.app.orchestration.enums import StageName


class StageRegistry:
    """Simple dispatcher for standard stage adapter execution."""

    def __init__(self, adapters: list[StageAdapter] | None = None) -> None:
        default_adapters: list[StageAdapter] = [
            JobParserAdapter(),
            RankerAdapter(),
            GeneratorAdapter(),
            VerifierAdapter(),
            LatexRendererAdapter(),
            PdfCompileAdapter(),
        ]
        self._adapters = {
            adapter.stage_name: adapter
            for adapter in (adapters or default_adapters)
        }

    def get(self, stage_name: StageName) -> StageAdapter:
        """Return the registered adapter for a stage."""

        try:
            return self._adapters[stage_name]
        except KeyError as exc:
            raise ValueError(f"no adapter registered for stage: {stage_name.value}") from exc

    def execute(self, stage_name: StageName, stage_input, context: StageExecutionContext):
        """Execute a registered adapter with the standard adapter signature."""

        return self.get(stage_name).execute(stage_input, context)

    @property
    def stage_names(self) -> list[StageName]:
        """Return registered stage names in insertion order."""

        return list(self._adapters)


DEFAULT_STAGE_REGISTRY = StageRegistry()
