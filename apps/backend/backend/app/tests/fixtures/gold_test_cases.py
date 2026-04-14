"""Gold test case fixtures for Phase 6 end-to-end acceptance tests.

Each fixture represents a different role type that the product must handle correctly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from resume_optimizer.models import (
    BulletEntry,
    CertificationEntry,
    EducationEntry,
    EvidenceStrength,
    ExperienceEntry,
    MasterProfile,
    MetricEntry,
    PartialDate,
    PersonalProfile,
    ProjectEntry,
    RoleType,
    SeniorityLevel,
    SkillEntry,
    VerifiedStatus,
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


def _metric(
    metric_id: str, label: str, value: int | float, unit: str | None = None
) -> MetricEntry:
    return MetricEntry(id=metric_id, label=label, value=value, unit=unit)


@dataclass(frozen=True)
class GoldTestCase:
    """A gold test case representing a specific role type."""

    key: str
    role_type: str
    seniority: str
    required_skills: list[str]
    profile: MasterProfile
    expected_keywords: list[str]
    expected_selected_experiences: list[str]
    expected_selected_projects: list[str]
    expected_selected_skills: list[str]


def frontend_heavy_profile() -> MasterProfile:
    """Profile suitable for frontend-heavy roles."""
    return MasterProfile(
        id="fixture.frontend",
        personal_profile=PersonalProfile(
            id="fixture.frontend.person",
            full_name="Alex Frontend",
            headline="Senior Frontend Engineer",
            summary="Frontend engineer specialized in React, TypeScript, and modern UI patterns.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.STRONG,
            domain_tags=["frontend", "react", "ui"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.frontend.exp.current",
                organization="WebCorp",
                title="Senior Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2022-01"),
                current=True,
                tools=["React", "TypeScript", "GraphQL", "CSS"],
                bullets=[
                    _bullet(
                        "fixture.frontend.exp.current.b1",
                        "Built React components serving 2M+ daily users with 99.9% uptime.",
                        tools=["React", "TypeScript"],
                        metrics=[
                            _metric("fixture.frontend.m1", "Daily users", 2000000)
                        ],
                    ),
                    _bullet(
                        "fixture.frontend.exp.current.b2",
                        "Migrated legacy jQuery codebase to React, reducing bundle size by 45%.",
                        tools=["React", "TypeScript", "Webpack"],
                        metrics=[
                            _metric("fixture.frontend.m2", "Bundle reduction", 45, "%")
                        ],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        projects=[
            ProjectEntry(
                id="fixture.frontend.project",
                name="Component Library",
                role="Lead Developer",
                role_type=RoleType.LEAD,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-06"),
                summary="Created internal React component library used by 8 teams.",
                tools=["React", "Storybook", "TypeScript"],
                bullets=[
                    _bullet(
                        "fixture.frontend.project.b1",
                        "Built 40+ reusable components with full TypeScript support.",
                        tools=["React", "TypeScript", "Storybook"],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        skills=[
            SkillEntry(
                id="fixture.frontend.skill.react",
                name="React",
                category="frontend",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            ),
            SkillEntry(
                id="fixture.frontend.skill.ts",
                name="TypeScript",
                category="frontend",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            ),
            SkillEntry(
                id="fixture.frontend.skill.graphql",
                name="GraphQL",
                category="frontend",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            ),
        ],
    )


def backend_heavy_profile() -> MasterProfile:
    """Profile suitable for backend-heavy roles."""
    return MasterProfile(
        id="fixture.backend",
        personal_profile=PersonalProfile(
            id="fixture.backend.person",
            full_name="Taylor Backend",
            headline="Staff Backend Platform Engineer",
            summary="Backend platform engineer focused on architecture, cloud infrastructure, reliability.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.STAFF,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["backend", "platform", "cloud"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.backend.exp.current",
                organization="InfraScale",
                title="Staff Backend Platform Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.STAFF,
                start_date=PartialDate(raw_value="2022-03"),
                current=True,
                tools=["Python", "PostgreSQL", "AWS", "Kubernetes", "Terraform"],
                bullets=[
                    _bullet(
                        "fixture.backend.exp.current.b1",
                        "Architected AWS and Kubernetes platform services reducing deployment time 68%.",
                        tools=["AWS", "Kubernetes", "Terraform"],
                        metrics=[
                            _metric(
                                "fixture.backend.m1",
                                "Deployment time reduction",
                                68,
                                "%",
                            )
                        ],
                    ),
                    _bullet(
                        "fixture.backend.exp.current.b2",
                        "Led Python API reliability work reducing Sev-1 incidents 42%.",
                        tools=["Python", "PostgreSQL", "AWS"],
                        metrics=[
                            _metric("fixture.backend.m2", "Incident reduction", 42, "%")
                        ],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        projects=[
            ProjectEntry(
                id="fixture.backend.project",
                name="Platform Portal",
                role="Lead Engineer",
                role_type=RoleType.LEAD,
                start_date=PartialDate(raw_value="2023-05"),
                summary="Built internal developer portal for cloud environment requests.",
                tools=["Python", "React", "AWS"],
                bullets=[
                    _bullet(
                        "fixture.backend.project.b1",
                        "Cut environment setup time by 80% for backend teams.",
                        tools=["Python", "React", "AWS"],
                        metrics=[
                            _metric(
                                "fixture.backend.m3", "Setup time reduction", 80, "%"
                            )
                        ],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        skills=[
            SkillEntry(
                id="fixture.backend.skill.python", name="Python", category="backend"
            ),
            SkillEntry(id="fixture.backend.skill.aws", name="AWS", category="cloud"),
            SkillEntry(
                id="fixture.backend.skill.postgres",
                name="PostgreSQL",
                category="database",
            ),
        ],
    )


def leadership_profile() -> MasterProfile:
    """Profile suitable for leadership roles."""
    return MasterProfile(
        id="fixture.leadership",
        personal_profile=PersonalProfile(
            id="fixture.leadership.person",
            full_name="Jordan Lead",
            headline="Engineering Manager",
            summary="Engineering leader with track record of building and scaling teams.",
            role_type=RoleType.MANAGER,
            seniority_level=SeniorityLevel.MANAGER,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.STRONG,
            domain_tags=["leadership", "management", "strategy"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.leadership.exp.current",
                organization="TechCorp",
                title="Engineering Manager",
                role_type=RoleType.MANAGER,
                seniority_level=SeniorityLevel.MANAGER,
                start_date=PartialDate(raw_value="2021-06"),
                current=True,
                tools=["Agile", "Jira", "Confluence"],
                bullets=[
                    _bullet(
                        "fixture.leadership.exp.current.b1",
                        "Led team of 12 engineers delivering 3 major product releases in 18 months.",
                        metrics=[_metric("fixture.leadership.m1", "Team size", 12)],
                    ),
                    _bullet(
                        "fixture.leadership.exp.current.b2",
                        "Drove 40% improvement in on-call incident response time through process changes.",
                        metrics=[
                            _metric(
                                "fixture.leadership.m2", "Response improvement", 40, "%"
                            )
                        ],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        skills=[
            SkillEntry(
                id="fixture.leadership.skill.agile", name="Agile", category="process"
            ),
            SkillEntry(
                id="fixture.leadership.skill.strategy",
                name="Technical Strategy",
                category="leadership",
            ),
        ],
    )


def project_gap_fill_profile() -> MasterProfile:
    """Profile with strong projects but potential experience gaps."""
    return MasterProfile(
        id="fixture.projects",
        personal_profile=PersonalProfile(
            id="fixture.projects.person",
            full_name="Casey Projects",
            headline="Software Engineer",
            summary="Engineer with strong project portfolio and practical skills.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.MID,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["fullstack", "projects"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.projects.exp.1",
                organization="StartupCo",
                title="Software Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.MID,
                start_date=PartialDate(raw_value="2023-01"),
                current=True,
                tools=["Python", "JavaScript", "SQL"],
                bullets=[
                    _bullet(
                        "fixture.projects.exp.1.b1",
                        "Built customer-facing features serving 50K users.",
                        tools=["Python", "React"],
                        metrics=[_metric("fixture.projects.m1", "Users", 50000)],
                    ),
                ],
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.MODERATE,
            ),
        ],
        projects=[
            ProjectEntry(
                id="fixture.projects.project.1",
                name="Open Source CLI Tool",
                role="Creator",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                start_date=PartialDate(raw_value="2023-09"),
                summary="Built CLI tool for developer productivity with 500+ GitHub stars.",
                tools=["Go", "Python"],
                bullets=[
                    _bullet(
                        "fixture.projects.project.b1",
                        "500+ GitHub stars, used by 200+ developers.",
                        metrics=[_metric("fixture.projects.m2", "GitHub stars", 500)],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ProjectEntry(
                id="fixture.projects.project.2",
                name="Personal Blog Platform",
                role="Developer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                start_date=PartialDate(raw_value="2022-06"),
                summary="Built high-performance blog platform with SEO optimization.",
                tools=["Next.js", "Node.js", "PostgreSQL"],
                bullets=[
                    _bullet(
                        "fixture.projects.project.2.b1",
                        "Achieved 95+ Lighthouse score across all metrics.",
                    )
                ],
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.MODERATE,
            ),
        ],
        skills=[
            SkillEntry(
                id="fixture.projects.skill.python", name="Python", category="backend"
            ),
            SkillEntry(
                id="fixture.projects.skill.js", name="JavaScript", category="frontend"
            ),
            SkillEntry(id="fixture.projects.skill.go", name="Go", category="backend"),
        ],
    )


def thin_evidence_profile() -> MasterProfile:
    """Profile with minimal evidence - thin profile scenario."""
    return MasterProfile(
        id="fixture.thin",
        personal_profile=PersonalProfile(
            id="fixture.thin.person",
            full_name="Sam Thin",
            headline="Junior Developer",
            summary="Junior developer with limited but relevant experience.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.JUNIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.LIGHT,
            domain_tags=["development"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.thin.exp.1",
                organization="SmallAgency",
                title="Junior Developer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.JUNIOR,
                start_date=PartialDate(raw_value="2024-01"),
                current=True,
                tools=["JavaScript", "HTML", "CSS"],
                bullets=[
                    _bullet(
                        "fixture.thin.exp.1.b1",
                        "Maintained and updated client websites.",
                        tools=["JavaScript", "HTML", "CSS"],
                    ),
                ],
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.LIGHT,
            ),
        ],
        skills=[
            SkillEntry(
                id="fixture.thin.skill.js", name="JavaScript", category="frontend"
            ),
            SkillEntry(id="fixture.thin.skill.html", name="HTML", category="frontend"),
        ],
    )


GOLD_TEST_CASES: dict[str, GoldTestCase] = {
    "frontend_heavy": GoldTestCase(
        key="frontend_heavy",
        role_type="frontend",
        seniority="senior",
        required_skills=["React", "TypeScript", "GraphQL"],
        profile=frontend_heavy_profile(),
        expected_keywords=["frontend", "React", "TypeScript", "senior"],
        expected_selected_experiences=["fixture.frontend.exp.current"],
        expected_selected_projects=["fixture.frontend.project"],
        expected_selected_skills=["React", "TypeScript", "GraphQL"],
    ),
    "backend_heavy": GoldTestCase(
        key="backend_heavy",
        role_type="backend",
        seniority="senior",
        required_skills=["Python", "AWS", "PostgreSQL"],
        profile=backend_heavy_profile(),
        expected_keywords=["backend", "Python", "AWS", "senior"],
        expected_selected_experiences=["fixture.backend.exp.current"],
        expected_selected_projects=["fixture.backend.project"],
        expected_selected_skills=["Python", "AWS", "PostgreSQL"],
    ),
    "leadership": GoldTestCase(
        key="leadership",
        role_type="management",
        seniority="manager",
        required_skills=["Agile", "Team Leadership", "Strategy"],
        profile=leadership_profile(),
        expected_keywords=["management", "Agile", "manager"],
        expected_selected_experiences=["fixture.leadership.exp.current"],
        expected_selected_projects=[],
        expected_selected_skills=["Agile", "Technical Strategy"],
    ),
    "project_gap_fill": GoldTestCase(
        key="project_gap_fill",
        role_type="fullstack",
        seniority="mid",
        required_skills=["Python", "JavaScript", "Go"],
        profile=project_gap_fill_profile(),
        expected_keywords=["fullstack", "Python", "Go", "mid"],
        expected_selected_experiences=["fixture.projects.exp.1"],
        expected_selected_projects=[
            "fixture.projects.project.1",
            "fixture.projects.project.2",
        ],
        expected_selected_skills=["Python", "JavaScript", "Go"],
    ),
    "thin_evidence": GoldTestCase(
        key="thin_evidence",
        role_type="frontend",
        seniority="junior",
        required_skills=["JavaScript", "HTML", "CSS"],
        profile=thin_evidence_profile(),
        expected_keywords=["frontend", "JavaScript", "junior"],
        expected_selected_experiences=["fixture.thin.exp.1"],
        expected_selected_projects=[],
        expected_selected_skills=["JavaScript"],
    ),
}


def get_gold_test_case(key: str) -> GoldTestCase:
    """Get a gold test case by key."""
    if key not in GOLD_TEST_CASES:
        raise ValueError(
            f"Unknown gold test case: {key}. Available: {list(GOLD_TEST_CASES.keys())}"
        )
    return GOLD_TEST_CASES[key]
