from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import Field

from resume_optimizer.generation.contracts import QualityDimension
from resume_optimizer.job_models import NormalizedJobAnalysis, NormalizedSkillRequirement, SkillPriority
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
    StrictModel,
    VerifiedStatus,
)
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode

from .phase2_candidate_profiles import (
    cert_heavy_profile,
    duplicate_heavy_messy_profile,
    frontend_heavy_engineer_profile,
    leadership_heavy_profile,
    project_selection_profile,
    sparse_junior_profile,
    strong_backend_engineer_profile,
)

DEFAULT_PHASE5_EVAL_TODAY = date(2026, 4, 9)


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


class Phase5EvalExpectedGenerationShape(StrictModel):
    require_summary: bool = True
    min_experience_items: int = Field(default=0, ge=0)
    min_project_items: int = Field(default=0, ge=0)
    min_skill_groups: int = Field(default=0, ge=0)
    require_skill_section: bool = False
    require_certification_section: bool = False
    require_omitted_items: bool = False


class Phase5EvalExpectedQualityRules(StrictModel):
    max_summary_words: int = Field(default=32, ge=1)
    max_skill_lines: int = Field(default=3, ge=1)
    allow_hard_failures: bool = False
    allow_summary_fallback: bool = False
    allow_bullet_fallbacks: bool = False
    require_omission_traceability: bool = False
    required_warning_dimensions: list[QualityDimension] = Field(default_factory=list)
    required_style_terms_any: list[str] = Field(default_factory=list)


class Phase5EvalRedFlags(StrictModel):
    banned_phrases: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Phase5EvalFixtureCase:
    case_id: str
    description: str
    build_profile: callable
    job_analysis: NormalizedJobAnalysis
    role_family: FunctionalRoleFamily
    organizational_role_mode: OrganizationalRoleMode
    target_page_count: int
    summary_text: str
    bullet_text_overrides: dict[str, str]
    expected_generation_shape: Phase5EvalExpectedGenerationShape
    expected_quality_rules: Phase5EvalExpectedQualityRules
    red_flags: Phase5EvalRedFlags


