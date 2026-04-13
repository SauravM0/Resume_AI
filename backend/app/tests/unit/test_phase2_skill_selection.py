from __future__ import annotations

from resume_optimizer.job_feature_adapter import adapt_job_analysis_to_ranking_features
from resume_optimizer.job_models import NormalizedJobAnalysis, NormalizedSkillRequirement, SkillPriority
from resume_optimizer.models import (
    BulletEntry,
    EvidenceStrength,
    ExperienceEntry,
    MasterProfile,
    MetricEntry,
    PartialDate,
    PersonalProfile,
    RoleType,
    SeniorityLevel,
    SkillEntry,
    VerifiedStatus,
)
from resume_optimizer.ranking_service import build_phase2_ranking_artifacts
from resume_optimizer.resume_selection_models import ExperienceAggregateScore, ProjectAggregateScore
from resume_optimizer.skill_selection import select_strategic_skills


def test_must_have_evidence_backed_skills_outrank_merely_present_skills() -> None:
    profile = _skill_profile()
    job_analysis = _skill_job()

    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)

    assert artifacts.ranking_response.skills_to_highlight[:3] == ["Python", "AWS", "Terraform"]
    assert artifacts.selection_result.selected_skills[0].ranking_explanation.summary
    assert artifacts.selection_result.resume_selection_decision.selected_skills[0].selection_audit.selection_reason
    assert artifacts.selection_result.resume_selection_decision.selected_skills[0].selection_audit.score_factors
    assert artifacts.selection_result.resume_selection_decision.selected_skills[0].selection_audit.supporting_evidence_ids
    assert "React" not in artifacts.ranking_response.skills_to_highlight
    omitted = {
        item.source_item_id: item.reason
        for item in artifacts.selection_result.resume_selection_decision.omitted_items
        if item.item_type.value == "skill"
    }
    assert omitted["fixture.skills.react"] == "low_relevance"
    omitted_audits = {
        item.source_item_id: item.selection_audit
        for item in artifacts.selection_result.resume_selection_decision.omitted_items
        if item.item_type.value == "skill"
    }
    assert omitted_audits["fixture.skills.react"] is not None
    assert omitted_audits["fixture.skills.react"].omission_reason == "low_relevance"


def test_skill_selector_enforces_limits_and_preserves_display_order() -> None:
    profile = _skill_profile()
    job_features = adapt_job_analysis_to_ranking_features(_skill_job())

    selected, omitted = select_strategic_skills(
        source_profile=profile,
        job_features=job_features,
        evidence_scores=_evidence_scores(),
        selected_experiences=[
                ExperienceAggregateScore(
                    source_item_id="fixture.skills.exp",
                    title="Platform Engineer",
                    relevance_score=0.95,
                    evidence_score_ids=["ev.python", "ev.aws", "ev.terraform", "ev.kubernetes"],
                    selected_bullet_ids=["fixture.skills.exp.b1", "fixture.skills.exp.b2"],
                    ranking_explanation=_explanation(["Python", "AWS", "Terraform", "Kubernetes"]),
                    selection_audit=_selection_audit(["Python", "AWS", "Terraform", "Kubernetes"]),
                )
            ],
        selected_projects=[],
        max_highlighted_skills=2,
        max_per_category=1,
    )

    assert [skill.skill_name for skill in selected] == ["Python", "AWS"]
    omitted_reasons = {item.source_item_id: item.reason for item in omitted}
    assert omitted_reasons["fixture.skills.terraform"] in {
        "insufficient_page_budget_priority",
        "redundant_with_stronger_selected_content",
    }
    assert omitted_reasons["fixture.skills.kubernetes"] in {
        "insufficient_page_budget_priority",
        "redundant_with_stronger_selected_content",
    }


