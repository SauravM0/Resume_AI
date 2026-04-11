"""Thin adapters from current source-profile models into evidence extraction outputs."""

from __future__ import annotations

from .evidence_builder import build_candidate_evidence_graph, build_canonical_evidence_units
from .evidence_models import CandidateEvidenceGraph, CanonicalEvidenceUnit
from .models import MasterProfile
from .phase2_artifacts import Phase2CandidateArtifacts, build_phase2_candidate_artifacts


def adapt_master_profile_to_evidence_graph(source_profile: MasterProfile) -> CandidateEvidenceGraph:
    """Project a normalized master profile into the typed candidate evidence graph."""

    return build_candidate_evidence_graph(source_profile)


def adapt_master_profile_to_ranking_evidence(
    source_profile: MasterProfile,
) -> list[CanonicalEvidenceUnit]:
    """Project a normalized master profile into the current ranking-compatible evidence subset."""

    return build_canonical_evidence_units(source_profile)


def adapt_master_profile_to_phase2_candidate_artifacts(
    source_profile: MasterProfile,
) -> Phase2CandidateArtifacts:
    """Project a normalized master profile into the full internal Phase 2 artifact bundle."""

    return build_phase2_candidate_artifacts(source_profile)