def load_phase5_eval_cases() -> list[Phase5EvalFixtureCase]:
    return [
        Phase5EvalFixtureCase(
            case_id="backend_senior_ic",
            description="Senior backend IC path with strong systems, reliability, and platform evidence.",
            build_profile=strong_backend_engineer_profile,
            job_analysis=_backend_job_analysis(),
            role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text=(
                "Backend engineer building Python services on AWS with reliability, platform automation, "
                "and measurable delivery improvements."
            ),
            bullet_text_overrides={
                "fixture.backend.exp.current.b1": "Architected Python platform services on AWS and Kubernetes with Terraform, cutting deployment time 68%.",
                "fixture.backend.exp.current.b2": "Improved Python and PostgreSQL API reliability on AWS, reducing Sev-1 incidents 42% and p95 latency 33%.",
                "fixture.backend.exp.current.b3": "Built CI/CD and self-serve provisioning workflows used by 14 engineering teams.",
                "fixture.backend.exp.prev.b1": "Built Go payment services with Redis caching and PostgreSQL, increasing checkout throughput 27%.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=2,
                min_skill_groups=1,
                require_skill_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["backend", "services", "reliability"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["results-driven", "dynamic professional", "10 years", "global"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="frontend_lead",
            description="Frontend lead path emphasizing interfaces, accessibility, design systems, and delivery leadership.",
            build_profile=frontend_heavy_engineer_profile,
            job_analysis=_frontend_lead_job_analysis(),
            role_family=FunctionalRoleFamily.FRONTEND,
            organizational_role_mode=OrganizationalRoleMode.TECH_LEAD,
            target_page_count=1,
            summary_text=(
                "Frontend lead shipping React and TypeScript interfaces with accessibility, experimentation, "
                "and design-system ownership."
            ),
            bullet_text_overrides={
                "fixture.frontend.exp.b1": "Built React, TypeScript, and Next.js onboarding flows that increased activation 21% and improved accessibility outcomes.",
                "fixture.frontend.exp.b2": "Partnered with product and design to run onboarding and pricing UX experiments.",
                "fixture.frontend.exp.b3": "Owned a shared design system across customer-facing web applications.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=1,
                min_skill_groups=1,
                require_skill_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["frontend", "accessibility", "design system", "interfaces"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["microservices", "terraform", "results-driven"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="devops_platform",
            description="Platform and DevOps case with automation, deployment, infra, and certification relevance.",
            build_profile=cert_heavy_profile,
            job_analysis=_devops_job_analysis(),
            role_family=FunctionalRoleFamily.PLATFORM,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text=(
                "Platform engineer automating AWS and Terraform workflows with Kubernetes-backed infrastructure "
                "and operational reliability focus."
            ),
            bullet_text_overrides={
                "fixture.certs.exp.b1": "Automated AWS, Terraform, and Kubernetes provisioning for internal platforms, reducing manual setup time 70%.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=1,
                min_skill_groups=1,
                require_skill_section=True,
                require_certification_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["platform", "automation", "infrastructure", "reliability"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["product roadmap", "user journey", "cutting-edge"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="data_analytics",
            description="Data role with pipelines, modeling, analytics, and experimentation evidence.",
            build_profile=data_analytics_profile,
            job_analysis=_data_job_analysis(),
            role_family=FunctionalRoleFamily.DATA,
            organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text=(
                "Data engineer building Python and SQL pipelines with warehouse modeling, experimentation support, "
                "and analytics delivery."
            ),
            bullet_text_overrides={
                "fixture.data.exp.current.b1": "Built Python and dbt pipelines into Snowflake, reducing refresh lag 63%.",
                "fixture.data.exp.current.b2": "Modeled SQL datasets in Snowflake for product and finance reporting with Looker.",
                "fixture.data.project.exp.b1": "Built an experimentation readout workflow that cut manual analysis time 45%.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=1,
                min_project_items=1,
                min_skill_groups=1,
                require_skill_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["data", "pipelines", "analytics", "modeling"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["machine learning", "world-class", "10 years"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="engineering_management",
            description="Engineering management case with delivery, team development, and stakeholder alignment evidence.",
            build_profile=leadership_heavy_profile,
            job_analysis=_management_job_analysis(),
            role_family=FunctionalRoleFamily.PLATFORM,
            organizational_role_mode=OrganizationalRoleMode.PEOPLE_MANAGER,
            target_page_count=1,
            summary_text=(
                "Engineering manager leading delivery, team development, and stakeholder alignment across platform work."
            ),
            bullet_text_overrides={
                "fixture.leadership.exp.b1": "Managed 11 engineers, mentored new tech leads, and led AWS-backed platform roadmap planning with product and operations.",
                "fixture.leadership.exp.b2": "Owned quarterly delivery across four teams and improved roadmap completion to 93%.",
                "fixture.leadership.exp.b3": "Drove incident review and reliability planning that reduced repeat incidents 31%.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=1,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["delivery", "team", "stakeholder", "leadership"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["visionary", "thought leader", "results-driven"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="weak_match",
            description="Weak-match case should stay conservative and avoid inflated seniority or specialization claims.",
            build_profile=sparse_junior_profile,
            job_analysis=_weak_match_job_analysis(),
            role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text="Early-career engineer with Python experience supporting internal tooling.",
            bullet_text_overrides={
                "fixture.junior.exp.b1": "Supported internal tooling work in an early-career software engineering role.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=1,
                min_skill_groups=1,
                require_skill_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["internal", "tooling", "engineer"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["staff", "principal", "architecture", "10 years", "led"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="overlapping_experiences",
            description="Overlapping experience/project evidence should surface repetition warnings without losing traceability.",
            build_profile=duplicate_heavy_messy_profile,
            job_analysis=_overlap_job_analysis(),
            role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text=(
                "Backend engineer improving Python service performance and platform workflows across repeated latency-sensitive systems."
            ),
            bullet_text_overrides={
                "fixture.duplicate.exp1.b1": "Built Python API with Redis cache that reduced checkout latency 40%.",
                "fixture.duplicate.exp1.b2": "Built internal onboarding tooling for support workflows with Python.",
                "fixture.duplicate.exp2.b1": "Built Python API with Redis cache that reduced checkout latency 40%.",
                "fixture.duplicate.exp2.b2": "Architected AWS and Terraform deployment automation for regulated backend workloads.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=2,
                min_skill_groups=1,
                require_skill_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_warning_dimensions=[QualityDimension.REPETITION],
                required_style_terms_any=["backend", "python", "performance"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["world-class", "dynamic professional"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="many_projects",
            description="Project-heavy case should keep project coverage balanced and traceable.",
            build_profile=many_projects_profile,
            job_analysis=_many_projects_job_analysis(),
            role_family=FunctionalRoleFamily.FRONTEND,
            organizational_role_mode=OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text=(
                "Frontend engineer with portfolio projects spanning React interfaces, accessibility, and reusable UI systems."
            ),
            bullet_text_overrides={
                "fixture.projects.exp.base.b1": "Built React interfaces for internal dashboards with reusable TypeScript components.",
                "fixture.projects.project.ds.b1": "Built a React and TypeScript design system demo with reusable components and accessibility coverage.",
                "fixture.projects.project.perf.b1": "Built a React, TypeScript, and Next.js performance playground that improved lighthouse performance 24%.",
                "fixture.projects.project.content.b1": "Built a content workflow UI that reduced editor setup time 38%.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=1,
                min_project_items=2,
                min_skill_groups=1,
                require_skill_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["frontend", "react", "ui", "accessibility"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["terraform", "microservices", "results-driven"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="sparse_certifications",
            description="Sparse-certification case should keep the certification section compact and truthful.",
            build_profile=strong_backend_engineer_profile,
            job_analysis=_sparse_cert_job_analysis(),
            role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text=(
                "Backend engineer with AWS platform experience, API reliability work, and one relevant cloud certification."
            ),
            bullet_text_overrides={
                "fixture.backend.exp.current.b1": "Architected Python platform services on AWS and Kubernetes with Terraform, cutting deployment time 68%.",
                "fixture.backend.exp.current.b2": "Improved Python and PostgreSQL API reliability on AWS, reducing Sev-1 incidents 42% and p95 latency 33%.",
                "fixture.backend.exp.current.b3": "Built CI/CD automation and self-serve provisioning used by 14 engineering teams.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=1,
                min_skill_groups=1,
                require_skill_section=True,
                require_certification_section=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                required_style_terms_any=["aws", "backend", "reliability"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["multiple certifications", "principal architect", "global"],
            ),
        ),
        Phase5EvalFixtureCase(
            case_id="page_budget_constrained",
            description="One-page constrained case should omit lower-priority content with explicit omission tracking.",
            build_profile=page_budget_constrained_profile,
            job_analysis=_backend_job_analysis(),
            role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            target_page_count=1,
            summary_text=(
                "Backend engineer with Python, AWS, and platform reliability experience across delivery-focused systems."
            ),
            bullet_text_overrides={
                "fixture.backend.exp.current.b1": "Architected Python platform services on AWS and Kubernetes with Terraform, cutting deployment time 68%.",
                "fixture.backend.exp.current.b2": "Improved Python and PostgreSQL API reliability on AWS, reducing Sev-1 incidents 42% and p95 latency 33%.",
                "fixture.backend.exp.current.b3": "Built CI/CD and self-serve provisioning workflows used by 14 engineering teams.",
                "fixture.backend.exp.prev.b1": "Built Go payment services with Redis caching and PostgreSQL, increasing checkout throughput 27%.",
                "fixture.backend.exp.extra.b1": "Architected Python platform services on AWS and Kubernetes with Terraform, improving deployment speed 68%.",
                "fixture.backend.exp.extra.b2": "Improved Python and PostgreSQL API reliability on AWS, reducing Sev-1 incidents 42% and p95 latency 33%.",
                "fixture.backend.exp.extra.b3": "Built platform automation for CI/CD and service provisioning across engineering teams.",
            },
            expected_generation_shape=Phase5EvalExpectedGenerationShape(
                min_experience_items=2,
                min_skill_groups=1,
                require_skill_section=True,
                require_omitted_items=True,
            ),
            expected_quality_rules=Phase5EvalExpectedQualityRules(
                require_omission_traceability=True,
                required_style_terms_any=["backend", "aws", "reliability"],
            ),
            red_flags=Phase5EvalRedFlags(
                banned_phrases=["2-page", "extensive background", "dynamic professional"],
            ),
        ),
    ]


def data_analytics_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.data",
        personal_profile=PersonalProfile(
            id="fixture.data.person",
            full_name="Dana Data",
            headline="Data Engineer",
            summary="Data engineer focused on pipelines, modeling, and experiment analysis.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["data", "analytics"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.data.exp.current",
                organization="InsightCo",
                title="Data Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2022-01"),
                current=True,
                tools=["Python", "SQL", "dbt", "Snowflake", "Looker"],
                bullets=[
                    _bullet(
                        "fixture.data.exp.current.b1",
                        "Built Python and dbt pipelines into Snowflake and reduced dashboard refresh lag 63%.",
                        tools=["Python", "dbt", "Snowflake"],
                        metrics=[_metric("fixture.data.metric.1", "Refresh lag reduction", 63, "%")],
                    ),
                    _bullet(
                        "fixture.data.exp.current.b2",
                        "Modeled SQL datasets for finance and product reporting in Looker.",
                        tools=["SQL", "Looker", "Snowflake"],
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        projects=[
            ProjectEntry(
                id="fixture.data.project.exp",
                name="Experimentation Readout Pipeline",
                role="Data Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-01"),
                end_date=PartialDate(raw_value="2024-07"),
                summary="Built a readout workflow for A/B test analysis and experiment reporting.",
                tools=["Python", "SQL", "Looker"],
                bullets=[
                    _bullet(
                        "fixture.data.project.exp.b1",
                        "Built an experimentation readout workflow that reduced manual analysis time 45%.",
                        tools=["Python", "SQL", "Looker"],
                        metrics=[_metric("fixture.data.metric.2", "Manual analysis reduction", 45, "%")],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        skills=[
            SkillEntry(
                id="fixture.data.skill.python",
                name="Python",
                category="data",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.data.skill.sql",
                name="SQL",
                category="data",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.data.skill.dbt",
                name="dbt",
                category="data",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )


def many_projects_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.projects",
        personal_profile=PersonalProfile(
            id="fixture.projects.person",
            full_name="Parker Portfolio",
            headline="Frontend Engineer",
            summary="Frontend engineer with product work and several portfolio projects.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
            domain_tags=["frontend", "product"],
        ),
        experience=[
            ExperienceEntry(
                id="fixture.projects.exp.base",
                organization="ClientUI",
                title="Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-02"),
                current=True,
                tools=["React", "TypeScript"],
                bullets=[
                    _bullet(
                        "fixture.projects.exp.base.b1",
                        "Built React interfaces for internal dashboards with reusable TypeScript components.",
                        tools=["React", "TypeScript"],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        projects=[
            ProjectEntry(
                id="fixture.projects.project.ds",
                name="Accessible Design System Demo",
                role="Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-01"),
                end_date=PartialDate(raw_value="2024-04"),
                summary="Built a React design system demo for reusable accessible components.",
                tools=["React", "TypeScript"],
                bullets=[
                    _bullet(
                        "fixture.projects.project.ds.b1",
                        "Built a React design system demo with reusable components and accessibility coverage.",
                        tools=["React", "TypeScript"],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ProjectEntry(
                id="fixture.projects.project.perf",
                name="Performance Playground",
                role="Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-05"),
                end_date=PartialDate(raw_value="2024-08"),
                summary="Built a Next.js performance playground for interactive page speed tuning.",
                tools=["React", "TypeScript", "Next.js"],
                bullets=[
                    _bullet(
                        "fixture.projects.project.perf.b1",
                        "Built a Next.js performance playground that improved lighthouse performance 24%.",
                        tools=["React", "TypeScript", "Next.js"],
                        metrics=[_metric("fixture.projects.metric.1", "Performance improvement", 24, "%")],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ProjectEntry(
                id="fixture.projects.project.content",
                name="Content Workflow Studio",
                role="Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-09"),
                end_date=PartialDate(raw_value="2025-01"),
                summary="Built a UI workflow for content editors and structured publishing.",
                tools=["React", "TypeScript"],
                bullets=[
                    _bullet(
                        "fixture.projects.project.content.b1",
                        "Built a content workflow UI that reduced editor setup time 38%.",
                        tools=["React", "TypeScript"],
                        metrics=[_metric("fixture.projects.metric.2", "Setup reduction", 38, "%")],
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
        skills=[
            SkillEntry(
                id="fixture.projects.skill.react",
                name="React",
                category="frontend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.projects.skill.typescript",
                name="TypeScript",
                category="frontend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            SkillEntry(
                id="fixture.projects.skill.next",
                name="Next.js",
                category="frontend",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )


def page_budget_constrained_profile() -> MasterProfile:
    profile = strong_backend_engineer_profile()
    extra_experience = profile.experience[0].model_copy(
        update={
            "id": "fixture.backend.exp.extra",
            "organization": "ScaleGrid",
            "title": "Platform Engineer",
            "start_date": PartialDate(raw_value="2018-01"),
            "end_date": PartialDate(raw_value="2018-12"),
            "current": False,
            "bullets": [
                bullet.model_copy(
                    update={
                        "id": f"fixture.backend.exp.extra.b{index + 1}",
                        "metrics": [
                            metric.model_copy(
                                update={"id": f"fixture.backend.exp.extra.metric.{index + 1}.{metric_index + 1}"}
                            )
                            for metric_index, metric in enumerate(bullet.metrics)
                        ],
                    }
                )
                for index, bullet in enumerate(profile.experience[0].bullets)
            ],
        }
    )
    extra_project = profile.projects[0].model_copy(
        update={
            "id": "fixture.backend.project.extra",
            "name": "Service Catalog",
            "bullets": [
                bullet.model_copy(
                    update={
                        "id": "fixture.backend.project.extra.b1",
                        "metrics": [
                            metric.model_copy(update={"id": "fixture.backend.project.extra.metric.1"})
                            for metric in bullet.metrics
                        ],
                    }
                )
                for bullet in profile.projects[0].bullets
            ],
        }
    )
    return profile.model_copy(
        update={
            "experience": [*profile.experience, extra_experience],
            "projects": [*profile.projects, extra_project],
        }
    )


def _backend_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.STAFF,
        industry_domain="cloud",
        technical_skills=["Python", "AWS", "Kubernetes", "Terraform", "PostgreSQL"],
        soft_skills=["Leadership", "Stakeholder Management"],
        key_action_verbs=["architect", "optimize", "automate"],
        must_have_requirements=[
            "Architect backend systems on AWS",
            "Improve reliability and delivery for platform services",
        ],
        nice_to_have_requirements=["Support developer platform adoption"],
        company_culture_signals=["ownership", "delivery", "platform"],
        years_experience_required=7,
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Kubernetes", priority=SkillPriority.IMPORTANT),
            NormalizedSkillRequirement(skill_name="Terraform", priority=SkillPriority.IMPORTANT),
        ],
    )


def _frontend_lead_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.LEAD,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="product",
        technical_skills=["React", "TypeScript", "Accessibility"],
        soft_skills=["Collaboration", "Leadership"],
        key_action_verbs=["build", "lead", "improve"],
        must_have_requirements=[
            "Lead frontend delivery for customer-facing interfaces",
            "Improve accessibility and design-system quality",
        ],
        nice_to_have_requirements=["Partner with product and design on experimentation"],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="React", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="TypeScript", priority=SkillPriority.CORE),
        ],
    )


def _devops_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="cloud",
        technical_skills=["AWS", "Terraform", "Kubernetes", "CI/CD"],
        soft_skills=["Ownership"],
        key_action_verbs=["automate", "deploy", "stabilize"],
        must_have_requirements=[
            "Automate infrastructure workflows",
            "Improve deployment reliability for internal platforms",
        ],
        nice_to_have_requirements=["Hold relevant cloud certifications"],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Terraform", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Kubernetes", priority=SkillPriority.IMPORTANT),
        ],
    )


def _data_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="data",
        technical_skills=["Python", "SQL", "dbt", "Snowflake", "Looker"],
        soft_skills=["Collaboration"],
        key_action_verbs=["build", "model", "analyze"],
        must_have_requirements=[
            "Build reliable data pipelines and warehouse models",
            "Support analytics and experimentation readouts",
        ],
        nice_to_have_requirements=["Partner with product and finance"],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="SQL", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="dbt", priority=SkillPriority.IMPORTANT),
        ],
    )


def _management_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.MANAGER,
        seniority_level=SeniorityLevel.DIRECTOR,
        industry_domain="platform",
        technical_skills=["AWS", "Kubernetes"],
        soft_skills=["Leadership", "Stakeholder Management", "Mentoring"],
        key_action_verbs=["lead", "mentor", "deliver"],
        must_have_requirements=[
            "Lead engineering teams through delivery planning",
            "Partner with stakeholders on roadmap execution",
        ],
        nice_to_have_requirements=["Improve team effectiveness and reliability"],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Leadership", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Stakeholder Management", priority=SkillPriority.IMPORTANT),
        ],
    )


def _weak_match_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="cloud",
        technical_skills=["Python", "AWS", "Kubernetes"],
        key_action_verbs=["architect", "optimize"],
        must_have_requirements=[
            "Build backend services on cloud infrastructure",
        ],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.IMPORTANT),
        ],
    )


def _overlap_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="commerce",
        technical_skills=["Python", "Redis", "AWS"],
        must_have_requirements=[
            "Improve backend performance for transaction systems",
            "Support deployment and platform workflows",
        ],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Redis", priority=SkillPriority.IMPORTANT),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.IMPORTANT),
        ],
    )


def _many_projects_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="product",
        technical_skills=["React", "TypeScript", "Next.js"],
        must_have_requirements=[
            "Show portfolio-quality frontend projects",
            "Build accessible and reusable UI systems",
        ],
        nice_to_have_requirements=["Demonstrate performance-oriented frontend work"],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="React", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="TypeScript", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Next.js", priority=SkillPriority.IMPORTANT),
        ],
    )


def _sparse_cert_job_analysis() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="cloud",
        technical_skills=["AWS", "Python", "Terraform"],
        must_have_requirements=[
            "Build backend services on AWS",
            "Hold or work toward a cloud certification",
        ],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
        ],
    )
