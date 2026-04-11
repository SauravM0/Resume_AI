"""Loader for Phase 7 evaluation packs from YAML or JSON.

Supports:
- YAML and JSON input formats
- Template inheritance for reusable case components
- Validation of required fields and malformed cases
- Relative path resolution for profile references
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .case_models import (
    EvaluationCase,
    EvaluationManifest,
    EvaluationPack,
)


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def load_evaluation_pack(path: str | Path) -> EvaluationPack:
    """Load a single evaluation pack from YAML or JSON file.

    Args:
        path: Path to the pack file (.yaml, .yml, or .json)

    Returns:
        Parsed EvaluationPack with template inheritance resolved.
    """
    path = Path(path)
    content = _load_file_content(path)
    data = _parse_content(content, path)

    pack = EvaluationPack.model_validate(data)
    pack = _resolve_template_inheritance(pack)
    _validate_case_paths(pack, path.parent)

    return pack


def load_evaluation_manifest(path: str | Path) -> EvaluationManifest:
    """Load the evaluation manifest referencing all packs.

    Args:
        path: Path to the manifest file.
    """
    path = Path(path)
    content = _load_file_content(path)
    data = _parse_content(content, path)

    return EvaluationManifest.model_validate(data)


def load_all_packs(base_dir: str | Path) -> list[EvaluationPack]:
    """Load all evaluation packs from a base directory.

    Scans for yaml/yml/json files and loads each as a pack.

    Args:
        base_dir: Directory containing pack files.

    Returns:
        List of all loaded packs.
    """
    base_dir = Path(base_dir)
    packs: list[EvaluationPack] = []

    for pattern in ["*.yaml", "*.yml", "*.json"]:
        for path in base_dir.glob(pattern):
            if path.name.startswith("."):
                continue
            try:
                pack = load_evaluation_pack(path)
                packs.append(pack)
            except Exception as e:
                raise RuntimeError(f"Failed to load pack {path}: {e}") from e

    return packs


def _load_file_content(path: Path) -> str:
    """Read file content with proper encoding."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Evaluation pack not found: {path}")
    except OSError as e:
        raise OSError(f"Failed to read {path}: {e}") from e


def _parse_content(content: str, path: Path) -> dict[str, Any]:
    """Parse YAML or JSON content into a dict."""
    suffix = path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        try:
            return yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}") from e
    elif suffix == ".json":
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {e}") from e
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts, with override taking precedence."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def _resolve_template_inheritance(pack: EvaluationPack) -> EvaluationPack:
    """Resolve template inheritance for cases.

    This supports YAML anchor/alias natively. For explicit template references,
    cases can define a _template_ref field that references a template name.
    """
    if not pack.templates:
        return pack

    templates = pack.templates
    resolved_cases = []

    for case in pack.cases:
        case_dict = case.model_dump(exclude_none=True)
        template_name = case_dict.pop("_template_ref", None)

        if template_name:
            if template_name not in templates:
                raise ValidationError(
                    f"Template '{template_name}' not found in pack '{pack.pack_id}'"
                )
            base_template = templates[template_name].copy()
            merged = _deep_merge(base_template, case_dict)
            resolved_case = EvaluationCase.model_validate(merged)
            resolved_cases.append(resolved_case)
        else:
            resolved_cases.append(case)

    return EvaluationPack(
        pack_id=pack.pack_id,
        pack_type=pack.pack_type,
        description=pack.description,
        version=pack.version,
        templates=pack.templates,
        cases=resolved_cases,
    )


def _validate_case_paths(pack: EvaluationPack, base_dir: Path) -> None:
    """Validate that profile reference paths resolve correctly."""
    for case in pack.cases:
        if case.profile is not None:
            profile_path = base_dir / case.profile.path
            if not profile_path.exists():
                raise ValidationError(
                    f"Case '{case.case_id}' references profile '{case.profile.path}' "
                    f"which does not exist (resolved from {base_dir})"
                )


def validate_case(case: EvaluationCase) -> tuple[bool, list[str]]:
    """Validate a single evaluation case.

    Args:
        case: The evaluation case to validate.

    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors: list[str] = []

    if not case.case_id:
        errors.append("case_id is required")

    if not case.description:
        errors.append("description is required")

    if not case.pack_type:
        errors.append("pack_type is required")
    elif case.pack_type not in ("jd_parse", "selection", "end_to_end", "red_team"):
        errors.append(f"Invalid pack_type: {case.pack_type}")

    if case.pack_type in ("jd_parse", "end_to_end"):
        if case.job_description is None:
            errors.append("job_description is required for this pack type")

    if case.pack_type in ("selection", "end_to_end"):
        if case.profile is None:
            errors.append("profile is required for this pack type")

    if case.tags:
        for tag in case.tags:
            if not tag or len(tag.strip()) == 0:
                errors.append(f"Empty tag in case '{case.case_id}'")

    return (len(errors) == 0, errors)


def validate_pack(pack: EvaluationPack) -> tuple[bool, list[str]]:
    """Validate an entire evaluation pack.

    Args:
        pack: The evaluation pack to validate.

    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors: list[str] = []

    if not pack.pack_id:
        errors.append("pack_id is required")

    if not pack.cases:
        errors.append(f"Pack '{pack.pack_id}' has no cases")

    seen_case_ids: set[str] = set()
    for case in pack.cases:
        case_valid, case_errors = validate_case(case)
        if not case_valid:
            for err in case_errors:
                errors.append(f"Case '{case.case_id}': {err}")

        if case.case_id in seen_case_ids:
            errors.append(f"Duplicate case_id: {case.case_id}")
        seen_case_ids.add(case.case_id)

    return (len(errors) == 0, errors)


def get_case_summary(case: EvaluationCase) -> str:
    """Get a human-readable summary of a case."""
    lines = [
        f"Case: {case.case_id}",
        f"Description: {case.description}",
        f"Pack Type: {case.pack_type}",
    ]

    if case.tags:
        lines.append(f"Tags: {', '.join(case.tags)}")

    return "\n".join(lines)
