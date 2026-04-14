from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytest

pytest.importorskip("sqlalchemy")

from backend.app.models.render_models import (  # noqa: E402
    LatexCompiler,
    RenderFailure,
    RenderFailureSeverity,
    RenderFailureStage,
    RenderOutputStatus,
)
from backend.app.services.document_assembler import assemble_document, build_section_map  # noqa: E402
from backend.app.services.latex_mapper import render_section_fragments  # noqa: E402
from backend.app.services.pdf_compiler import PdflatexExecutionResult, build_compile_result  # noqa: E402
from backend.app.services.render_diagnostics import build_render_diagnostics_payload  # noqa: E402
from backend.app.services.template_registry import get_active_template  # noqa: E402


def test_diagnostics_payload_avoids_raw_stdout_stderr(normal_resume, tmp_path: Path) -> None:
    template = get_active_template()
    assembled = assemble_document(template, build_section_map(render_section_fragments(normal_resume)))
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    tex_path = workspace_path / "resume.tex"
    tex_path.write_text(assembled.tex_content, encoding="utf-8")
    compile_result = build_compile_result(
        render_job_id=normal_resume.render_job_id,
        template_id=template.metadata.template_id,
        workspace=type(
            "Workspace",
            (),
            {
                "render_job_id": normal_resume.render_job_id,
                "workspace_path": str(workspace_path),
            },
        )(),
        tex_file_path=tex_path,
        pdf_file_path=None,
        execution_result=PdflatexExecutionResult(
            return_code=1,
            stdout="raw resume text echoed by latex",
            stderr="! Undefined control sequence",
            elapsed_ms=11,
        ),
    )

    payload = build_render_diagnostics_payload(
        render_job_id=normal_resume.render_job_id,
        template_id=template.metadata.template_id,
        page_policy=normal_resume.target_page_policy,
        compile_result=compile_result,
        assembled_document=assembled,
        render_status=RenderOutputStatus.FAILED,
    )

    assert payload.render_status.value == "failed"
    assert payload.compile_success is False
    assert payload.errors_count >= 1
    assert payload.artifact_references.tex == str(tex_path)
    assert "stdout_summary" not in payload.compile_diagnostics_summary
    assert payload.compile_diagnostics_summary["stdout_available"] is True
    assert payload.compile_diagnostics_summary["errors"][0]["redacted"] is True
    assert payload.placeholder_fill_info["placeholders_filled"]
    assert "raw resume text" not in str(payload.model_dump(mode="json"))


def test_diagnostics_payload_counts_failures_without_content() -> None:
    failure = RenderFailure(
        code="compile-failed",
        message="pdflatex failed at line 10",
        severity=RenderFailureSeverity.ERROR,
        stage=RenderFailureStage.LATEX_COMPILE,
    )

    payload = build_render_diagnostics_payload(
        render_job_id="render-diagnostics-001",
        template_id="ats_standard",
        compile_result=type(
            "CompileResultLike",
            (),
            {
                "success": False,
                "compiler": LatexCompiler.PDFLATEX,
                "exit_code": 1,
                "pdf_artifact": None,
                "log_artifact": None,
                "stdout_excerpt": None,
                "stderr_excerpt": None,
                "warnings": ["LaTeX Warning: x"],
                "failures": [failure],
            },
        )(),
    )

    assert payload.warnings_count == 1
    assert payload.errors_count == 1
    assert payload.compile_diagnostics_summary["failures"][0]["code"] == "compile-failed"
    assert payload.compile_diagnostics_summary["failures"][0]["message"]["redacted"] is True
