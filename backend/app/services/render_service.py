"""Service that composes Phase 5 deterministic LaTeX rendering primitives."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.models.render_models import (
    RenderDiagnostics,
    RenderFailure,
    RenderJobInput,
    RenderJobOutput,
    RenderOutputStatus,
)
from backend.app.services.document_assembler import AssembledDocument, assemble_document, build_section_map
from backend.app.services.latex_mapper import render_section_fragments
from backend.app.services.layout_manager import LayoutPlanResult, manage_layout
from backend.app.services.rendering_contract import (
    validate_display_ready_content,
    validate_required_rendering_prerequisites,
    validate_section_consistency,
)
from backend.app.services.template_registry import load_template


class RenderServiceError(RuntimeError):
    """Raised when deterministic LaTeX rendering cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class RenderLatexServiceResult:
    """LaTeX rendering result before PDF compilation."""

    render_input: RenderJobInput
    layout_plan: LayoutPlanResult
    assembled_document: AssembledDocument
    render_output: RenderJobOutput


class RenderLatexService:
    """Render verified structured resume content into deterministic LaTeX."""

    def render_latex(self, render_input: RenderJobInput) -> RenderLatexServiceResult:
        """Validate, layout, map, and assemble a LaTeX document."""

        failures = [
            *validate_required_rendering_prerequisites(render_input),
            *validate_section_consistency(render_input),
            *validate_display_ready_content(render_input),
        ]
        if failures:
            raise RenderServiceError(_failure_summary(failures))

        layout_plan = manage_layout(render_input)
        adjusted_input = layout_plan.adjusted_render_input
        template = load_template(adjusted_input.template_id)
        section_results = render_section_fragments(adjusted_input)
        assembled = assemble_document(template, build_section_map(section_results))
        render_output = RenderJobOutput(
            render_job_id=adjusted_input.render_job_id,
            status=RenderOutputStatus.PARTIAL,
            success=False,
            generated_tex_content=assembled.tex_content,
            warnings=[*layout_plan.warnings, *assembled.diagnostics.warnings],
            diagnostics=RenderDiagnostics(
                warnings=[*layout_plan.warnings, *assembled.diagnostics.warnings],
                section_stats=[],
                layout_overflow=layout_plan.overflow_remaining,
            ),
            estimated_page_count=None,
        )
        return RenderLatexServiceResult(
            render_input=adjusted_input,
            layout_plan=layout_plan,
            assembled_document=assembled,
            render_output=render_output,
        )


def _failure_summary(failures: list[RenderFailure]) -> str:
    return "; ".join(f"{failure.code}: {failure.message}" for failure in failures)


DEFAULT_RENDER_LATEX_SERVICE = RenderLatexService()
