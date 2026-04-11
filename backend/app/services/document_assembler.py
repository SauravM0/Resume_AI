# Assembly is separated from mapping, sanitization, and compilation so each
# phase has one responsibility: mappers create section fragments, sanitizers
# make text safe, this layer inserts fragments into validated template slots,
# and compilers produce artifacts later. Placeholder replacement must be tightly
# controlled because blind substitution can corrupt template structure or allow
# accidental template directives inside content. This layer is critical for
# preserving template integrity: only known placeholders are replaced, every
# required slot is accounted for, and leaked placeholder markers are rejected
# before LaTeX compilation.
"""Deterministic LaTeX document assembly for Phase 5 rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
import re

from pydantic import Field, model_validator

from backend.app.models.render_models import (
    LoadedLatexTemplate,
    TemplatePlaceholder,
)
from backend.app.services.latex_mapper import SectionRenderResult
from backend.app.services.template_registry import PLACEHOLDER_PATTERN
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel

PLACEHOLDER_LINE_PATTERN = re.compile(r"^\s*%+\s*PLACEHOLDER\b")


class AssemblyWarningCode(StrEnum):
    """Stable diagnostic warning codes emitted by document assembly."""

    OPTIONAL_SECTION_OMITTED = "optional_section_omitted"
    EMPTY_REQUIRED_SECTION = "empty_required_section"


class DocumentAssemblyError(ValueError):
    """Raised when deterministic document assembly integrity checks fail."""


class SectionInsertionDiagnostics(StrictModel):
    """Diagnostics describing placeholder insertion results."""

    template_id: StableId
    template_version: NonEmptyStr
    placeholders_filled: list[TemplatePlaceholder] = Field(default_factory=list)
    sections_omitted: list[TemplatePlaceholder] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)


class AssembledDocument(StrictModel):
    """Final assembled .tex document plus insertion diagnostics."""

    template_id: StableId
    template_version: NonEmptyStr
    tex_content: NonEmptyStr
    diagnostics: SectionInsertionDiagnostics

    @model_validator(mode="after")
    def validate_template_identity(self) -> "AssembledDocument":
        """Keep top-level metadata aligned with nested diagnostics."""

        if self.template_id != self.diagnostics.template_id:
            raise ValueError("template_id must match diagnostics.template_id")
        if self.template_version != self.diagnostics.template_version:
            raise ValueError("template_version must match diagnostics.template_version")
        return self


__all__ = [
    "AssembledDocument",
    "AssemblyWarningCode",
    "DocumentAssemblyError",
    "SectionInsertionDiagnostics",
    "assemble_document",
    "build_section_map",
    "replace_placeholders",
    "validate_assembled_document",
]


def assemble_document(
    template: LoadedLatexTemplate,
    section_fragments: Mapping[TemplatePlaceholder | str, str],
) -> AssembledDocument:
    """Assemble a final .tex document from a loaded template and fragments."""

    normalized_section_map = _normalize_section_map(section_fragments)
    complete_section_map, warnings, omitted = _apply_missing_section_fallbacks(
        template,
        normalized_section_map,
    )
    tex_content, filled = replace_placeholders(template, complete_section_map)
    validate_assembled_document(template, tex_content)

    diagnostics = SectionInsertionDiagnostics(
        template_id=template.metadata.template_id,
        template_version=template.metadata.version,
        placeholders_filled=filled,
        sections_omitted=omitted,
        warnings=warnings,
    )
    return AssembledDocument(
        template_id=template.metadata.template_id,
        template_version=template.metadata.version,
        tex_content=tex_content,
        diagnostics=diagnostics,
    )


def build_section_map(
    section_results: Sequence[SectionRenderResult],
) -> dict[TemplatePlaceholder, str]:
    """Build a placeholder map from mapper section render results."""

    section_map: dict[TemplatePlaceholder, str] = {}
    duplicate_placeholders: list[str] = []

    for result in section_results:
        if result.placeholder in section_map:
            duplicate_placeholders.append(result.placeholder.value)
            continue
        section_map[result.placeholder] = result.content

    if duplicate_placeholders:
        raise DocumentAssemblyError(
            "Duplicate section placeholder fragments: "
            + ", ".join(sorted(duplicate_placeholders))
        )

    return section_map


def replace_placeholders(
    template: LoadedLatexTemplate,
    section_fragments: Mapping[TemplatePlaceholder | str, str],
) -> tuple[str, list[TemplatePlaceholder]]:
    """Replace only known placeholders in template content."""

    normalized_section_map = _normalize_section_map(section_fragments)
    _validate_template_placeholder_integrity(template)
    _validate_fragment_integrity(normalized_section_map)

    output_lines: list[str] = []
    placeholders_filled: list[TemplatePlaceholder] = []

    for line_number, line in enumerate(template.content.splitlines(), start=1):
        if not PLACEHOLDER_LINE_PATTERN.match(line):
            output_lines.append(line)
            continue

        match = PLACEHOLDER_PATTERN.match(line.strip())
        if match is None:
            raise DocumentAssemblyError(
                f"Malformed template placeholder at line {line_number}: {line.strip()}"
            )

        placeholder = _placeholder_from_name(match.group(1))
        if placeholder not in _allowed_placeholders(template):
            raise DocumentAssemblyError(
                f"Template contains unregistered placeholder: {placeholder.value}"
            )

        fragment = normalized_section_map.get(placeholder)
        if fragment is None:
            raise DocumentAssemblyError(
                f"No fragment provided for template placeholder: {placeholder.value}"
            )

        if fragment:
            output_lines.extend(fragment.rstrip("\n").splitlines())
            placeholders_filled.append(placeholder)

    assembled = "\n".join(output_lines)
    if template.content.endswith("\n"):
        assembled += "\n"
    return assembled, placeholders_filled


def validate_assembled_document(
    template: LoadedLatexTemplate,
    tex_content: str,
) -> None:
    """Run pre-compile integrity checks on assembled .tex content."""

    if not tex_content.strip():
        raise DocumentAssemblyError("Assembled LaTeX document is empty.")

    leaked_placeholders = _discover_placeholder_names(tex_content)
    if leaked_placeholders:
        raise DocumentAssemblyError(
            "Assembled document still contains placeholder markers: "
            + ", ".join(sorted(leaked_placeholders))
        )

    for placeholder in template.metadata.required_placeholders:
        marker = _placeholder_marker(placeholder)
        if marker in tex_content:
            raise DocumentAssemblyError(
                f"Required placeholder was not replaced: {placeholder.value}"
            )


def _apply_missing_section_fallbacks(
    template: LoadedLatexTemplate,
    section_map: dict[TemplatePlaceholder, str],
) -> tuple[dict[TemplatePlaceholder, str], list[str], list[TemplatePlaceholder]]:
    """Fill omitted optional slots with empty fragments and warn on empty required."""

    complete = dict(section_map)
    warnings: list[str] = []
    omitted: list[TemplatePlaceholder] = []

    for placeholder in template.metadata.required_placeholders:
        if placeholder not in complete:
            complete[placeholder] = ""
            omitted.append(placeholder)
            warnings.append(
                f"Required placeholder {placeholder.value} received an empty fragment."
            )
        elif not complete[placeholder].strip():
            omitted.append(placeholder)
            warnings.append(
                f"Required placeholder {placeholder.value} was filled with empty content."
            )

    for placeholder in template.metadata.optional_placeholders:
        if placeholder not in complete:
            complete[placeholder] = ""
            omitted.append(placeholder)
            warnings.append(
                f"Optional placeholder {placeholder.value} omitted with empty content."
            )

    return complete, warnings, omitted


def _normalize_section_map(
    section_fragments: Mapping[TemplatePlaceholder | str, str],
) -> dict[TemplatePlaceholder, str]:
    """Validate and normalize a placeholder fragment map."""

    normalized: dict[TemplatePlaceholder, str] = {}
    for raw_placeholder, fragment in section_fragments.items():
        placeholder = _coerce_placeholder(raw_placeholder)
        if not isinstance(fragment, str):
            raise DocumentAssemblyError(
                f"Fragment for {placeholder.value} must be a string."
            )
        if placeholder in normalized:
            raise DocumentAssemblyError(
                f"Duplicate placeholder fragment provided: {placeholder.value}"
            )
        normalized[placeholder] = fragment
    return normalized


def _validate_template_placeholder_integrity(template: LoadedLatexTemplate) -> None:
    """Validate required placeholder presence and duplicates in template content."""

    if not template.content.strip():
        raise DocumentAssemblyError("Template content is empty.")

    discovered = _discover_placeholders(template.content)
    duplicate_placeholders = sorted(
        placeholder.value
        for placeholder in set(discovered)
        if discovered.count(placeholder) > 1
    )
    if duplicate_placeholders:
        raise DocumentAssemblyError(
            "Template contains duplicate placeholder markers: "
            + ", ".join(duplicate_placeholders)
        )

    missing_required = [
        placeholder.value
        for placeholder in template.metadata.required_placeholders
        if placeholder not in discovered
    ]
    if missing_required:
        raise DocumentAssemblyError(
            "Template is missing required placeholders: "
            + ", ".join(missing_required)
        )


def _validate_fragment_integrity(
    section_map: Mapping[TemplatePlaceholder, str],
) -> None:
    """Reject placeholder marker injection inside section fragments."""

    leaked_fragments = [
        placeholder.value
        for placeholder, fragment in section_map.items()
        if _discover_placeholder_names(fragment)
    ]
    if leaked_fragments:
        raise DocumentAssemblyError(
            "Section fragments contain placeholder markers: "
            + ", ".join(sorted(leaked_fragments))
        )


def _discover_placeholders(content: str) -> list[TemplatePlaceholder]:
    """Return known placeholders discovered in template content."""

    placeholders: list[TemplatePlaceholder] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not PLACEHOLDER_LINE_PATTERN.match(line):
            continue
        match = PLACEHOLDER_PATTERN.match(line.strip())
        if match is None:
            raise DocumentAssemblyError(
                f"Malformed placeholder marker at line {line_number}: {line.strip()}"
            )
        placeholders.append(_placeholder_from_name(match.group(1)))
    return placeholders


def _discover_placeholder_names(content: str) -> list[str]:
    """Return placeholder names that appear in content."""

    names: list[str] = []
    for line in content.splitlines():
        if not PLACEHOLDER_LINE_PATTERN.match(line):
            continue
        match = PLACEHOLDER_PATTERN.match(line.strip())
        if match is None:
            names.append(line.strip())
            continue
        names.append(match.group(1))
    return names


def _coerce_placeholder(placeholder: TemplatePlaceholder | str) -> TemplatePlaceholder:
    """Coerce a known placeholder enum or name into TemplatePlaceholder."""

    if isinstance(placeholder, TemplatePlaceholder):
        return placeholder
    return _placeholder_from_name(placeholder)


def _placeholder_from_name(name: str) -> TemplatePlaceholder:
    """Parse a placeholder name and reject unknown values clearly."""

    try:
        return TemplatePlaceholder(name)
    except ValueError as exc:
        raise DocumentAssemblyError(f"Unknown placeholder name: {name}") from exc


def _allowed_placeholders(template: LoadedLatexTemplate) -> set[TemplatePlaceholder]:
    """Return the allowed placeholder set for a loaded template."""

    return set(template.metadata.required_placeholders).union(
        template.metadata.optional_placeholders
    )


def _placeholder_marker(placeholder: TemplatePlaceholder) -> str:
    """Return the canonical placeholder marker used by controlled templates."""

    return f"% PLACEHOLDER: {placeholder.value}"
