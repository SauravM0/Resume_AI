from __future__ import annotations

from backend.app.tests.fixtures.phase2_candidate_profiles import (
    duplicate_heavy_messy_profile,
    strong_backend_engineer_profile,
)
from resume_optimizer.evidence_builder import build_candidate_evidence_graph
from resume_optimizer.phase2_validators import (
    validate_candidate_coverage_map,
    validate_phase2_graph,
    validate_phase2_stable_ids,
)
from resume_optimizer.services.evidence_coverage_map_service import (
    CandidateEvidenceCoverageMapService,
)


def test_phase2_graph_validator_accepts_realistic_backend_fixture() -> None:
    profile = strong_backend_engineer_profile()
    graph = build_candidate_evidence_graph(profile)

    report = validate_phase2_graph(graph, source_profile=profile)

    assert report.is_valid, report.model_dump()


def test_phase2_stable_id_validator_accepts_realistic_duplicate_fixture() -> None:
    report = validate_phase2_stable_ids(duplicate_heavy_messy_profile())

    assert report.is_valid, report.model_dump()


def test_phase2_coverage_validator_accepts_realistic_backend_fixture() -> None:
    profile = strong_backend_engineer_profile()
    graph = build_candidate_evidence_graph(profile)
    coverage_map = CandidateEvidenceCoverageMapService().build(graph)

    report = validate_candidate_coverage_map(graph, coverage_map)

    assert report.is_valid, report.model_dump()


def test_phase2_graph_validator_detects_invalid_duplicate_metadata() -> None:
    profile = duplicate_heavy_messy_profile()
    graph = build_candidate_evidence_graph(profile)
    duplicate_unit = next(unit for unit in graph.evidence_units if unit.duplicate_of is not None)
    broken_graph = graph.model_copy(
        update={
            "overlap_links": [
                link
                for link in graph.overlap_links
                if duplicate_unit.evidence_id not in {link.primary_evidence_id, link.related_evidence_id}
            ]
        }
    )

    report = validate_phase2_graph(broken_graph, source_profile=profile)

    assert not report.is_valid
    assert any(issue.code == "duplicate_without_overlap_link" for issue in report.issues)


def test_phase2_coverage_validator_detects_non_primary_references() -> None:
    profile = duplicate_heavy_messy_profile()
    graph = build_candidate_evidence_graph(profile)
    coverage_map = CandidateEvidenceCoverageMapService().build(graph)
    repeated_unit = next(unit for unit in graph.evidence_units if unit.duplicate_of is not None)
    broken_dimension = coverage_map.cloud_platform_strength.model_copy(
        update={"evidence_ids": [repeated_unit.evidence_id]}
    )
    broken_map = coverage_map.model_copy(update={"cloud_platform_strength": broken_dimension})

    report = validate_candidate_coverage_map(graph, broken_map)

    assert not report.is_valid
    assert any(issue.code == "coverage_dimension_non_primary_reference" for issue in report.issues)
