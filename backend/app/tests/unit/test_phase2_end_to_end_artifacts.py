from __future__ import annotations

from backend.app.tests.fixtures.phase2_candidate_profiles import (
    strong_backend_engineer_profile,
    strong_backend_job_analysis,
)
from resume_optimizer.phase2_validators import (
    validate_candidate_coverage_map,
    validate_phase2_graph,
)
from resume_optimizer.ranking_service import build_phase2_ranking_artifacts
from resume_optimizer.services.evidence_coverage_map_service import (
    CandidateEvidenceCoverageMapService,
)
from resume_optimizer.services.evidence_extraction_service import (
    CandidateEvidenceExtractionService,
)


def test_end_to_end_phase2_artifact_generation_for_backend_fixture() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()

    extraction_result = CandidateEvidenceExtractionService().extract(profile)
    coverage_map = CandidateEvidenceCoverageMapService().build(extraction_result.evidence_graph)
    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)

    graph_report = validate_phase2_graph(extraction_result.evidence_graph, source_profile=profile)
    coverage_report = validate_candidate_coverage_map(extraction_result.evidence_graph, coverage_map)

    assert graph_report.is_valid, graph_report.model_dump()
    assert coverage_report.is_valid, coverage_report.model_dump()

    golden_summary = {
        "candidate_profile_id": extraction_result.evidence_graph.candidate_profile_id,
        "total_evidence_units": len(extraction_result.evidence_graph.evidence_units),
        "suppressed_repeat_units": coverage_map.suppressed_repeat_units,
        "top_role_family": coverage_map.role_family_strengths[0].area,
        "top_cluster": coverage_map.core_technical_clusters[0].area,
        "top_experience_sources": [item.source_item_id for item in artifacts.ranking_response.ranked_experiences],
        "skills_to_highlight": artifacts.ranking_response.skills_to_highlight,
        "selected_experience_count": len(artifacts.selection_result.selected_experiences),
        "selected_skill_count": len(artifacts.selection_result.selected_skills),
    }

    assert golden_summary == {
        "candidate_profile_id": "fixture.backend",
        "total_evidence_units": 14,
        "suppressed_repeat_units": 0,
        "top_role_family": "backend",
        "top_cluster": "cloud_platform",
        "top_experience_sources": [
            "fixture.backend.exp.current",
            "fixture.backend.exp.prev",
        ],
        "skills_to_highlight": ["Python", "AWS"],
        "selected_experience_count": 2,
        "selected_skill_count": 2,
    }
