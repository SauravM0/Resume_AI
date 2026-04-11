# Templates are controlled assets because Phase 5 renders verified content
# deterministically instead of letting an AI reinterpret resume structure.
# Registry validation matters because broken placeholders can drop verified
# content, corrupt provenance alignment, or produce invalid PDFs.
# AI must not mutate template structure in Phase 5; renderer code may only
# insert escaped structured content into validated placeholders.
"""Filesystem-backed registry for controlled LaTeX resume templates.

Templates are treated as controlled assets because Phase 5 must render already
verified content deterministically, without changing the resume structure after
verification. Registry validation matters because a missing or malformed
placeholder can silently drop verified content, corrupt provenance alignment,
or produce a bad PDF. AI is not allowed to mutate template structure in this
phase; later tasks may only insert escaped, structured content into validated
placeholders.
"""

from __future__ import annotations

from backend.app.cache.codecs import deserialize_loaded_template, serialize_model
from backend.app.cache.keys import build_cache_key, stable_code_hash
from backend.app.cache.storage import get_or_compute
from hashlib import sha256
from pathlib import Path
import re

from backend.app.models.render_models import (
    LatexTemplateMetadata,
    LoadedLatexTemplate,
    TemplatePlaceholder,
)

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "latex"
PLACEHOLDER_PATTERN = re.compile(r"^%\s*PLACEHOLDER:\s*([A-Z][A-Z0-9_]*)\s*$")
PLACEHOLDER_LINE_PATTERN = re.compile(r"^\s*%+\s*PLACEHOLDER\b")

REQUIRED_TEMPLATE_PLACEHOLDERS: tuple[TemplatePlaceholder, ...] = (
    TemplatePlaceholder.PERSONAL_INFO,
    TemplatePlaceholder.SUMMARY_SECTION,
    TemplatePlaceholder.EXPERIENCE_SECTION,
    TemplatePlaceholder.PROJECTS_SECTION,
    TemplatePlaceholder.SKILLS_SECTION,
    TemplatePlaceholder.EDUCATION_SECTION,
    TemplatePlaceholder.CERTIFICATIONS_SECTION,
)

_REGISTERED_TEMPLATES: tuple[LatexTemplateMetadata, ...] = (
    LatexTemplateMetadata(
        template_id="ats_standard",
        version="1.0.0",
        display_name="ATS Standard",
        description=(
            "Minimal ATS-safe LaTeX resume template with deterministic section "
            "insertion placeholders."
        ),
        active=True,
        ats_safe=True,
        max_recommended_pages=1,
        filesystem_path=TEMPLATE_ROOT / "ats_standard" / "v1" / "main.tex",
        required_placeholders=list(REQUIRED_TEMPLATE_PLACEHOLDERS),
        optional_placeholders=[],
    ),
)
TEMPLATE_LOAD_CACHE_NAMESPACE = "template_load"
TEMPLATE_LOAD_CACHE_TTL_SECONDS = 24 * 60 * 60


class TemplateRegistryError(ValueError):
    """Raised when template registry metadata or file integrity is invalid."""


def list_templates(*, include_inactive: bool = True) -> list[LatexTemplateMetadata]:
    """Return registered template metadata, optionally filtering inactive entries."""

    templates = list(_REGISTERED_TEMPLATES)
    if include_inactive:
        return templates
    return [template for template in templates if template.active]


def get_active_template() -> LoadedLatexTemplate:
    """Load the single active template, failing if registry state is ambiguous."""

    active_templates = [template for template in _REGISTERED_TEMPLATES if template.active]
    if not active_templates:
        raise TemplateRegistryError("No active LaTeX resume template is registered.")
    if len(active_templates) > 1:
        template_ids = ", ".join(
            f"{template.template_id}@{template.version}" for template in active_templates
        )
        raise TemplateRegistryError(
            "Multiple active LaTeX resume templates are registered: " + template_ids
        )
    active_template = active_templates[0]
    return load_template(active_template.template_id, version=active_template.version)


def load_template(template_id: str, *, version: str | None = None) -> LoadedLatexTemplate:
    """Load and validate template content from the filesystem."""

    metadata = _lookup_template_metadata(template_id=template_id, version=version)
    template_path = metadata.filesystem_path
    checksum = _checksum_content(_read_template_content(metadata))
    cache_key = build_cache_key(
        TEMPLATE_LOAD_CACHE_NAMESPACE,
        {
            "template_id": metadata.template_id,
            "template_version": metadata.version,
            "template_checksum": checksum,
            "registry_code_hash": stable_code_hash(
                load_template,
                validate_template_placeholders,
                _lookup_template_metadata,
            ),
        },
    )
    cached, _ = get_or_compute(
        namespace=TEMPLATE_LOAD_CACHE_NAMESPACE,
        key=cache_key,
        compute=lambda: _load_template_from_disk(metadata),
        serialize=serialize_model,
        deserialize=deserialize_loaded_template,
        ttl_seconds=TEMPLATE_LOAD_CACHE_TTL_SECONDS,
        metadata={"template_id": metadata.template_id, "template_version": metadata.version},
    )
    return cached


