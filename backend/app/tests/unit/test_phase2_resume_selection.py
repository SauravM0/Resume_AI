from __future__ import annotations

from backend.app.tests.fixtures.phase2_candidate_profiles import (
    strong_backend_engineer_profile,
    strong_backend_job_analysis,
)
from resume_optimizer.job_models import NormalizedJobAnalysis, NormalizedSkillRequirement, SkillPriority
from resume_optimizer.models import (
    BulletEntry,
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
from resume_optimizer.phase3_assembler import assemble_phase3_generation_payload
from resume_optimizer.ranking_service import build_phase2_ranking_artifacts


def test_multiple_bullets_from_same_experience_do_not_duplicate_ranked_experience_entries() -> None:
    artifacts = build_phase2_ranking_artifacts(
        strong_backend_job_analysis(),
        strong_backend_engineer_profile(),
    )

    ranked_source_ids = [
        item.source_item_id for item in artifacts.ranking_response.ranked_experiences
    ]

    assert ranked_source_ids == ["fixture.backend.exp.current"]
    assert len(ranked_source_ids) == len(set(ranked_source_ids))
    assert artifacts.ranking_response.atomic_evidence_scores


def test_resume_selection_selects_experience_entries_not_raw_fragments_only() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()
    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)

    selection = artifacts.selection_result.selected_experiences[0]
    audited_selection = artifacts.selection_result.resume_selection_decision.selected_experiences[0]
    payload = assemble_phase3_generation_payload(
        job_analysis,
        artifacts.selection_result,
        profile,
        artifacts.ranking_response,
    )

    assert selection.source_item_id == "fixture.backend.exp.current"
    assert len(selection.evidence_unit_ids) > 1
    assert audited_selection.selection_audit.selection_reason
    assert audited_selection.selection_audit.matched_requirements
    assert audited_selection.selection_audit.score_factors
    assert audited_selection.selection_audit.supporting_evidence_ids
    assert payload.selected_experiences[0].id == "fixture.backend.exp.current"
    assert len(payload.selected_experiences[0].evidence_unit_ids) > 1
    assert payload.selected_experiences[0].selection_reason
    assert payload.selected_experiences[0].matched_requirements
    assert payload.selected_experiences[0].supporting_evidence_ids
    assert payload.selected_experiences[0].score_factors


def test_broader_experience_can_outrank_narrow_spike_on_aggregate_value() -> None:
    profile = _aggregate_selection_profile()
    job_analysis = _aggregate_selection_job()

    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)
    ranked_source_ids = [item.source_item_id for item in artifacts.ranking_response.ranked_experiences]

    assert ranked_source_ids[:3] == [
        "fixture.aggregate.exp.broad",
        "fixture.aggregate.exp.recent-balanced",
        "fixture.aggregate.exp.narrow",
    ]
    broad = artifacts.selection_result.resume_selection_decision.selected_experiences[0]
    narrow = next(
        item
        for item in artifacts.selection_result.resume_selection_decision.selected_experiences
        if item.source_item_id == "fixture.aggregate.exp.narrow"
    )
    assert broad.matched_must_have_count > narrow.matched_must_have_count
    assert broad.matched_requirement_diversity > narrow.matched_requirement_diversity
    assert "strategic resume fit" in broad.ranking_explanation.summary


def test_experience_omission_reasons_are_returned_for_rejected_experiences() -> None:
    profile = _aggregate_selection_profile()
    job_analysis = _aggregate_selection_job()

    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)
    omitted = [
        item
        for item in artifacts.selection_result.resume_selection_decision.omitted_items
        if item.item_type.value == "experience"
    ]

    assert len(omitted) == 1
    assert omitted[0].source_item_id == "fixture.aggregate.exp.omitted"
    assert omitted[0].reason in {
        "low_relevance",
        "weak_evidence_quality",
        "outdated_content",
        "insufficient_page_budget_priority",
        "weak_strategic_fit",
    }


def test_projects_section_is_hidden_when_projects_are_redundant_for_backend_role() -> None:
    profile = _project_selection_profile()
    job_analysis = _backend_project_job()

    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)
    decision = artifacts.selection_result.resume_selection_decision

    assert decision.selected_projects == []
    assert decision.project_selection_reasoning.show_projects_section is False
    assert "experience_already_covers_target_fit_without_projects" in decision.project_selection_reasoning.reasons
    assert any(
        item.source_item_id == "fixture.project.selection.project.redundant"
        and item.reason == "redundant_with_stronger_selected_content"
        for item in decision.omitted_projects
    )


