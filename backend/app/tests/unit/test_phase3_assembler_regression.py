from __future__ import annotations

from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.models import (
    BulletEntry,
    EvidenceStrength,
    ExperienceEntry,
    MasterProfile,
    PartialDate,
    PersonalProfile,
    RoleType,
    SeniorityLevel,
    VerifiedStatus,
)
from resume_optimizer.phase2_models import (
    JobAnalysisInput,
    Phase2Diagnostics,
    Phase2SelectionResult,
    RankingExplanation,
    ScoredEvidenceUnit,
    SelectedExperience,
)
from resume_optimizer.phase3_assembler import assemble_phase3_generation_payload
from resume_optimizer.ranking_models import RankingResponse
from resume_optimizer.resume_selection_models import EvidenceScore, ResumeSelectionDecision, SelectionAudit


def test_phase3_assembler_backfills_bullets_when_selection_is_too_sparse() -> None:
    profile = MasterProfile(
        id="fixture.phase3.backfill",
        personal_profile=PersonalProfile(
            id="fixture.phase3.backfill.person",
            full_name="Alex Backfill",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.phase3.backfill.exp",
                organization="Backfill Co",
                title="Backend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2023-01"),
                current=True,
                bullets=[
                    BulletEntry(id="fixture.phase3.backfill.b1", text="Built backend APIs.", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                    BulletEntry(id="fixture.phase3.backfill.b2", text="Improved reliability.", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                    BulletEntry(id="fixture.phase3.backfill.b3", text="Automated deployments.", verified_status=VerifiedStatus.CORROBORATED, evidence_strength=EvidenceStrength.STRONG),
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )
    job = NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        technical_skills=["Python"],
        must_have_requirements=["Build backend APIs"],
    )
    explanation = RankingExplanation(
        summary="Selected.",
        matched_keywords=["Python"],
        matched_required_skills=["Python"],
        matched_job_requirements=["Build backend APIs"],
    )
    scored = ScoredEvidenceUnit(
        id="evidence.backfill.1",
        item_type="experience",
        title="Backend Engineer",
        source_item_id="fixture.phase3.backfill.exp",
        source_bullet_ids=[
            "fixture.phase3.backfill.b1",
            "fixture.phase3.backfill.b2",
        ],
        bullets=[
            "Built backend APIs.",
            "Improved reliability.",
        ],
        relevance_score=0.9,
        ranking_explanation=explanation,
        selected_bullet_ids=["fixture.phase3.backfill.b1"],
    )
    scored_follow_on = ScoredEvidenceUnit(
        id="evidence.backfill.2",
        item_type="experience",
        title="Backend Engineer",
        source_item_id="fixture.phase3.backfill.exp",
        source_bullet_ids=["fixture.phase3.backfill.b2"],
        bullets=["Improved reliability."],
        relevance_score=0.85,
        ranking_explanation=explanation,
        selected_bullet_ids=[],
    )
    selection = Phase2SelectionResult(
        job_analysis=JobAnalysisInput.model_validate(job.model_dump()),
        candidate_profile_id=profile.id,
        evidence_scores=[
            EvidenceScore(
                id="evidence.backfill.1",
                item_type="experience",
                source_item_id="fixture.phase3.backfill.exp",
                source_bullet_id="fixture.phase3.backfill.b1",
                title="Backend Engineer",
                evidence_text="Built backend APIs.",
                relevance_score=0.9,
                ranking_explanation=explanation,
            ),
            EvidenceScore(
                id="evidence.backfill.2",
                item_type="experience",
                source_item_id="fixture.phase3.backfill.exp",
                source_bullet_id="fixture.phase3.backfill.b2",
                title="Backend Engineer",
                evidence_text="Improved reliability.",
                relevance_score=0.85,
                ranking_explanation=explanation,
            ),
        ],
        scored_evidence=[scored, scored_follow_on],
        selected_experiences=[
            SelectedExperience(
                id="sel.fixture.phase3.backfill.exp",
                source_item_id="fixture.phase3.backfill.exp",
                relevance_score=0.92,
                evidence_unit_ids=["evidence.backfill.1", "evidence.backfill.2"],
                selected_bullet_ids=["fixture.phase3.backfill.b1"],
                ranking_explanation=explanation,
            )
        ],
        diagnostics=Phase2Diagnostics(candidate_evidence_count=2),
        resume_selection_decision=ResumeSelectionDecision(
            selected_experiences=[],
            selected_skills=[],
            selected_projects=[],
            omitted_items=[],
        ),
    )
    payload = assemble_phase3_generation_payload(
        job,
        selection,
        profile,
        RankingResponse(),
    )

    assert [bullet.id for bullet in payload.selected_experiences[0].bullets] == [
        "fixture.phase3.backfill.b1",
        "fixture.phase3.backfill.b2",
    ]