def test_skill_selector_supports_canonical_multiword_skills_from_selected_evidence_context() -> None:
    profile = MasterProfile(
        id="fixture.skills.soft",
        personal_profile=PersonalProfile(
            id="fixture.skills.soft.person",
            full_name="Taylor Soft Skills",
            headline="Frontend Engineer",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.skills.soft.exp",
                organization="AppStudio",
                title="Senior Frontend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-01"),
                current=True,
                bullets=[
                    BulletEntry(
                        id="fixture.skills.soft.exp.b1",
                        text="Partnered with product and design stakeholders to drive onboarding experiments and UX improvements.",
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        skills=[
            SkillEntry(
                id="fixture.skills.soft.stakeholder",
                name="Stakeholder Management",
                category="leadership",
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )
    job_features = adapt_job_analysis_to_ranking_features(
        NormalizedJobAnalysis(
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            industry_domain="product",
            technical_skills=["React"],
            soft_skills=["Stakeholder Management"],
            must_have_requirements=["Partner effectively with stakeholders across product and design"],
            prioritized_skills=[
                NormalizedSkillRequirement(
                    skill_name="Stakeholder Management",
                    priority=SkillPriority.CORE,
                )
            ],
        )
    )

    selected, omitted = select_strategic_skills(
        source_profile=profile,
        job_features=job_features,
        evidence_scores=[
            _soft_skill_evidence_score(),
        ],
        selected_experiences=[
            ExperienceAggregateScore(
                source_item_id="fixture.skills.soft.exp",
                title="Senior Frontend Engineer",
                relevance_score=0.9,
                evidence_score_ids=["ev.stakeholder"],
                selected_bullet_ids=["fixture.skills.soft.exp.b1"],
                ranking_explanation=_explanation(
                    ["product stakeholders", "design stakeholders", "experimentation"]
                ),
                selection_audit=_selection_audit(
                    ["Stakeholder Management", "Product Partnership"]
                ),
            )
        ],
        selected_projects=[],
        max_highlighted_skills=3,
        max_per_category=2,
    )

    assert [skill.skill_name for skill in selected] == ["Stakeholder Management"]
    assert not omitted


def _skill_profile() -> MasterProfile:
    return MasterProfile(
        id="fixture.skills",
        personal_profile=PersonalProfile(
            id="fixture.skills.person",
            full_name="Taylor Skills",
            headline="Platform Engineer",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.skills.exp",
                organization="InfraScale",
                title="Platform Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-01"),
                current=True,
                tools=["Python", "AWS", "Terraform", "Kubernetes"],
                bullets=[
                    BulletEntry(
                        id="fixture.skills.exp.b1",
                        text="Built Python services on AWS with Terraform automation and reduced deployment time 40%.",
                        tools=["Python", "AWS", "Terraform"],
                        metrics=[MetricEntry(id="fixture.skills.metric.1", label="Deployment reduction", value=40, unit="%")],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    ),
                    BulletEntry(
                        id="fixture.skills.exp.b2",
                        text="Improved Kubernetes reliability for platform workloads.",
                        tools=["Kubernetes"],
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    ),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        skills=[
            SkillEntry(id="fixture.skills.python", name="Python", category="backend", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
            SkillEntry(id="fixture.skills.aws", name="AWS", category="cloud", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
            SkillEntry(id="fixture.skills.terraform", name="Terraform", category="cloud", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
            SkillEntry(id="fixture.skills.kubernetes", name="Kubernetes", category="cloud", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
            SkillEntry(id="fixture.skills.react", name="React", category="frontend", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
        ],
    )


def _skill_job() -> NormalizedJobAnalysis:
    return NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        industry_domain="cloud",
        technical_skills=["Python", "AWS", "Terraform", "Kubernetes", "React"],
        must_have_requirements=[
            "Build Python services on AWS",
            "Automate infrastructure with Terraform",
        ],
        nice_to_have_requirements=[
            "Improve Kubernetes reliability",
            "Use React when needed",
        ],
        prioritized_skills=[
            NormalizedSkillRequirement(skill_name="Python", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="AWS", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Terraform", priority=SkillPriority.CORE),
            NormalizedSkillRequirement(skill_name="Kubernetes", priority=SkillPriority.IMPORTANT),
            NormalizedSkillRequirement(skill_name="React", priority=SkillPriority.NICE_TO_HAVE),
        ],
    )


def _evidence_scores():
    from resume_optimizer.resume_selection_models import EvidenceScore
    from resume_optimizer.scoring_engine import ScoreComponent

    def ev(ev_id: str, bullet_id: str, keywords: list[str], score: float, recency: float = 8.0):
        return EvidenceScore(
            id=ev_id,
            item_type="experience",
            source_item_id="fixture.skills.exp",
            source_bullet_id=bullet_id,
            title="Platform Engineer",
            evidence_text="evidence",
            keywords=keywords,
            relevance_score=score,
            ranking_explanation=_explanation(keywords),
            component_scores={"recency": ScoreComponent(value=recency, weight=10.0, rationale="recent")},
        )

    return [
        ev("ev.python", "fixture.skills.exp.b1", ["Python", "AWS"], 0.95),
        ev("ev.aws", "fixture.skills.exp.b1", ["AWS", "Terraform"], 0.9),
        ev("ev.terraform", "fixture.skills.exp.b1", ["Terraform"], 0.88),
        ev("ev.kubernetes", "fixture.skills.exp.b2", ["Kubernetes"], 0.72),
    ]


def _soft_skill_evidence_score():
    from resume_optimizer.resume_selection_models import EvidenceScore
    from resume_optimizer.scoring_engine import ScoreComponent

    return EvidenceScore(
        id="ev.stakeholder",
        item_type="experience",
        source_item_id="fixture.skills.soft.exp",
        source_bullet_id="fixture.skills.soft.exp.b1",
        title="Senior Frontend Engineer",
        evidence_text="stakeholder evidence",
        keywords=["product stakeholders", "design stakeholders", "experimentation"],
        relevance_score=0.86,
        ranking_explanation=_explanation(
            ["product stakeholders", "design stakeholders", "experimentation"]
        ).model_copy(
            update={
                "matched_job_requirements": [
                    "Partner effectively with stakeholders across product and design"
                ]
            }
        ),
        component_scores={
            "recency": ScoreComponent(value=8.0, weight=10.0, rationale="recent")
        },
    )


def _explanation(keywords: list[str]):
    from resume_optimizer.ranking_explanation_models import RankingExplanation

    must_have = [keyword for keyword in keywords if keyword in {"Python", "AWS", "Terraform"}]
    preferred = [keyword for keyword in keywords if keyword == "Kubernetes"]
    return RankingExplanation(
        summary="Skill support.",
        matched_keywords=keywords,
        matched_required_skills=must_have,
        matched_preferred_skills=preferred,
        matched_job_requirements=keywords,
        matched_prioritized_skills=keywords,
    )


def _selection_audit(keywords: list[str]):
    from resume_optimizer.resume_selection_models import SelectionAudit

    return SelectionAudit(
        matched_requirements=keywords,
        score_factors={"aggregate_score": 0.95},
        evidence_signals=["test_signal"],
        selection_reason="test_selection",
        supporting_evidence_ids=["ev.python"],
        human_summary="Test selection audit.",
    )
