from __future__ import annotations

from pathlib import Path

from resume_optimizer.evidence_builder import (
    build_candidate_evidence_graph,
    build_canonical_evidence_units,
)
from resume_optimizer.evidence_models import (
    CandidateEvidenceGraph,
    DeliveryScope,
    EvidenceChildType,
    EvidenceCoverage,
    EvidenceParentLink,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceRewriteSafety,
    EvidenceSignals,
    EvidenceSourceType,
    EvidenceTag,
    EvidenceTagCategory,
    EvidenceUnit,
    ImpactType,
    OwnershipLevel,
    RecencyMetadata,
    RewriteSafetyLevel,
)
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.models import (
    AwardEntry,
    BulletEntry,
    EducationEntry,
    EvidenceStrength,
    ItemType,
    MasterProfile,
    PartialDate,
    PersonalProfile,
    SkillEntry,
    SourceLink,
    VerifiedStatus,
)


def test_evidence_unit_round_trip_serialization() -> None:
    unit = EvidenceUnit(
        evidence_id="evidence.experience.demo",
        source_type=EvidenceSourceType.EXPERIENCE_BULLET,
        parent_link=EvidenceParentLink(
            source_section="experience",
            source_parent_id="exp.demo",
            source_parent_type=ItemType.EXPERIENCE,
            source_child_id="bullet.demo",
            source_child_type=EvidenceChildType.BULLET,
            source_child_index=0,
        ),
        canonical_text="Led platform migration with measurable latency improvements.",
        raw_text="Led platform migration with measurable latency improvements.",
        normalized_skills=["python", "aws"],
        normalized_tools=["python", "aws"],
        normalized_domains=["platform"],
        signals=EvidenceSignals(
            ownership_level=OwnershipLevel.OWNER,
            delivery_scope=DeliveryScope.PLATFORM,
            impact_types=[ImpactType.RELIABILITY, ImpactType.PERFORMANCE],
            impact_metrics_present=True,
            role_family_hints=["individual_contributor"],
            business_outcome_hints=["reliability"],
            seniority_signals=["senior"],
            signal_tokens=["metrics_present", "high_impact_score"],
            tags=[
                EvidenceTag(category=EvidenceTagCategory.SKILL, value="python"),
                EvidenceTag(category=EvidenceTagCategory.DOMAIN, value="platform"),
            ],
        ),
        quality=EvidenceQuality(
            clarity_score=0.92,
            specificity_score=0.88,
        ),
        rewrite_safety=EvidenceRewriteSafety(
            level=RewriteSafetyLevel.CAUTION,
            rewrite_allowed=True,
            paraphrase_safe=True,
            merge_safe=False,
            preserve_metrics=True,
            preserve_named_entities=True,
        ),
        coverage=EvidenceCoverage(
            source_item_count=1,
            source_child_count=1,
            source_metric_count=2,
            source_link_count=1,
            multi_source_support=False,
        ),
        recency=RecencyMetadata(
            start_date="2023-01",
            end_date="2024-02",
            is_current=False,
            source_recency_score=0.73,
        ),
        evidence_strength=EvidenceStrength.STRONG,
        verified_status=VerifiedStatus.CORROBORATED,
        dedupe_fingerprint="dedupe.1234567890abcdef",
        provenance=EvidenceProvenance(
            source_section="experience",
            source_item_type=ItemType.EXPERIENCE,
            source_parent_id="exp.demo",
            source_parent_title="Senior Platform Engineer",
            source_organization="Demo Corp",
            source_child_id="bullet.demo",
            source_child_type=EvidenceChildType.BULLET,
            source_child_index=0,
            source_links=[
                SourceLink(
                    source_type="resume",
                    source_id="source.resume.demo",
                    source_url="https://example.com/resume-demo",
                )
            ],
            extraction_method="experience_bullet",
            metric_ids=["metric.demo.1", "metric.demo.2"],
        ),
    )

    payload = unit.model_dump(mode="json")
    restored = EvidenceUnit.model_validate(payload)
    restored_from_json = EvidenceUnit.model_validate_json(unit.model_dump_json())

    assert restored == unit
    assert restored_from_json == unit
    assert restored.evidence_unit_id == "evidence.experience.demo"
    assert restored.source_entity_id == "exp.demo"
    assert restored.source_bullet_id == "bullet.demo"
    assert restored.provenance.source_entity_title == "Senior Platform Engineer"


def test_build_candidate_evidence_graph_supports_new_schema_and_legacy_subset() -> None:
    profile_path = (
        Path(__file__).resolve().parents[4] / "data" / "master_profile.example.json"
    )
    profile = load_and_normalize_master_profile(profile_path)

    graph = build_candidate_evidence_graph(profile)
    legacy_units = build_canonical_evidence_units(profile)
    round_tripped = CandidateEvidenceGraph.model_validate_json(graph.model_dump_json())

    assert round_tripped == graph
    assert graph.candidate_profile_id == profile.id
    assert any(unit.source_type == EvidenceSourceType.PERSONAL_SUMMARY for unit in graph.evidence_units)
    assert any(unit.source_type == EvidenceSourceType.EDUCATION_ACHIEVEMENT for unit in graph.evidence_units)
    assert all(isinstance(unit, EvidenceUnit) for unit in graph.evidence_units)
    assert all(
        unit.source_type
        in {
            EvidenceSourceType.EXPERIENCE_BULLET,
            EvidenceSourceType.EXPERIENCE_SUMMARY,
            EvidenceSourceType.PROJECT_BULLET,
            EvidenceSourceType.PROJECT_SUMMARY,
            EvidenceSourceType.CERTIFICATION,
            EvidenceSourceType.SKILL_DECLARATION,
        }
        for unit in legacy_units
    )


def test_build_candidate_evidence_graph_handles_awards_and_education_honors() -> None:
    profile = MasterProfile(
        id="master.schema-test",
        personal_profile=PersonalProfile(
            id="person.schema-test",
            item_type=ItemType.PERSONAL_PROFILE,
            full_name="Schema Test",
            headline="Staff Platform Engineer",
            summary="Built internal platforms and mentored delivery teams.",
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        education=[
            EducationEntry(
                id="edu.schema-test",
                institution="University Test",
                degree="BSc Computer Science",
                honors=["Dean's List"],
                start_date=PartialDate(raw_value="2015-09"),
                end_date=PartialDate(raw_value="2019-06"),
                evidence_strength=EvidenceStrength.MODERATE,
            )
        ],
        awards=[
            AwardEntry(
                id="award.schema-test",
                title="Engineering Excellence Award",
                awarder="Example Org",
                award_date=PartialDate(raw_value="2024-05"),
                bullets=[
                    BulletEntry(
                        id="bullet.award.schema-test",
                        text="Recognized for leading a platform modernization rollout across multiple teams.",
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    )
                ],
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        skills=[
            SkillEntry(
                id="skill.schema-test",
                name="Python",
                category="backend",
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
    )

    graph = build_candidate_evidence_graph(profile)
    source_types = {unit.source_type for unit in graph.evidence_units}

    assert EvidenceSourceType.AWARD in source_types
    assert EvidenceSourceType.EDUCATION_ACHIEVEMENT in source_types
    assert EvidenceSourceType.PERSONAL_SUMMARY in source_types
    assert EvidenceSourceType.SKILL_DECLARATION in source_types

    award_unit = next(unit for unit in graph.evidence_units if unit.source_type == EvidenceSourceType.AWARD)
    assert award_unit.parent_link.source_parent_id == "award.schema-test"
    assert award_unit.parent_link.source_child_type == EvidenceChildType.BULLET
    assert award_unit.coverage.source_child_count == 1
