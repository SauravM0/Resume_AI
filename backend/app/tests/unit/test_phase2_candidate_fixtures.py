from __future__ import annotations

from backend.app.tests.fixtures.phase2_candidate_profiles import (
    all_phase2_candidate_profile_fixtures,
    duplicate_heavy_messy_profile,
)
from resume_optimizer.evidence_builder import build_candidate_evidence_graph
from resume_optimizer.evidence_models import CoverageBand, EvidenceRelationshipType, EvidenceSourceType
from resume_optimizer.phase2_validators import (
    validate_candidate_coverage_map,
    validate_phase2_graph,
    validate_phase2_stable_ids,
)
from resume_optimizer.services.evidence_coverage_map_service import (
    CandidateEvidenceCoverageMapService,
)


def test_phase2_fixture_set_builds_valid_graphs_and_coverage_maps() -> None:
    coverage_service = CandidateEvidenceCoverageMapService()

    for case in all_phase2_candidate_profile_fixtures():
        graph = build_candidate_evidence_graph(case.profile)
        coverage_map = coverage_service.build(graph)

        graph_report = validate_phase2_graph(graph, source_profile=case.profile)
        stable_id_report = validate_phase2_stable_ids(case.profile)
        coverage_report = validate_candidate_coverage_map(graph, coverage_map)

        assert graph_report.is_valid, (case.key, graph_report.model_dump())
        assert stable_id_report.is_valid, (case.key, stable_id_report.model_dump())
        assert coverage_report.is_valid, (case.key, coverage_report.model_dump())


def test_fixture_profiles_cover_requested_candidate_shapes() -> None:
    cases = {case.key: case.profile for case in all_phase2_candidate_profile_fixtures()}

    assert set(cases) == {
        "strong_backend_engineer",
        "frontend_heavy_engineer",
        "fullstack_mixed_profile",
        "leadership_heavy_profile",
        "sparse_junior_profile",
        "duplicate_heavy_messy_profile",
        "cert_heavy_profile",
    }

    backend_graph = build_candidate_evidence_graph(cases["strong_backend_engineer"])
    frontend_graph = build_candidate_evidence_graph(cases["frontend_heavy_engineer"])
    leadership_graph = build_candidate_evidence_graph(cases["leadership_heavy_profile"])
    cert_graph = build_candidate_evidence_graph(cases["cert_heavy_profile"])

    assert any(unit.source_type == EvidenceSourceType.CERTIFICATION for unit in cert_graph.evidence_units)
    assert any("react" in unit.normalized_tools for unit in frontend_graph.evidence_units)
    assert any("kubernetes" in unit.normalized_tools for unit in backend_graph.evidence_units)
    assert any("leadership_signal" in unit.signals.signal_tokens for unit in leadership_graph.evidence_units)


def test_duplicate_heavy_fixture_produces_overlap_links_and_repeat_suppression() -> None:
    profile = duplicate_heavy_messy_profile()
    graph = build_candidate_evidence_graph(profile)
    coverage_map = CandidateEvidenceCoverageMapService().build(graph)

    relationship_types = {link.relationship_type for link in graph.overlap_links}

    assert EvidenceRelationshipType.EXACT_DUPLICATE in relationship_types
    assert EvidenceRelationshipType.NEAR_DUPLICATE in relationship_types
    assert coverage_map.suppressed_repeat_units >= 1


def test_golden_fixture_level_assertions_hold_for_backend_and_sparse_profiles() -> None:
    cases = {case.key: case.profile for case in all_phase2_candidate_profile_fixtures()}
    backend_coverage = CandidateEvidenceCoverageMapService().build(
        build_candidate_evidence_graph(cases["strong_backend_engineer"])
    )
    sparse_coverage = CandidateEvidenceCoverageMapService().build(
        build_candidate_evidence_graph(cases["sparse_junior_profile"])
    )

    assert backend_coverage.architecture_system_design_strength.band in {
        CoverageBand.STRONG,
        CoverageBand.MODERATE,
    }
    assert backend_coverage.cloud_platform_strength.band in {
        CoverageBand.STRONG,
        CoverageBand.MODERATE,
    }
    assert sparse_coverage.delivery_execution_strength.band in {
        CoverageBand.EMERGING,
        CoverageBand.SPARSE,
    }
    assert any(gap.area == "overall_evidence_sparsity" for gap in sparse_coverage.sparsity_weak_zones)