def test_unique_project_is_selected_when_role_is_portfolio_sensitive() -> None:
    profile = _project_selection_profile()
    job_analysis = _frontend_project_job()

    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)
    decision = artifacts.selection_result.resume_selection_decision

    assert decision.project_selection_reasoning.show_projects_section is True
    assert "target_role_is_project_portfolio_sensitive" in decision.project_selection_reasoning.reasons
    assert "fixture.project.selection.project.portfolio" in decision.project_selection_reasoning.selected_project_ids
    assert [item.source_item_id for item in decision.selected_projects] == [
        "fixture.project.selection.project.portfolio"
    ]
    assert decision.selected_projects[0].selection_audit.selection_reason
    assert decision.selected_projects[0].selection_audit.score_factors
    assert decision.selected_projects[0].selection_audit.supporting_evidence_ids
    assert any(
        item.source_item_id == "fixture.project.selection.project.redundant"
        for item in decision.omitted_projects
    )

    payload = assemble_phase3_generation_payload(
        job_analysis,
        artifacts.selection_result,
        profile,
        artifacts.ranking_response,
    )
    assert [item.id for item in payload.selected_projects] == [
        "fixture.project.selection.project.portfolio"
    ]
    assert len(payload.selected_projects[0].bullets) >= 1
    assert payload.selected_projects[0].selection_reason
    assert payload.selected_projects[0].matched_requirements
    assert payload.selected_projects[0].supporting_evidence_ids
    assert all(item.selection_audit is not None for item in decision.omitted_projects)


def test_phase3_assembly_prefers_resume_selection_decision_when_legacy_selected_lists_are_sparse() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()
    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)
    phase2_selection = artifacts.selection_result.model_copy(
        update={
            "selected_experiences": [],
            "selected_projects": [],
            "selected_skills": [],
        }
    )

    payload = assemble_phase3_generation_payload(
        job_analysis,
        phase2_selection,
        profile,
        artifacts.ranking_response,
    )

    assert [item.id for item in payload.selected_experiences] == ["fixture.backend.exp.current"]
    assert payload.matched_skills
    assert payload.selected_experiences[0].selection_reason
    assert payload.matched_skills[0].selection_reason


def test_diversity_balancing_trims_bullet_concentration_when_experiences_are_similarly_relevant() -> None:
    profile = _balanced_experience_profile()
    job_analysis = _balanced_experience_job()

    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)
    selected = artifacts.selection_result.resume_selection_decision.selected_experiences

    bullet_counts = {item.source_item_id: len(item.selected_bullet_ids) for item in selected}
    total_bullets = sum(bullet_counts.values())

    assert len(selected) == 3
    assert bullet_counts["fixture.balance.exp.primary"] == 5
    assert bullet_counts["fixture.balance.exp.support1"] == 1
    assert bullet_counts["fixture.balance.exp.support2"] == 1
    assert bullet_counts["fixture.balance.exp.primary"] / total_bullets > 0.6


def test_diversity_balancing_allows_concentration_when_one_experience_is_dominant() -> None:
    artifacts = build_phase2_ranking_artifacts(
        strong_backend_job_analysis(),
        strong_backend_engineer_profile(),
    )
    selected = artifacts.selection_result.resume_selection_decision.selected_experiences
    bullet_counts = {item.source_item_id: len(item.selected_bullet_ids) for item in selected}
    total_bullets = sum(bullet_counts.values())

    assert bullet_counts["fixture.backend.exp.current"] == 3
    assert bullet_counts["fixture.backend.exp.current"] / total_bullets > 0.6


