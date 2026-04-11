from __future__ import annotations

from resume_optimizer.evidence_builder import build_candidate_evidence_graph
from resume_optimizer.evidence_models import CoverageBand
from resume_optimizer.models import (
    BulletEntry,
    CertificationEntry,
    EvidenceStrength,
    ExperienceEntry,
    MasterProfile,
    MetricEntry,
    PartialDate,
    PersonalProfile,
    SkillEntry,
    VerifiedStatus,
)
from resume_optimizer.services.evidence_coverage_map_service import (
    CandidateEvidenceCoverageMapService,
)


def _bullet(
    bullet_id: str,
    text: str,
    *,
    tools: list[str] | None = None,
    metrics: list[MetricEntry] | None = None,
    verified_status: VerifiedStatus = VerifiedStatus.CORROBORATED,
    evidence_strength: EvidenceStrength = EvidenceStrength.STRONG,
) -> BulletEntry:
    return BulletEntry(
        id=bullet_id,
        text=text,
        tools=tools or [],
        metrics=metrics or [],
        verified_status=verified_status,
        evidence_strength=evidence_strength,
    )


def _profile(
    *,
    profile_id: str,
    headline: str,
    summary: str,
    experience: list[ExperienceEntry],
    certifications: list[CertificationEntry] | None = None,
    skills: list[SkillEntry] | None = None,
) -> MasterProfile:
    return MasterProfile(
        id=profile_id,
        personal_profile=PersonalProfile(
            id=f"{profile_id}.person",
            full_name="Coverage Test",
            headline=headline,
            summary=summary,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=experience,
        certifications=certifications or [],
        skills=skills or [],
    )


def _coverage_map(profile: MasterProfile):
    graph = build_candidate_evidence_graph(profile)
    return CandidateEvidenceCoverageMapService().build(graph)


def test_strong_backend_profile_has_backend_cloud_and_architecture_strength() -> None:
    profile = _profile(
        profile_id="profile.backend",
        headline="Staff Backend Engineer",
        summary="Backend platform engineer focused on reliability, cloud infrastructure, and delivery.",
        experience=[
            ExperienceEntry(
                id="exp.backend",
                organization="InfraCo",
                title="Staff Backend Engineer",
                start_date=PartialDate(raw_value="2022-01"),
                current=True,
                tools=["Python", "AWS", "Kubernetes", "Terraform"],
                bullets=[
                    _bullet(
                        "bullet.backend.1",
                        "Architected AWS platform services with Kubernetes and Terraform, reducing deployment time 60% across backend systems.",
                        tools=["Python", "AWS", "Kubernetes", "Terraform"],
                        metrics=[MetricEntry(id="metric.backend.1", label="Deployment time reduction", value=60, unit="%")],
                    ),
                    _bullet(
                        "bullet.backend.2",
                        "Led reliability improvements for Python APIs and reduced incident volume 35% on the shared platform.",
                        tools=["Python", "AWS"],
                        metrics=[MetricEntry(id="metric.backend.2", label="Incident reduction", value=35, unit="%")],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        certifications=[
            CertificationEntry(
                id="cert.backend.aws",
                name="AWS Certified Solutions Architect Associate",
                issuer="Amazon Web Services",
                issue_date=PartialDate(raw_value="2024-03"),
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )

    coverage = _coverage_map(profile)

    assert coverage.architecture_system_design_strength.band in {CoverageBand.STRONG, CoverageBand.MODERATE}
    assert coverage.cloud_platform_strength.band in {CoverageBand.STRONG, CoverageBand.MODERATE}
    assert any(item.area == "backend" and item.band in {CoverageBand.STRONG, CoverageBand.MODERATE} for item in coverage.role_family_strengths)
    assert any(item.area == "cloud_platform" for item in coverage.core_technical_clusters)


def test_mixed_fullstack_profile_surfaces_balanced_role_family_and_product_strength() -> None:
    profile = _profile(
        profile_id="profile.fullstack",
        headline="Senior Fullstack Engineer",
        summary="Fullstack engineer shipping backend services and frontend product experiences with partner teams.",
        experience=[
            ExperienceEntry(
                id="exp.fullstack",
                organization="ProductCo",
                title="Senior Fullstack Engineer",
                start_date=PartialDate(raw_value="2021-06"),
                current=True,
                tools=["React", "TypeScript", "Python", "PostgreSQL"],
                bullets=[
                    _bullet(
                        "bullet.fullstack.1",
                        "Built React and TypeScript customer workflows with backend Python APIs, increasing conversion 18%.",
                        tools=["React", "TypeScript", "Python"],
                        metrics=[MetricEntry(id="metric.fullstack.1", label="Conversion lift", value=18, unit="%")],
                    ),
                    _bullet(
                        "bullet.fullstack.2",
                        "Partnered with product and design stakeholders to launch experimentation dashboards for checkout analytics.",
                        tools=["React", "PostgreSQL"],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )

    coverage = _coverage_map(profile)

    role_areas = {item.area for item in coverage.role_family_strengths}
    assert {"backend", "frontend", "fullstack"} & role_areas
    assert coverage.product_stakeholder_strength.band in {CoverageBand.STRONG, CoverageBand.MODERATE, CoverageBand.EMERGING}
    assert coverage.experimentation_analytics_strength.evidence_count >= 1


def test_leadership_heavy_profile_surfaces_leadership_and_ownership_depth() -> None:
    profile = _profile(
        profile_id="profile.leadership",
        headline="Engineering Manager",
        summary="Engineering leader mentoring teams and driving cross-functional delivery.",
        experience=[
            ExperienceEntry(
                id="exp.leadership",
                organization="ScaleCo",
                title="Engineering Manager",
                start_date=PartialDate(raw_value="2020-02"),
                current=True,
                bullets=[
                    _bullet(
                        "bullet.leadership.1",
                        "Managed eight engineers, mentored senior ICs, and led cross-functional roadmap delivery across platform and product teams.",
                    ),
                    _bullet(
                        "bullet.leadership.2",
                        "Owned multi-team delivery execution and improved quarterly roadmap completion to 92%.",
                        metrics=[MetricEntry(id="metric.leadership.1", label="Roadmap completion", value=92, unit="%")],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )

    coverage = _coverage_map(profile)

    assert coverage.leadership_depth.band in {CoverageBand.STRONG, CoverageBand.MODERATE}
    assert coverage.ownership_depth.band in {CoverageBand.STRONG, CoverageBand.MODERATE}
    assert any(highlight.area == "leadership_depth" for highlight in coverage.high_level_strengths)


def test_junior_sparse_profile_surfaces_sparsity_and_weak_zones() -> None:
    profile = _profile(
        profile_id="profile.junior",
        headline="Software Engineer",
        summary="Early-career engineer.",
        experience=[
            ExperienceEntry(
                id="exp.junior",
                organization="Startup",
                title="Software Engineer",
                start_date=PartialDate(raw_value="2025-01"),
                current=True,
                bullets=[
                    _bullet(
                        "bullet.junior.1",
                        "Worked on internal tools.",
                        verified_status=VerifiedStatus.SELF_REPORTED,
                        evidence_strength=EvidenceStrength.WEAK,
                    )
                ],
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.WEAK,
            )
        ],
    )

    coverage = _coverage_map(profile)

    assert any(gap.area == "overall_evidence_sparsity" for gap in coverage.sparsity_weak_zones)
    assert coverage.delivery_execution_strength.band in {CoverageBand.EMERGING, CoverageBand.SPARSE}
    assert coverage.weak_evidence_units >= 1


def test_declared_skills_without_support_surface_skill_gap() -> None:
    profile = _profile(
        profile_id="profile.skills-gap",
        headline="Software Engineer",
        summary="Engineer with many claimed skills.",
        experience=[
            ExperienceEntry(
                id="exp.skills-gap",
                organization="Builder",
                title="Software Engineer",
                start_date=PartialDate(raw_value="2023-01"),
                current=True,
                bullets=[
                    _bullet(
                        "bullet.skills-gap.1",
                        "Built Python automation for an internal workflow.",
                        tools=["Python"],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.MODERATE,
            )
        ],
        skills=[
            SkillEntry(
                id="skill.python",
                name="Python",
                category="backend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="skill.react",
                name="React",
                category="frontend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="skill.aws",
                name="AWS",
                category="cloud",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )

    coverage = _coverage_map(profile)

    assert any(gap.area == "declared_skill_support_gap" for gap in coverage.sparsity_weak_zones)
    assert coverage.declared_skill_units == 3
