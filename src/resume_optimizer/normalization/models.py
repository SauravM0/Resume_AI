"""Structured outputs for taxonomy-backed normalization."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from ..models import NonEmptyStr, StrictModel


class NormalizationStatus(StrEnum):
    """Normalization confidence class for downstream ranking and diagnostics."""

    EXACT = "exact"
    ALIAS = "alias"
    INFERRED = "inferred"
    PASSTHROUGH = "passthrough"


class NormalizedTerm(StrictModel):
    """Normalized comparable term with traceability back to the raw source text."""

    raw: NonEmptyStr
    canonical: NonEmptyStr
    taxonomy: NonEmptyStr
    status: NormalizationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    matched_by: NonEmptyStr

    @property
    def is_known(self) -> bool:
        """Return whether the term matched a known taxonomy entry."""

        return self.status != NormalizationStatus.PASSTHROUGH


class TitleNormalization(NormalizedTerm):
    """Normalized title plus derived hints for role family, seniority, and role type."""

    role_family: str | None = None
    seniority_hint: str | None = None
    functional_role_family_hint: str | None = None
    organizational_role_mode_hint: str | None = None
    role_type_hint: str | None = None


class EvidenceNormalizationBundle(StrictModel):
    """Deterministic normalized facets extracted from one raw evidence text input."""

    raw_text: NonEmptyStr
    tool_platforms: list[NormalizedTerm] = Field(default_factory=list)
    cloud_services: list[NormalizedTerm] = Field(default_factory=list)
    frameworks_libraries: list[NormalizedTerm] = Field(default_factory=list)
    programming_languages: list[NormalizedTerm] = Field(default_factory=list)
    domains_industries: list[NormalizedTerm] = Field(default_factory=list)
    action_verbs: list[NormalizedTerm] = Field(default_factory=list)
    leadership_phrases: list[NormalizedTerm] = Field(default_factory=list)
    ownership_phrases: list[NormalizedTerm] = Field(default_factory=list)
    delivery_scope_phrases: list[NormalizedTerm] = Field(default_factory=list)
    stakeholder_phrases: list[NormalizedTerm] = Field(default_factory=list)
    title: TitleNormalization | None = None
