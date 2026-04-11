"""Load static normalization taxonomies from JSON config files."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from .models import StrictModel

_TAXONOMY_DIR = Path(__file__).resolve().parent.parent / "config" / "taxonomy"


class TaxonomyConfig(StrictModel):
    """Single taxonomy config mapping canonical terms to known aliases."""

    canonical_terms: dict[str, list[str]]


class TitleTaxonomyConfig(StrictModel):
    """Title taxonomy config with aliases, canonical mappings, and derived hints."""

    aliases: dict[str, str]
    canonical_titles: dict[str, list[str]]
    role_family_hints: dict[str, str]


@lru_cache(maxsize=None)
def load_taxonomy(name: str) -> TaxonomyConfig:
    """Load a reusable taxonomy config by name."""

    payload = json.loads((_TAXONOMY_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return TaxonomyConfig.model_validate(payload)


@lru_cache(maxsize=1)
def load_title_taxonomy() -> TitleTaxonomyConfig:
    """Load the title normalization config."""

    payload = json.loads((_TAXONOMY_DIR / "titles.json").read_text(encoding="utf-8"))
    return TitleTaxonomyConfig.model_validate(payload)
