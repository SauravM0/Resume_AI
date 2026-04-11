from __future__ import annotations

from dataclasses import dataclass

from resume_optimizer.job_models import (
    NormalizedJobAnalysis,
    NormalizedSkillRequirement,
    SkillPriority,
)
from resume_optimizer.models import (
    AwardEntry,
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


def _metric(metric_id: str, label: str, value: int | float, unit: str | None = None) -> MetricEntry:
    return MetricEntry(id=metric_id, label=label, value=value, unit=unit)


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


@dataclass(frozen=True)
class Phase2FixtureCase:
    key: str
    profile: MasterProfile


def strong_backend_engineer_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.backend",
        personal_profile=PersonalProfile(
            id="fixture.backend.person",
            full_name="Taylor Backend",
            headline="Staff Backend Platform Engineer",
            summary="Backend platform engineer focused on architecture, cloud infrastructure, reliability, and delivery execution.",
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
                        "Architected AWS and Kubernetes platform services with Terraform, reducing deployment time 68% across backend systems.",
                        tools=["AWS", "Kubernetes", "Terraform", "Python"],
                        metrics=[_metric("fixture.backend.metric.1", "Deployment time reduction", 68, "%")],
                    ),
                    _bullet(
                        "fixture.backend.exp.current.b2",
                        "Led Python and PostgreSQL API reliability work that reduced Sev-1 incidents 42% and improved p95 latency 33%.",
                        tools=["Python", "PostgreSQL", "AWS"],
                        metrics=[
                            _metric("fixture.backend.metric.2", "Incident reduction", 42, "%"),
                            _metric("fixture.backend.metric.3", "Latency improvement", 33, "%"),
                        ],
                    ),
                    _bullet(
                        "fixture.backend.exp.current.b3",
                        "Owned internal platform automation for CI/CD and self-serve service provisioning used by 14 engineering teams.",
                        tools=["GitHub Actions", "Terraform", "Kubernetes"],
                        metrics=[_metric("fixture.backend.metric.4", "Teams enabled", 14)],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ExperienceEntry(
                id="fixture.backend.exp.prev",
                organization="PayLayer",
                title="Senior Backend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2019-01"),
                end_date=PartialDate(raw_value="2022-02"),
                tools=["Go", "Redis", "PostgreSQL", "Docker"],
                bullets=[
                    _bullet(
                        "fixture.backend.exp.prev.b1",
                        "Built Go payment services with Redis caching, increasing checkout throughput 27% while maintaining audit-compliant controls.",
                        tools=["Go", "Redis", "PostgreSQL"],
                        metrics=[_metric("fixture.backend.metric.5", "Throughput increase", 27, "%")],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        projects=[
            ProjectEntry(
                id="fixture.backend.project",
                name="Internal Platform Portal",
                role="Lead Engineer",
                role_type=RoleType.LEAD,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-05"),
                end_date=PartialDate(raw_value="2023-12"),
                summary="Built an internal developer portal on Python and React to automate cloud environment requests and service onboarding.",
                tools=["Python", "React", "AWS"],
                bullets=[
                    _bullet(
                        "fixture.backend.project.b1",
                        "Built Python APIs and React workflows that cut environment setup time by 80% for backend teams.",
                        tools=["Python", "React", "AWS"],
                        metrics=[_metric("fixture.backend.metric.6", "Setup time reduction", 80, "%")],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        certifications=[
            CertificationEntry(
                id="fixture.backend.cert.aws",
                name="AWS Certified Solutions Architect Associate",
                issuer="Amazon Web Services",
                issue_date=PartialDate(raw_value="2024-04"),
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
                domain_tags=["cloud", "platform"],
            )
        ],
        awards=[
            AwardEntry(
                id="fixture.backend.award",
                title="Platform Excellence Award",
                awarder="InfraScale",
                award_date=PartialDate(raw_value="2024-12"),
                summary="Recognized for leading platform modernization and improving reliability across core backend services.",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        skills=[
            SkillEntry(
                id="fixture.backend.skill.python",
                name="Python",
                category="backend",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.STAFF,
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.backend.skill.aws",
                name="AWS",
                category="cloud",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )


def frontend_heavy_engineer_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.frontend",
        personal_profile=PersonalProfile(
            id="fixture.frontend.person",
            full_name="Jordan Frontend",
            headline="Senior Frontend Engineer",
            summary="Frontend engineer focused on design systems, accessibility, experimentation, and customer-facing product delivery.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["frontend", "product"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.frontend.exp",
                organization="AppStudio",
                title="Senior Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2021-02"),
                current=True,
                tools=["React", "TypeScript", "Next.js", "Figma"],
                bullets=[
                    _bullet(
                        "fixture.frontend.exp.b1",
                        "Built React and TypeScript onboarding flows that increased activation 21% and improved accessibility audit scores.",
                        tools=["React", "TypeScript", "Next.js"],
                        metrics=[_metric("fixture.frontend.metric.1", "Activation lift", 21, "%")],
                    ),
                    _bullet(
                        "fixture.frontend.exp.b2",
                        "Partnered with product and design stakeholders to run A/B experiments for pricing and onboarding UX.",
                        tools=["React", "Figma"],
                    ),
                    _bullet(
                        "fixture.frontend.exp.b3",
                        "Owned a shared design system used across customer-facing web applications.",
                        tools=["React", "TypeScript"],
                    ),
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
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.frontend.skill.typescript",
                name="TypeScript",
                category="frontend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )


def fullstack_mixed_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.fullstack",
        personal_profile=PersonalProfile(
            id="fixture.fullstack.person",
            full_name="Alex Fullstack",
            headline="Senior Fullstack Engineer",
            summary="Fullstack engineer shipping product features across backend services, frontend apps, analytics, and stakeholder collaboration.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["fullstack", "product", "analytics"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.fullstack.exp",
                organization="GrowthLab",
                title="Senior Fullstack Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2020-07"),
                current=True,
                tools=["React", "TypeScript", "Python", "PostgreSQL"],
                bullets=[
                    _bullet(
                        "fixture.fullstack.exp.b1",
                        "Built React and Python checkout workflows that increased conversion 18% and reduced support tickets 24%.",
                        tools=["React", "TypeScript", "Python", "PostgreSQL"],
                        metrics=[
                            _metric("fixture.fullstack.metric.1", "Conversion lift", 18, "%"),
                            _metric("fixture.fullstack.metric.2", "Support ticket reduction", 24, "%"),
                        ],
                    ),
                    _bullet(
                        "fixture.fullstack.exp.b2",
                        "Partnered with product managers and analysts to launch experimentation dashboards for pricing and onboarding analytics.",
                        tools=["React", "PostgreSQL"],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )


def leadership_heavy_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.leadership",
        personal_profile=PersonalProfile(
            id="fixture.leadership.person",
            full_name="Morgan Lead",
            headline="Engineering Manager",
            summary="Engineering leader focused on team execution, stakeholder management, mentoring, and platform delivery.",
            role_type=RoleType.MANAGER,
            seniority_level=SeniorityLevel.DIRECTOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["leadership", "platform"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.leadership.exp",
                organization="ScaleWorks",
                title="Engineering Manager",
                role_type=RoleType.MANAGER,
                seniority_level=SeniorityLevel.DIRECTOR,
                start_date=PartialDate(raw_value="2019-04"),
                current=True,
                tools=["AWS", "Kubernetes"],
                bullets=[
                    _bullet(
                        "fixture.leadership.exp.b1",
                        "Managed 11 engineers, mentored three new tech leads, and led cross-functional platform roadmap planning with product and operations leaders.",
                        tools=["AWS"],
                    ),
                    _bullet(
                        "fixture.leadership.exp.b2",
                        "Owned quarterly delivery execution across four teams and improved roadmap completion to 93%.",
                        metrics=[_metric("fixture.leadership.metric.1", "Roadmap completion", 93, "%")],
                    ),
                    _bullet(
                        "fixture.leadership.exp.b3",
                        "Drove incident review and reliability planning that cut repeat customer-facing incidents by 31%.",
                        metrics=[_metric("fixture.leadership.metric.2", "Repeat incident reduction", 31, "%")],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )


def sparse_junior_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.junior",
        personal_profile=PersonalProfile(
            id="fixture.junior.person",
            full_name="Sam Junior",
            headline="Software Engineer",
            summary="Early-career engineer.",
            role_type=RoleType.STUDENT,
            seniority_level=SeniorityLevel.JUNIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.WEAK,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.junior.exp",
                organization="TinyStartup",
                title="Software Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.JUNIOR,
                start_date=PartialDate(raw_value="2025-01"),
                current=True,
                bullets=[
                    _bullet(
                        "fixture.junior.exp.b1",
                        "Worked on internal tools.",
                        verified_status=VerifiedStatus.SELF_REPORTED,
                        evidence_strength=EvidenceStrength.WEAK,
                    )
                ],
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.WEAK,
            )
        ],
        education=[
            EducationEntry(
                id="fixture.junior.edu",
                institution="State University",
                degree="BS Computer Science",
                start_date=PartialDate(raw_value="2021-09"),
                end_date=PartialDate(raw_value="2025-05"),
                honors=["Dean's List"],
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.MODERATE,
            )
        ],
        skills=[
            SkillEntry(
                id="fixture.junior.skill.python",
                name="Python",
                category="backend",
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.WEAK,
            )
        ],
    )


def duplicate_heavy_messy_profile() -> MasterProfile:
    repeated = "Built Python API with Redis cache that reduced checkout latency 40%."
    return MasterProfile(
        id="fixture.duplicate",
        personal_profile=PersonalProfile(
            id="fixture.duplicate.person",
            full_name="Riley Messy",
            headline="Backend Engineer",
            summary="Backend engineer with repeated accomplishment wording across resume sections.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.duplicate.exp1",
                organization="ShopFast",
                title="Backend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2021-01"),
                end_date=PartialDate(raw_value="2023-08"),
                tools=["Python", "Redis"],
                bullets=[
                    _bullet(
                        "fixture.duplicate.exp1.b1",
                        repeated,
                        tools=["Python", "Redis"],
                        metrics=[_metric("fixture.duplicate.metric.1", "Latency reduction", 40, "%")],
                    ),
                    _bullet(
                        "fixture.duplicate.exp1.b2",
                        "Built internal onboarding tool with Python for support workflows.",
                        tools=["Python"],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ExperienceEntry(
                id="fixture.duplicate.exp2",
                organization="PayFlow",
                title="Senior Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-09"),
                current=True,
                tools=["Python", "Redis", "AWS"],
                bullets=[
                    _bullet(
                        "fixture.duplicate.exp2.b1",
                        repeated,
                        tools=["Python", "Redis"],
                        metrics=[_metric("fixture.duplicate.metric.2", "Latency reduction", 40, "%")],
                    ),
                    _bullet(
                        "fixture.duplicate.exp2.b2",
                        "Architected AWS platform deployment automation for regulated workloads.",
                        tools=["AWS", "Terraform"],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        projects=[
            ProjectEntry(
                id="fixture.duplicate.project",
                name="Checkout Rewrite",
                role="Lead Engineer",
                role_type=RoleType.LEAD,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-03"),
                end_date=PartialDate(raw_value="2023-12"),
                summary="Built Python API with Redis cache that reduced checkout latency 40% for checkout traffic.",
                tools=["Python", "Redis"],
                bullets=[
                    _bullet(
                        "fixture.duplicate.project.b1",
                        "Built Python API with Redis cache that reduced checkout latency by 40% for the checkout flow.",
                        tools=["Python", "Redis"],
                        metrics=[_metric("fixture.duplicate.metric.3", "Latency reduction", 40, "%")],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        certifications=[
            CertificationEntry(
                id="fixture.duplicate.cert.aws",
                name="AWS Certified Solutions Architect Associate",
                issuer="Amazon Web Services",
                issue_date=PartialDate(raw_value="2024-05"),
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        awards=[
            AwardEntry(
                id="fixture.duplicate.award",
                title="Engineering Excellence Award",
                awarder="ShopFast",
                summary="Recognized for reducing checkout latency 40% on the Python API platform.",
                award_date=PartialDate(raw_value="2024-01"),
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        skills=[
            SkillEntry(
                id="fixture.duplicate.skill.python",
                name="Python",
                category="backend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )


def cert_heavy_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.certs",
        personal_profile=PersonalProfile(
            id="fixture.certs.person",
            full_name="Casey Certified",
            headline="Cloud Platform Engineer",
            summary="Cloud platform engineer with strong certification coverage and operational automation experience.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["cloud", "platform"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.certs.exp",
                organization="CloudOps",
                title="Cloud Platform Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2021-10"),
                current=True,
                tools=["AWS", "Terraform", "Kubernetes"],
                bullets=[
                    _bullet(
                        "fixture.certs.exp.b1",
                        "Automated AWS and Terraform provisioning for internal platforms and reduced manual setup hours by 70%.",
                        tools=["AWS", "Terraform", "Kubernetes"],
                        metrics=[_metric("fixture.certs.metric.1", "Manual setup reduction", 70, "%")],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        certifications=[
            CertificationEntry(
                id="fixture.certs.cert.aws.arch",
                name="AWS Certified Solutions Architect Associate",
                issuer="Amazon Web Services",
                issue_date=PartialDate(raw_value="2024-01"),
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            CertificationEntry(
                id="fixture.certs.cert.aws.devops",
                name="AWS Certified DevOps Engineer Professional",
                issuer="Amazon Web Services",
                issue_date=PartialDate(raw_value="2024-06"),
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            CertificationEntry(
                id="fixture.certs.cert.cka",
                name="Certified Kubernetes Administrator",
                issuer="Cloud Native Computing Foundation",
                issue_date=PartialDate(raw_value="2023-11"),
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        skills=[
            SkillEntry(
                id="fixture.certs.skill.aws",
                name="AWS",
                category="cloud",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.certs.skill.terraform",
                name="Terraform",
                category="cloud",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )


def all_phase2_candidate_profile_fixtures() -> list[Phase2FixtureCase]:
    return [
        Phase2FixtureCase("strong_backend_engineer", strong_backend_engineer_profile()),
        Phase2FixtureCase("frontend_heavy_engineer", frontend_heavy_engineer_profile()),
        Phase2FixtureCase("fullstack_mixed_profile", fullstack_mixed_profile()),
        Phase2FixtureCase("leadership_heavy_profile", leadership_heavy_profile()),
        Phase2FixtureCase("sparse_junior_profile", sparse_junior_profile()),
        Phase2FixtureCase("duplicate_heavy_messy_profile", duplicate_heavy_messy_profile()),
        Phase2FixtureCase("cert_heavy_profile", cert_heavy_profile()),
    ]


def strong_backend_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.STAFF,
        industry_domain="cloud",
        technical_skills=["Python", "AWS", "Kubernetes", "Terraform", "PostgreSQL"],
        soft_skills=["Leadership", "Stakeholder Management"],
        key_action_verbs=["architect", "lead", "optimize", "automate"],
        must_have_requirements=[
            "Architect backend systems on AWS",
            "Improve reliability and delivery for platform services",
        ],
        nice_to_have_requirements=[
            "Mentor engineers",
            "Support developer platform adoption",
        ],
        company_culture_signals=["ownership", "delivery", "platform"],
        years_experience_required=7,
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Kubernetes", priority=SkillPriority.IMPORTANT),
            NormalizedSkillRequirement(skill_name="Terraform", priority=SkillPriority.IMPORTANT),
        ],
    )


def project_selection_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.project.selection",
        personal_profile=PersonalProfile(
            id="fixture.project.selection.person",
            full_name="Jordan Projects",
            headline="Software Engineer",
            summary="Engineer with backend experience and selective portfolio projects.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.project.selection.exp.backend",
                organization="CoreSystems",
                title="Backend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2022-02"),
                current=True,
                tools=["Python", "AWS", "Terraform"],
                bullets=[
                    BulletEntry(
                        id="fixture.project.selection.exp.backend.b1",
                        text="Built Python services on AWS with Terraform automation and improved reliability by 32%.",
                        tools=["Python", "AWS", "Terraform"],
                        metrics=[MetricEntry(id="fixture.project.selection.metric.1", label="Reliability improvement", value=32, unit="%")],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    ),
                    BulletEntry(
                        id="fixture.project.selection.exp.backend.b2",
                        text="Led backend delivery for platform APIs and deployment workflows.",
                        tools=["Python", "AWS"],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        projects=[
            ProjectEntry(
                id="fixture.project.selection.project.redundant",
                name="Deployment Automation Toolkit",
                role="Lead Engineer",
                role_type=RoleType.LEAD,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-01"),
                end_date=PartialDate(raw_value="2023-09"),
                summary="Built Python and Terraform deployment automation for AWS services.",
                tools=["Python", "AWS", "Terraform"],
                bullets=[
                    BulletEntry(
                        id="fixture.project.selection.project.redundant.b1",
                        text="Built Python and Terraform deployment automation for AWS services and reduced release toil 30%.",
                        tools=["Python", "AWS", "Terraform"],
                        metrics=[MetricEntry(id="fixture.project.selection.metric.2", label="Release toil reduction", value=30, unit="%")],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ProjectEntry(
                id="fixture.project.selection.project.portfolio",
                name="Interactive Design System Demo",
                role="Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-04"),
                end_date=PartialDate(raw_value="2024-11"),
                summary="Built a React and TypeScript portfolio project demonstrating reusable UI components and accessible interaction patterns.",
                tools=["React", "TypeScript"],
                bullets=[
                    BulletEntry(
                        id="fixture.project.selection.project.portfolio.b1",
                        text="Built a React and TypeScript design system demo with reusable components, accessibility checks, and polished UI states.",
                        tools=["React", "TypeScript"],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        skills=[
            SkillEntry(
                id="fixture.project.selection.skill.python",
                name="Python",
                category="backend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.project.selection.skill.react",
                name="React",
                category="frontend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )


def backend_project_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="cloud",
        technical_skills=["Python", "AWS", "Terraform"],
        must_have_requirements=[
            "Build Python services on AWS",
            "Automate infrastructure with Terraform",
        ],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Terraform", priority=SkillPriority.IMPORTANT),
        ],
    )


def frontend_project_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="product",
        technical_skills=["React", "TypeScript"],
        must_have_requirements=[
            "Build polished React user interfaces",
            "Use TypeScript for reusable frontend components",
        ],
        nice_to_have_requirements=[
            "Show portfolio-quality UI work",
        ],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="React", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="TypeScript", priority=SkillPriority.CORE),
        ],
    )


def phase3_eval_profile_fixture(profile_fixture_key: str) -> MasterProfile:
    fixtures = {
        "strong_backend_engineer": strong_backend_engineer_profile,
        "frontend_heavy_engineer": frontend_heavy_engineer_profile,
        "project_selection_profile": project_selection_profile,
    }
    try:
        return fixtures[profile_fixture_key]()
    except KeyError as exc:
        available = ", ".join(sorted(fixtures))
        raise KeyError(
            f"unknown phase3 eval profile fixture: {profile_fixture_key}; available: {available}"
        ) from exc
