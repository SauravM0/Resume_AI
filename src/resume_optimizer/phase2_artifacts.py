"""Shared Phase 2 artifact bundle bridging new evidence models into the pipeline."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.app.cache.codecs import (
    deserialize_phase2_candidate_artifacts,
    serialize_phase2_candidate_artifacts,
)
from backend.app.cache.keys import build_cache_key, stable_code_hash, stable_model_hash
from backend.app.cache.storage import get_or_compute

from .evidence_models import CandidateEvidenceCoverageMap, CandidateEvidenceGraph, CanonicalEvidenceUnit
from .models import MasterProfile

if TYPE_CHECKING:
    from .services.evidence_extraction_service import CandidateEvidenceExtractionSummary

PHASE2_CANDIDATE_ARTIFACTS_CACHE_NAMESPACE = "phase2_candidate_artifacts"
PHASE2_CANDIDATE_ARTIFACTS_CACHE_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class Phase2CandidateArtifacts:
    """Candidate-level Phase 2 artifacts derived from the normalized source profile."""

    source_profile: MasterProfile
    evidence_graph: CandidateEvidenceGraph
    coverage_map: CandidateEvidenceCoverageMap
    ranking_compatible_evidence: list[CanonicalEvidenceUnit]
    extraction_summary: CandidateEvidenceExtractionSummary


def build_phase2_candidate_artifacts(source_profile: MasterProfile) -> Phase2CandidateArtifacts:
    """Build the typed Phase 2 evidence artifacts from source truth once per pipeline run."""

    from .services.evidence_coverage_map_service import (
        DEFAULT_CANDIDATE_EVIDENCE_COVERAGE_MAP_SERVICE,
    )
    from .services.evidence_extraction_service import (
        DEFAULT_CANDIDATE_EVIDENCE_EXTRACTION_SERVICE,
    )
    cache_key = build_cache_key(
        PHASE2_CANDIDATE_ARTIFACTS_CACHE_NAMESPACE,
        {
            "source_profile_hash": stable_model_hash(source_profile),
            "artifact_builder_code_hash": stable_code_hash(
                build_phase2_candidate_artifacts,
                DEFAULT_CANDIDATE_EVIDENCE_EXTRACTION_SERVICE.extractor.extract,
                DEFAULT_CANDIDATE_EVIDENCE_COVERAGE_MAP_SERVICE.build,
            ),
        },
    )
    cached, _ = get_or_compute(
        namespace=PHASE2_CANDIDATE_ARTIFACTS_CACHE_NAMESPACE,
        key=cache_key,
        compute=lambda: _compute_phase2_candidate_artifacts(
            source_profile=source_profile,
            extraction_service=DEFAULT_CANDIDATE_EVIDENCE_EXTRACTION_SERVICE,
            coverage_service=DEFAULT_CANDIDATE_EVIDENCE_COVERAGE_MAP_SERVICE,
        ),
        serialize=serialize_phase2_candidate_artifacts,
        deserialize=deserialize_phase2_candidate_artifacts,
        ttl_seconds=PHASE2_CANDIDATE_ARTIFACTS_CACHE_TTL_SECONDS,
        metadata={"source_profile_id": source_profile.id},
    )
    return cached


def _compute_phase2_candidate_artifacts(
    *,
    source_profile: MasterProfile,
    extraction_service,
    coverage_service,
) -> Phase2CandidateArtifacts:
    extraction_result = extraction_service.extract(source_profile)
    coverage_map = coverage_service.build(extraction_result.evidence_graph)
    return Phase2CandidateArtifacts(
        source_profile=source_profile,
        evidence_graph=extraction_result.evidence_graph,
        coverage_map=coverage_map,
        ranking_compatible_evidence=extraction_result.ranking_compatible_evidence,
        extraction_summary=extraction_result.summary,
    )


def phase2_artifact_diagnostics_payload(
    artifacts: Phase2CandidateArtifacts,
) -> dict[str, object]:
    """Return a compact, log-safe diagnostics payload for Phase 2 artifact inspection."""

    source_mix = Counter(unit.source_type.value for unit in artifacts.evidence_graph.evidence_units)
    top_role_families = [dimension.area for dimension in artifacts.coverage_map.role_family_strengths[:3]]
    top_clusters = [dimension.area for dimension in artifacts.coverage_map.core_technical_clusters[:3]]
    return {
        "evidence_graph_size": len(artifacts.evidence_graph.evidence_units),
        "evidence_source_mix": dict(sorted(source_mix.items())),
        "coverage_top_role_families": top_role_families,
        "coverage_top_clusters": top_clusters,
        "coverage_weak_zones": [gap.area for gap in artifacts.coverage_map.weak_match_flags[:5]],
        "dedupe_repeat_count": artifacts.coverage_map.suppressed_repeat_units,
        "declared_skill_count": artifacts.coverage_map.declared_skill_units,
    }
