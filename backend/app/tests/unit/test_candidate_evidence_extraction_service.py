from __future__ import annotations

from pathlib import Path

from resume_optimizer.evidence_adapters import (
    adapt_master_profile_to_evidence_graph,
    adapt_master_profile_to_ranking_evidence,
)
from resume_optimizer.evidence_models import EvidenceChildType, EvidenceSection, EvidenceSourceType
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.services.evidence_extraction_service import (
    CandidateEvidenceExtractionService,
)


def _fixture_profile():
    profile_path = (
        Path(__file__).resolve().parents[4] / "data" / "master_profile.example.json"
    )
    return load_and_normalize_master_profile(profile_path)


def test_extraction_service_emits_graph_and_summary_counts() -> None:
    profile = _fixture_profile()
    service = CandidateEvidenceExtractionService()

    result = service.extract(profile)

    expected_total = (
        int(bool(profile.personal_profile.headline))
        + int(bool(profile.personal_profile.summary))
        + sum(len(entry.bullets) + 1 for entry in profile.experience)
        + sum(len(entry.bullets) + int(bool(entry.summary)) for entry in profile.projects)
        + sum(len(entry.bullets) + len(entry.honors) for entry in profile.education)
        + len(profile.certifications)
        + sum(len(entry.bullets) if entry.bullets else 1 for entry in profile.awards)
        + sum(
            1
            for skill in profile.skills
            if not (
                skill.verified_status.value == "unverified"
                and skill.evidence_strength.value == "weak"
            )
        )
    )

    assert result.evidence_graph.candidate_profile_id == profile.id
    assert result.summary.total_evidence_units == expected_total
    assert result.summary.experience_evidence_count == sum(len(entry.bullets) + 1 for entry in profile.experience)
    assert result.summary.project_evidence_count == sum(
        len(entry.bullets) + int(bool(entry.summary)) for entry in profile.projects
    )
    assert result.summary.certification_evidence_count == len(profile.certifications)
    assert result.summary.skill_declaration_count == len(
        [
            skill
            for skill in profile.skills
            if not (
                skill.verified_status.value == "unverified"
                and skill.evidence_strength.value == "weak"
            )
        ]
    )


def test_extraction_provenance_preserves_sections_parent_ids_and_bullet_indexes() -> None:
    profile = _fixture_profile()
    graph = adapt_master_profile_to_evidence_graph(profile)

    exp_bullet = next(
        unit for unit in graph.evidence_units if unit.source_type == EvidenceSourceType.EXPERIENCE_BULLET
    )
    project_bullet = next(
        unit for unit in graph.evidence_units if unit.source_type == EvidenceSourceType.PROJECT_BULLET
    )

    assert exp_bullet.parent_link.source_section == EvidenceSection.EXPERIENCE
    assert exp_bullet.parent_link.source_parent_id in {entry.id for entry in profile.experience}
    assert exp_bullet.parent_link.source_child_type == EvidenceChildType.BULLET
    assert exp_bullet.parent_link.source_child_index == 0
    assert exp_bullet.provenance.source_section == EvidenceSection.EXPERIENCE
    assert exp_bullet.provenance.source_child_index == 0

    assert project_bullet.parent_link.source_section == EvidenceSection.PROJECTS
    assert project_bullet.parent_link.source_parent_id in {entry.id for entry in profile.projects}
    assert project_bullet.parent_link.source_child_type == EvidenceChildType.BULLET
    assert project_bullet.provenance.source_section == EvidenceSection.PROJECTS


def test_extraction_ids_and_parent_child_links_are_stable() -> None:
    profile = _fixture_profile()

    graph_one = adapt_master_profile_to_evidence_graph(profile)
    graph_two = adapt_master_profile_to_evidence_graph(profile)

    one_by_id = {unit.evidence_id: unit for unit in graph_one.evidence_units}
    two_by_id = {unit.evidence_id: unit for unit in graph_two.evidence_units}

    assert set(one_by_id) == set(two_by_id)
    for evidence_id, unit in one_by_id.items():
        other = two_by_id[evidence_id]
        assert other.parent_link == unit.parent_link
        assert other.provenance == unit.provenance


def test_extraction_distinguishes_skill_declarations_from_bullet_backed_evidence() -> None:
    profile = _fixture_profile()
    graph = adapt_master_profile_to_evidence_graph(profile)
    ranking_subset = adapt_master_profile_to_ranking_evidence(profile)

    skill_declarations = [
        unit for unit in graph.evidence_units if unit.source_type == EvidenceSourceType.SKILL_DECLARATION
    ]
    experience_bullets = [
        unit for unit in graph.evidence_units if unit.source_type == EvidenceSourceType.EXPERIENCE_BULLET
    ]

    assert skill_declarations
    assert experience_bullets
    assert all(unit.parent_link.source_section == EvidenceSection.SKILLS for unit in skill_declarations)
    assert all(unit.parent_link.source_child_id is None for unit in skill_declarations)
    assert all(unit.parent_link.source_child_id is not None for unit in experience_bullets)
    assert any(unit.source_type == EvidenceSourceType.SKILL_DECLARATION for unit in ranking_subset)


def test_mixed_source_extraction_covers_experience_projects_certs_and_skills() -> None:
    profile = _fixture_profile()
    graph = adapt_master_profile_to_evidence_graph(profile)

    source_types = {unit.source_type for unit in graph.evidence_units}

    assert EvidenceSourceType.EXPERIENCE_SUMMARY in source_types
    assert EvidenceSourceType.EXPERIENCE_BULLET in source_types
    assert EvidenceSourceType.PROJECT_SUMMARY in source_types
    assert EvidenceSourceType.PROJECT_BULLET in source_types
    assert EvidenceSourceType.CERTIFICATION in source_types
    assert EvidenceSourceType.SKILL_DECLARATION in source_types
