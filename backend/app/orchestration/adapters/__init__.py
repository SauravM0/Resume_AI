"""Stage adapters for calling existing Phase 1-5 modules through one interface."""

from backend.app.orchestration.adapters.base import StageAdapter, StageExecutionContext
from backend.app.orchestration.adapters.generator_adapter import GeneratorAdapter
from backend.app.orchestration.adapters.job_parser_adapter import JobParserAdapter
from backend.app.orchestration.adapters.latex_renderer_adapter import LatexRendererAdapter
from backend.app.orchestration.adapters.pdf_compile_adapter import PdfCompileAdapter
from backend.app.orchestration.adapters.ranker_adapter import RankerAdapter
from backend.app.orchestration.adapters.verifier_adapter import VerifierAdapter

__all__ = [
    "GeneratorAdapter",
    "JobParserAdapter",
    "LatexRendererAdapter",
    "PdfCompileAdapter",
    "RankerAdapter",
    "StageAdapter",
    "StageExecutionContext",
    "VerifierAdapter",
]
