from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.models.render_models import TemplatePlaceholder  # noqa: E402
from backend.app.services.document_assembler import (  # noqa: E402
    DocumentAssemblyError,
    assemble_document,
    build_section_map,
)
from backend.app.services.latex_mapper import render_section_fragments  # noqa: E402
from backend.app.services.pdf_compiler import (  # noqa: E402
    WorkspaceCleanupPolicy,
    compile_tex_document,
)
from backend.app.services.template_registry import get_active_template  # noqa: E402


def test_document_assembly_replaces_all_required_placeholders(normal_resume) -> None:
    template = get_active_template()
    section_map = build_section_map(render_section_fragments(normal_resume))

    assembled = assemble_document(template, section_map)

    assert "% PLACEHOLDER:" not in assembled.tex_content
    assert "\\documentclass" in assembled.tex_content
    assert "\\end{document}" in assembled.tex_content
    assert "Ada Lovelace" in assembled.tex_content
    assert TemplatePlaceholder.PERSONAL_INFO in assembled.diagnostics.placeholders_filled


def test_document_assembly_rejects_placeholder_leakage(normal_resume) -> None:
    template = get_active_template()
    section_map = build_section_map(render_section_fragments(normal_resume))
    section_map[TemplatePlaceholder.SUMMARY_SECTION] = "% PLACEHOLDER: PERSONAL_INFO\n"

    with pytest.raises(DocumentAssemblyError, match="placeholder markers"):
        assemble_document(template, section_map)


def test_document_assembly_records_omitted_empty_sections(empty_optional_resume) -> None:
    template = get_active_template()
    section_map = build_section_map(render_section_fragments(empty_optional_resume))

    assembled = assemble_document(template, section_map)

    assert TemplatePlaceholder.PROJECTS_SECTION in assembled.diagnostics.sections_omitted
    assert TemplatePlaceholder.CERTIFICATIONS_SECTION in assembled.diagnostics.sections_omitted
    assert "% PLACEHOLDER:" not in assembled.tex_content


@pytest.mark.latex
def test_pdf_compile_succeeds_for_known_good_fixture(normal_resume, tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")

    template = get_active_template()
    assembled = assemble_document(template, build_section_map(render_section_fragments(normal_resume)))

    result = compile_tex_document(
        tex_content=assembled.tex_content,
        render_job_id=normal_resume.render_job_id,
        template_id=template.metadata.template_id,
        workspace_root=tmp_path,
        cleanup_policy=WorkspaceCleanupPolicy.CLEAN_ALWAYS,
    )

    assert result.compile_success is True
    assert result.compile_result.success is True
    assert result.pdf_file_path is not None


@pytest.mark.latex
def test_pdf_compile_failure_reports_structured_error(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")

    result = compile_tex_document(
        tex_content="\\documentclass{article}\\begin{document}\\badcommand\\end{document}",
        render_job_id="render-bad-latex-001",
        template_id="ats_standard",
        workspace_root=tmp_path,
        cleanup_policy=WorkspaceCleanupPolicy.CLEAN_ALWAYS,
    )

    assert result.compile_success is False
    assert result.compile_result.success is False
    assert result.compile_result.failures
    assert result.compile_result.failures[0].stage.value == "latex_compile"
