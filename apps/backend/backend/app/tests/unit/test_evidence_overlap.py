from __future__ import annotations

from resume_optimizer.evidence_builder import build_candidate_evidence_graph
from resume_optimizer.evidence_models import (
    EvidenceRelationshipType,
    EvidenceSourceType,
    WeakEvidenceTag,
)
from resume_optimizer.models import (
    AwardEntry,
    BulletEntry,
    CertificationEntry,
    EvidenceStrength,
    ExperienceEntry,
    MasterProfile,
    MetricEntry,
    PartialDate,
    PersonalProfile,
    ProjectEntry,
    SkillEntry,
    VerifiedStatus,
)


def _overlap_profile() -> MasterProfile:
    return MasterProfile(
        id="master.overlap",
        personal_profile=PersonalProfile(
            id="person.overlap",
            full_name="Overlap Tester",
            headline="Senior Backend Engineer",
            summary="Backend engineer focused on platform reliability and delivery.",
            evidence_strength=EvidenceStrength.MODERATE,
            verified_status=VerifiedStatus.SELF_REPORTED,
        ),
        experience=[
            ExperienceEntry(
                id="exp.one",
                organization="ShopCo",
                title="Senior Backend Engineer",
                start_date=PartialDate(raw_value="2022-01"),
                end_date=PartialDate(raw_value="2024-03"),
                bullets=[
                    BulletEntry(
                        id="bullet.exp.one.exact",
                        text="Built Python API with Redis cache that reduced checkout latency 40%.",
                        tools=["Python", "Redis"],
                        metrics=[MetricEntry(id="metric.latency.40", label="Latency reduction", value=40, unit="%")],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    ),
                    BulletEntry(
                        id="bullet.exp.one.partial",
                        text="Built internal onboarding tool with Python for support workflows.",
                        tools=["Python"],
                        evidence_strength=EvidenceStrength.MODERATE,
                        verified_status=VerifiedStatus.SELF_REPORTED,
                    ),
                ],
                tools=["Python", "Redis"],
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            ),
            ExperienceEntry(
                id="exp.two",
                organization="PayCo",
                title="Staff Engineer",
                start_date=PartialDate(raw_value="2024-04"),
                current=True,
                bullets=[
                    BulletEntry(
                        id="bullet.exp.two.clone",
                        text="Built Python API with Redis cache that reduced checkout latency 40%.",
                        tools=["Python", "Redis"],
                            metrics=[MetricEntry(id="metric.latency.clone", label="Latency reduction", value=40, unit="%")],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    ),
                    BulletEntry(
                        id="bullet.exp.two.partial",
                        text="Built internal CI tool with Python for release workflows.",
                        tools=["Python"],
                        evidence_strength=EvidenceStrength.MODERATE,
                        verified_status=VerifiedStatus.SELF_REPORTED,
                    ),
                    BulletEntry(
                        id="bullet.exp.two.aws",
                        text="Architected AWS platform deployment automation for regulated workloads.",
                        tools=["AWS", "Terraform"],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    ),
                ],
                tools=["AWS", "Terraform"],
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            ),
        ],
        projects=[
            ProjectEntry(
                id="proj.one",
                name="Checkout Platform Rewrite",
                role="Lead Engineer",
                summary="Built Python API with Redis cache that reduced checkout latency 40% for checkout traffic.",
                bullets=[
                    BulletEntry(
                        id="bullet.proj.one.restatement",
                        text="Built Python service with Redis cache that reduced checkout latency by 40% for the checkout flow.",
                        tools=["Python", "Redis"],
                            metrics=[MetricEntry(id="metric.latency.project", label="Latency reduction", value=40, unit="%")],
                        evidence_strength=EvidenceStrength.STRONG,
                        verified_status=VerifiedStatus.CORROBORATED,
                    )
                ],
                tools=["Python", "Redis"],
                start_date=PartialDate(raw_value="2023-05"),
                end_date=PartialDate(raw_value="2023-12"),
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        certifications=[
            CertificationEntry(
                id="cert.aws",
                name="AWS Certified Solutions Architect Associate",
                issuer="Amazon Web Services",
                issue_date=PartialDate(raw_value="2024-06"),
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        awards=[
            AwardEntry(
                id="award.latency",
                title="Engineering Excellence Award",
                awarder="ShopCo",
                summary="Recognized for reducing checkout latency 40% on the Python API platform.",
                award_date=PartialDate(raw_value="2024-02"),
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
        skills=[
            SkillEntry(
                id="skill.python",
                name="Python",
                category="backend",
                evidence_strength=EvidenceStrength.STRONG,
                verified_status=VerifiedStatus.CORROBORATED,
            )
        ],
    )


def test_exact_duplicates_are_marked_without_deleting_evidence() -> None:
    graph = build_candidate_evidence_graph(_overlap_profile())

    exact_links = [
        link for link in graph.overlap_links if link.relationship_type == EvidenceRelationshipType.EXACT_DUPLICATE
    ]

    assert exact_links
    exact_link = next(
        link
        for link in exact_links
        if {
            link.primary_evidence_id,
            link.related_evidence_id,
        }
        == {
            "evidence.bullet.exp.one.exact",
            "evidence.bullet.exp.two.clone",
        }
    )
    related = next(unit for unit in graph.evidence_units if unit.evidence_id == exact_link.related_evidence_id)

    assert len(graph.evidence_units) > 0
    assert exact_link.suppress_as_repeat is True
    assert related.duplicate_of == exact_link.primary_evidence_id
    assert WeakEvidenceTag.DUPLICATE in related.quality.weak_evidence_tags


def test_near_duplicates_and_parent_child_restatements_are_linked_deterministically() -> None:
    graph = build_candidate_evidence_graph(_overlap_profile())
    project_summary = next(
        unit
        for unit in graph.evidence_units
        if unit.source_type == EvidenceSourceType.PROJECT_SUMMARY
        and unit.parent_link.source_parent_id == "proj.one"
    )

    near_duplicate = next(
        link
        for link in graph.overlap_links
        if link.relationship_type == EvidenceRelationshipType.NEAR_DUPLICATE
        and {
            link.primary_evidence_id,
            link.related_evidence_id,
        }
        & {
            "evidence.bullet.exp.one.exact",
            "evidence.bullet.exp.two.clone",
        }
        and any(
            evidence_id.startswith("evidence.project_summary.")
            or evidence_id == "evidence.bullet.proj.one.restatement"
            for evidence_id in {link.primary_evidence_id, link.related_evidence_id}
        )
    )
    restatement = next(
        link
        for link in graph.overlap_links
        if link.relationship_type == EvidenceRelationshipType.PARENT_CHILD_RESTATEMENT
        and {
            link.primary_evidence_id,
            link.related_evidence_id,
        }
        == {
            "evidence.bullet.proj.one.restatement",
            project_summary.evidence_id,
        }
    )

    assert near_duplicate.suppress_as_repeat is True
    assert near_duplicate.confidence_score and near_duplicate.confidence_score >= 0.82
    assert restatement.same_parent is True
    assert restatement.shared_tools == ["python", "redis"]


def test_supporting_evidence_links_distinguish_declared_skill_certification_and_award_support() -> None:
    graph = build_candidate_evidence_graph(_overlap_profile())

    support_links = [
        link for link in graph.overlap_links if link.relationship_type == EvidenceRelationshipType.SUPPORTING_EVIDENCE
    ]

    assert any(link.related_evidence_id == "evidence.skill.python" for link in support_links)
    assert any(link.related_evidence_id == "evidence.cert.aws" for link in support_links)
    assert any(link.related_evidence_id == "evidence.award.latency" for link in support_links)

    python_support = next(link for link in support_links if link.related_evidence_id == "evidence.skill.python")
    cert_support = next(link for link in support_links if link.related_evidence_id == "evidence.cert.aws")

    assert python_support.suppress_as_repeat is False
    assert cert_support.primary_evidence_id == "evidence.bullet.exp.two.aws"


def test_partial_overlap_does_not_create_false_positive_duplicate_links() -> None:
    graph = build_candidate_evidence_graph(_overlap_profile())

    duplicate_like_links = [
        link
        for link in graph.overlap_links
        if link.relationship_type
        in {
            EvidenceRelationshipType.EXACT_DUPLICATE,
            EvidenceRelationshipType.NEAR_DUPLICATE,
        }
    ]

    partial_ids = {
        "evidence.bullet.exp.one.partial",
        "evidence.bullet.exp.two.partial",
    }
    assert not any(
        {link.primary_evidence_id, link.related_evidence_id} == partial_ids
        for link in duplicate_like_links
    )


def test_overlap_graph_preserves_mixed_source_relationships() -> None:
    graph = build_candidate_evidence_graph(_overlap_profile())

    relationship_types = {link.relationship_type for link in graph.overlap_links}
    source_types = {unit.source_type for unit in graph.evidence_units}

    assert relationship_types == {
        EvidenceRelationshipType.EXACT_DUPLICATE,
        EvidenceRelationshipType.NEAR_DUPLICATE,
        EvidenceRelationshipType.PARENT_CHILD_RESTATEMENT,
        EvidenceRelationshipType.SUPPORTING_EVIDENCE,
    }
    assert {
        EvidenceSourceType.EXPERIENCE_BULLET,
        EvidenceSourceType.PROJECT_SUMMARY,
        EvidenceSourceType.CERTIFICATION,
        EvidenceSourceType.AWARD,
        EvidenceSourceType.SKILL_DECLARATION,
    }.issubset(source_types)
