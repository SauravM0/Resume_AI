"""Deterministic Phase 2 candidate evidence extraction service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import Field

from ..evidence_builder import build_candidate_evidence_graph, build_canonical_evidence_units
from ..evidence_models import CandidateEvidenceGraph, CanonicalEvidenceUnit, EvidenceSourceType
from ..models import MasterProfile, StableId, StrictModel


class CandidateEvidenceExtractor(Protocol):
    """Stable interface for deterministic candidate-evidence extraction backends."""

    def extract(self, profile: MasterProfile) -> CandidateEvidenceGraph:
        """Return a typed evidence graph derived from the normalized source profile."""


class DefaultCandidateEvidenceExtractor:
    """Default deterministic extractor backed by the core evidence builder."""

    def extract(self, profile: MasterProfile) -> CandidateEvidenceGraph:
        return build_candidate_evidence_graph(profile)


class CandidateEvidenceExtractionSummary(StrictModel):
    """Small extraction summary for tests, diagnostics, and future instrumentation."""

    candidate_profile_id: StableId
    total_evidence_units: int = Field(default=0, ge=0)
    experience_evidence_count: int = Field(default=0, ge=0)
    project_evidence_count: int = Field(default=0, ge=0)
    education_evidence_count: int = Field(default=0, ge=0)
    certification_evidence_count: int = Field(default=0, ge=0)
    award_evidence_count: int = Field(default=0, ge=0)
    skill_declaration_count: int = Field(default=0, ge=0)
    personal_summary_count: int = Field(default=0, ge=0)


@dataclass(frozen=True, slots=True)
class CandidateEvidenceExtractionResult:
    """Full extraction result bundle for Phase 2 inputs and tests."""

    source_profile: MasterProfile
    evidence_graph: CandidateEvidenceGraph
    ranking_compatible_evidence: list[CanonicalEvidenceUnit]
    summary: CandidateEvidenceExtractionSummary


@dataclass(slots=True)
class CandidateEvidenceExtractionService:
    """Service facade that extracts typed evidence without mutating source truth."""

    extractor: CandidateEvidenceExtractor = field(default_factory=DefaultCandidateEvidenceExtractor)

    def extract(self, source_profile: MasterProfile) -> CandidateEvidenceExtractionResult:
        graph = self.extractor.extract(source_profile)
        return CandidateEvidenceExtractionResult(
            source_profile=source_profile,
            evidence_graph=graph,
            ranking_compatible_evidence=build_canonical_evidence_units(source_profile),
            summary=_build_summary(graph),
        )


def _build_summary(graph: CandidateEvidenceGraph) -> CandidateEvidenceExtractionSummary:
    counts = {source_type: 0 for source_type in EvidenceSourceType}
    for unit in graph.evidence_units:
        counts[unit.source_type] += 1
    return CandidateEvidenceExtractionSummary(
        candidate_profile_id=graph.candidate_profile_id,
        total_evidence_units=len(graph.evidence_units),
        experience_evidence_count=counts[EvidenceSourceType.EXPERIENCE_BULLET]
        + counts[EvidenceSourceType.EXPERIENCE_SUMMARY],
        project_evidence_count=counts[EvidenceSourceType.PROJECT_BULLET]
        + counts[EvidenceSourceType.PROJECT_SUMMARY],
        education_evidence_count=counts[EvidenceSourceType.EDUCATION_ACHIEVEMENT],
        certification_evidence_count=counts[EvidenceSourceType.CERTIFICATION],
        award_evidence_count=counts[EvidenceSourceType.AWARD],
        skill_declaration_count=counts[EvidenceSourceType.SKILL_DECLARATION],
        personal_summary_count=counts[EvidenceSourceType.PERSONAL_SUMMARY],
    )


DEFAULT_CANDIDATE_EVIDENCE_EXTRACTION_SERVICE = CandidateEvidenceExtractionService()