def _aggregate_selection_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.aggregate",
        personal_profile=PersonalProfile(
            id="fixture.aggregate.person",
            full_name="Casey Aggregate",
            headline="Platform Engineer",
            summary="Engineer with platform, backend, and reliability delivery experience.",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.aggregate.exp.broad",
                organization="PlatformCo",
                title="Senior Platform Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2022-01"),
                current=True,
                tools=["Python", "AWS", "Terraform", "Kubernetes"],
                bullets=[
                    BulletEntry(
                        id="fixture.aggregate.exp.broad.b1",
                        text="Architected Python services on AWS with Terraform automation, cutting deployment time 35% for platform teams.",
                        tools=["Python", "AWS", "Terraform"],
                        metrics=[MetricEntry(id="fixture.aggregate.metric.1", label="Deployment reduction", value=35, unit="%")],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    ),
                    BulletEntry(
                        id="fixture.aggregate.exp.broad.b2",
                        text="Improved Kubernetes reliability, mentored engineers, and drove platform adoption across backend teams.",
                        tools=["Kubernetes"],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ExperienceEntry(
                id="fixture.aggregate.exp.recent-balanced",
                organization="ServiceFlow",
                title="Backend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-01"),
                current=True,
                tools=["Python", "AWS"],
                bullets=[
                    BulletEntry(
                        id="fixture.aggregate.exp.recent-balanced.b1",
                        text="Built Python and AWS backend services that improved reliability by 28% for customer APIs.",
                        tools=["Python", "AWS"],
                        metrics=[MetricEntry(id="fixture.aggregate.metric.2", label="Reliability improvement", value=28, unit="%")],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ExperienceEntry(
                id="fixture.aggregate.exp.narrow",
                organization="LatencyLab",
                title="Software Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-06"),
                current=True,
                tools=["Python"],
                bullets=[
                    BulletEntry(
                        id="fixture.aggregate.exp.narrow.b1",
                        text="Built a Python API optimization that reduced latency 60% for one backend service.",
                        tools=["Python"],
                        metrics=[MetricEntry(id="fixture.aggregate.metric.3", label="Latency reduction", value=60, unit="%")],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ExperienceEntry(
                id="fixture.aggregate.exp.omitted",
                organization="LegacyApps",
                title="Application Developer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.MID,
                start_date=PartialDate(raw_value="2018-01"),
                end_date=PartialDate(raw_value="2020-12"),
                tools=["JavaScript"],
                bullets=[
                    BulletEntry(
                        id="fixture.aggregate.exp.omitted.b1",
                        text="Maintained internal dashboards and responded to bug reports.",
                        tools=["JavaScript"],
                        verified_status=VerifiedStatus.SELF_REPORTED,
                        evidence_strength=EvidenceStrength.MODERATE,
                    )
                ],
                verified_status=VerifiedStatus.SELF_REPORTED,
                evidence_strength=EvidenceStrength.MODERATE,
            ),
        ],
    )


def _balanced_experience_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.balance",
        personal_profile=PersonalProfile(
            id="fixture.balance.person",
            full_name="Balanced Casey",
            headline="Platform Engineer",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.balance.exp.primary",
                organization="PrimaryCo",
                title="Platform Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-01"),
                current=True,
                tools=["Python", "AWS", "Terraform"],
                bullets=[
                    BulletEntry(id="fixture.balance.exp.primary.b1", text="Built Python services on AWS and improved deployment speed 20%.", tools=["Python", "AWS"], metrics=[MetricEntry(id="fixture.balance.metric.1", label="Deployment speed", value=20, unit="%")], verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                    BulletEntry(id="fixture.balance.exp.primary.b2", text="Automated infrastructure with Terraform for platform teams.", tools=["Terraform"], verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                    BulletEntry(id="fixture.balance.exp.primary.b3", text="Improved reliability for backend services running on AWS.", tools=["AWS"], verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                    BulletEntry(id="fixture.balance.exp.primary.b4", text="Mentored engineers on Python service ownership.", tools=["Python"], verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                    BulletEntry(id="fixture.balance.exp.primary.b5", text="Led platform adoption for Terraform workflows.", tools=["Terraform"], verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ExperienceEntry(
                id="fixture.balance.exp.support1",
                organization="SupportOne",
                title="Backend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2022-03"),
                end_date=PartialDate(raw_value="2022-12"),
                tools=["Python", "AWS"],
                bullets=[
                    BulletEntry(id="fixture.balance.exp.support1.b1", text="Built Python APIs on AWS and improved reliability 18%.", tools=["Python", "AWS"], metrics=[MetricEntry(id="fixture.balance.metric.2", label="Reliability", value=18, unit="%")], verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
            ExperienceEntry(
                id="fixture.balance.exp.support2",
                organization="SupportTwo",
                title="DevOps Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2021-05"),
                end_date=PartialDate(raw_value="2022-02"),
                tools=["Terraform", "AWS"],
                bullets=[
                    BulletEntry(id="fixture.balance.exp.support2.b1", text="Automated AWS infrastructure using Terraform and improved release consistency.", tools=["Terraform", "AWS"], verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            ),
        ],
    )


def _aggregate_selection_job() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="cloud",
        technical_skills=["Python", "AWS", "Terraform", "Kubernetes"],
        must_have_requirements=[
            "Build Python services on AWS",
            "Automate infrastructure with Terraform",
            "Improve Kubernetes reliability",
        ],
        nice_to_have_requirements=[
            "Mentor engineers",
            "Drive platform adoption",
        ],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Terraform", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Kubernetes", priority=SkillPriority.IMPORTANT),
        ],
    )


def _balanced_experience_job() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="cloud",
        technical_skills=["Python", "AWS", "Terraform"],
        must_have_requirements=[
            "Build Python services on AWS",
            "Automate infrastructure with Terraform",
            "Improve service reliability",
        ],
        nice_to_have_requirements=["Mentor engineers", "Drive platform adoption"],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Terraform", priority=SkillPriority.CORE),
        ],
    )


def _project_selection_profile() -> MasterProfile:
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


def _backend_project_job() -> NormalizedJobAnalysis:
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


def _frontend_project_job() -> NormalizedJobAnalysis:
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