def ensure_template_is_renderable(
    template_id: str,
    *,
    version: str | None = None,
) -> LatexTemplateMetadata:
    """Validate that a template can be loaded and rendered, returning metadata."""

    loaded_template = load_template(template_id, version=version)
    return loaded_template.metadata


def validate_template_placeholders(
    template_content: str,
    *,
    required_placeholders: list[TemplatePlaceholder] | None = None,
    optional_placeholders: list[TemplatePlaceholder] | None = None,
) -> list[TemplatePlaceholder]:
    """Validate template placeholder syntax and required placeholder coverage."""

    if not template_content.strip():
        raise TemplateRegistryError("Template content is empty.")

    required = required_placeholders or list(REQUIRED_TEMPLATE_PLACEHOLDERS)
    optional = optional_placeholders or []
    allowed_placeholders = set(required).union(optional)
    discovered: list[TemplatePlaceholder] = []
    malformed_lines: list[str] = []
    unknown_placeholders: list[str] = []

    for line_number, line in enumerate(template_content.splitlines(), start=1):
        if not PLACEHOLDER_LINE_PATTERN.match(line):
            continue

        match = PLACEHOLDER_PATTERN.match(line.strip())
        if match is None:
            malformed_lines.append(f"line {line_number}: {line.strip()}")
            continue

        placeholder_name = match.group(1)
        try:
            placeholder = TemplatePlaceholder(placeholder_name)
        except ValueError:
            unknown_placeholders.append(f"line {line_number}: {placeholder_name}")
            continue

        if placeholder not in allowed_placeholders:
            unknown_placeholders.append(f"line {line_number}: {placeholder_name}")
            continue

        discovered.append(placeholder)

    if malformed_lines:
        raise TemplateRegistryError(
            "Malformed LaTeX template placeholder comments: "
            + "; ".join(malformed_lines)
        )

    if unknown_placeholders:
        raise TemplateRegistryError(
            "Unknown LaTeX template placeholders: " + "; ".join(unknown_placeholders)
        )

    duplicate_placeholders = sorted(
        placeholder.value
        for placeholder in set(discovered)
        if discovered.count(placeholder) > 1
    )
    if duplicate_placeholders:
        raise TemplateRegistryError(
            "Duplicate LaTeX template placeholders: "
            + ", ".join(duplicate_placeholders)
        )

    missing_placeholders = [
        placeholder.value for placeholder in required if placeholder not in discovered
    ]
    if missing_placeholders:
        raise TemplateRegistryError(
            "Missing required LaTeX template placeholders: "
            + ", ".join(missing_placeholders)
        )

    return discovered


def _lookup_template_metadata(
    *,
    template_id: str,
    version: str | None,
) -> LatexTemplateMetadata:
    """Find one registered template by id and optional version."""

    matches = [
        template
        for template in _REGISTERED_TEMPLATES
        if template.template_id == template_id and (version is None or template.version == version)
    ]
    if not matches:
        version_detail = f" version {version}" if version is not None else ""
        raise TemplateRegistryError(
            f"No LaTeX resume template registered for {template_id}{version_detail}."
        )
    if len(matches) > 1:
        versions = ", ".join(template.version for template in matches)
        raise TemplateRegistryError(
            f"Multiple LaTeX resume templates registered for {template_id}: {versions}."
        )
    return matches[0]


def _checksum_content(content: str) -> str:
    """Return a stable SHA-256 checksum for template content."""

    return sha256(content.encode("utf-8")).hexdigest()


def _read_template_content(metadata: LatexTemplateMetadata) -> str:
    template_path = metadata.filesystem_path
    if not template_path.exists():
        raise TemplateRegistryError(
            f"Template file does not exist for {metadata.template_id}@{metadata.version}: "
            f"{template_path}"
        )
    if not template_path.is_file():
        raise TemplateRegistryError(
            f"Template path is not a file for {metadata.template_id}@{metadata.version}: "
            f"{template_path}"
        )
    content = template_path.read_text(encoding="utf-8")
    if not content.strip():
        raise TemplateRegistryError(
            f"Template file is empty for {metadata.template_id}@{metadata.version}: "
            f"{template_path}"
        )
    return content


def _load_template_from_disk(metadata: LatexTemplateMetadata) -> LoadedLatexTemplate:
    content = _read_template_content(metadata)
    discovered_placeholders = validate_template_placeholders(
        content,
        required_placeholders=metadata.required_placeholders,
        optional_placeholders=metadata.optional_placeholders,
    )
    checksum = _checksum_content(content)
    if metadata.checksum_sha256 is not None and metadata.checksum_sha256 != checksum:
        raise TemplateRegistryError(
            f"Template checksum mismatch for {metadata.template_id}@{metadata.version}."
        )
    return LoadedLatexTemplate(
        metadata=metadata.model_copy(update={"checksum_sha256": checksum}),
        content=content,
        discovered_placeholders=discovered_placeholders,
        checksum_sha256=checksum,
    )
