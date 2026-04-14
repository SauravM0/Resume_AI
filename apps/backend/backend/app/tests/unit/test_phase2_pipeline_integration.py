from __future__ import annotations

from backend.app.tests.fixtures.phase2_candidate_profiles import (
    strong_backend_engineer_profile,
    strong_backend_job_analysis,
)
from resume_optimizer.evidence_adapters import (
    adapt_master_profile_to_phase2_candidate_artifacts,
)
from resume_optimizer.phase2_artifacts import phase2_artifact_diagnostics_payload
from resume_optimizer.phase3_assembler import assemble_phase3_generation_payload
from resume_optimizer.services.phase2_service import Phase2Service


def test_phase2_service_exposes_new_candidate_artifacts_without_breaking_legacy_outputs() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()

    result = Phase2Service().run(job_analysis, source_profile=profile)

    assert result.ranking_response.ranked_experiences
    assert result.phase2_result.scored_evidence
    assert result.evidence_graph.candidate_profile_id == profile.id
    assert result.coverage_map.candidate_profile_id == profile.id
    assert result.coverage_map.total_evidence_units == len(result.evidence_graph.evidence_units)


def test_phase2_artifact_adapter_and_phase3_assembly_remain_compatible() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()
    phase2_service_result = Phase2Service().run(job_analysis, source_profile=profile)
    candidate_artifacts = adapt_master_profile_to_phase2_candidate_artifacts(profile)

    payload = assemble_phase3_generation_payload(
        job_analysis,
        phase2_service_result.phase2_result,
        profile,
        phase2_service_result.ranking_response,
    )

    assert candidate_artifacts.evidence_graph.candidate_profile_id == profile.id
    assert candidate_artifacts.coverage_map.candidate_profile_id == profile.id
    assert payload.validation_metadata.profile_id == profile.id
    assert payload.selected_experiences
    assert len(payload.selected_experiences) >= 2
    assert len(payload.selected_experiences[0].bullets) >= 2


def test_phase3_payload_preserves_breadth_of_selected_evidence() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()
    phase2_service_result = Phase2Service().run(job_analysis, source_profile=profile)

    payload = assemble_phase3_generation_payload(
        job_analysis,
        phase2_service_result.phase2_result,
        profile,
        phase2_service_result.ranking_response,
    )

    assert [item.id for item in payload.selected_experiences] == [
        "fixture.backend.exp.current",
        "fixture.backend.exp.prev",
    ]
    assert [bullet.id for bullet in payload.selected_experiences[0].bullets] == [
        "fixture.backend.exp.current.b1",
        "fixture.backend.exp.current.b2",
        "fixture.backend.exp.current.b3",
    ]
    assert len({item.id for item in payload.selected_experiences}) == len(payload.selected_experiences)
    assert payload.selected_experiences[0].selection_reason
    assert payload.selected_experiences[0].matched_requirements
    assert payload.selected_experiences[0].supporting_evidence_ids
    assert payload.matched_skills[0].selection_reason


def test_phase2_artifact_diagnostics_payload_exposes_graph_mix_and_coverage_summary() -> None:
    artifacts = adapt_master_profile_to_phase2_candidate_artifacts(
        strong_backend_engineer_profile()
    )

    diagnostics = phase2_artifact_diagnostics_payload(artifacts)

    assert diagnostics["evidence_graph_size"] == len(artifacts.evidence_graph.evidence_units)
    assert "experience_bullet" in diagnostics["evidence_source_mix"]
    assert diagnostics["coverage_top_role_families"]
    assert "dedupe_repeat_count" in diagnostics
