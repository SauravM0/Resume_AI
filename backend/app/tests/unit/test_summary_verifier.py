from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.services.verification.deterministic_validators import (
    DeterministicValidationInput,
    SelectedContentContext,
    SourceContext,
)
from backend.app.services.verification.provenance_service import ProvenanceMatch
from backend.app.services.verification.summary_verifier import (
    SummaryClaimType,
    SummaryVerifier,
    extract_summary_claims,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    ProvenanceRelationType,
)
from resume_optimizer.models import (
    BulletEntry,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    PersonalProfile,
    ProjectEntry,
    SeniorityLevel,
    SkillEntry,
)
from resume_optimizer.phase3_models import (
    Phase3GenerationPayload,
    Phase3RoleContext,
    Phase3SelectedProjectPayload,
    Phase3SelectedSkillPayload,
    Phase3ValidationMetadata,
    SupportLevel,
)


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile.summary",
        personal_profile=PersonalProfile(
            id="personal.summary",
            full_name="Alex Summary",
            summary="Backend engineer focused on Python APIs and delivery execution.",
            seniority_level=SeniorityLevel.SENIOR,
        ),
        experience=[
            ExperienceEntry(
                id="exp.backend",
                organization="Acme",
                title="Senior Backend Engineer",
                seniority_level=SeniorityLevel.SENIOR,
                start_date={"raw_value": "2019-01"},
                tools=["Python", "PostgreSQL"],
                bullets=[
                    BulletEntry(
                        id="bullet.backend.1",
                        text="Built Python APIs and improved reliability for internal delivery workflows.",
                        tools=["Python"],
                    )
                ],
                canonical_tags=["backend"],
                domain_tags=["platform"],
            )
        ],
        projects=[
            ProjectEntry(
                id="project.portal",
                name="Developer Portal",
                role="Backend Engineer",
                start_date={"raw_value": "2023-01"},
                summary="Internal developer tooling for service onboarding.",
                bullets=[
                    BulletEntry(
                        id="bullet.portal.1",
                        text="Built internal developer tooling that simplified service onboarding.",
                        tools=["Python"],
                    )
                ],
                canonical_tags=["platform"],
                domain_tags=["developer tooling"],
            )
        ],
        skills=[
            SkillEntry(id="skill.python", name="Python", category="language"),
            SkillEntry(id="skill.platform", name="Platform", category="domain"),
        ],
    )


def _payload() -> Phase3GenerationPayload:
    return Phase3GenerationPayload(
        role_context=Phase3RoleContext(target_role_title="Backend Engineer", must_have_skills=["Python"]),
        selected_projects=[
            Phase3SelectedProjectPayload(
                id="project.portal",
                evidence_unit_ids=["evidence.project.portal"],
                name="Developer Portal",
                role="Backend Engineer",
                summary="Internal developer tooling for service onboarding.",
                relevance_score=0.8,
            )
        ],
        matched_skills=[
            Phase3SelectedSkillPayload(
                id="skill.python",
                skill_name="Python",
                relevance_score=0.9,
                evidence_strength="strong",
                verified_status="corroborated",
            )
        ],
        validation_metadata=Phase3ValidationMetadata(profile_id="profile.summary"),
    )


def _matches(summary_text: str) -> list[ProvenanceMatch]:
    return [
        ProvenanceMatch(
            generated_item_key="summary",
            generated_item_type="summary",
            generated_text=summary_text,
            source_entity_type=ItemType.EXPERIENCE,
            source_entity_id="exp.backend",
            source_bullet_id="bullet.backend.1",
            relation_type=ProvenanceRelationType.INFERRED_FROM_MULTIPLE_SUPPORTED_SOURCES,
            evidence_strength=EvidenceStrength.MODERATE,
            support_level=SupportLevel.SYNTHESIZED,
        )
    ]


def _validation_input(summary_text: str) -> DeterministicValidationInput:
    return DeterministicValidationInput(
        item_id="summary",
        item_type="summary",
        generated_text=summary_text,
        provenance_matches=_matches(summary_text),
        source_profile=_profile(),
        generation_payload=_payload(),
    )


def test_extract_summary_claims_captures_claim_categories() -> None:
    claims = extract_summary_claims(
        "Senior backend engineer with 9 years of experience, distributed systems expertise, and cross-functional leadership."
    )

    claim_types = {claim.claim_type for claim in claims}
    assert SummaryClaimType.YEARS_EXPERIENCE in claim_types
    assert SummaryClaimType.SENIORITY in claim_types
    assert SummaryClaimType.ROLE_FAMILY in claim_types
    assert SummaryClaimType.DOMAIN_EXPERTISE in claim_types
    assert SummaryClaimType.LEADERSHIP_LEVEL in claim_types


def test_summary_verifier_passes_supported_summary() -> None:
    verifier = SummaryVerifier()
    source_context = SourceContext.from_entire_profile(_profile())
    selected_context = SelectedContentContext.from_generation_payload(_payload())

    result = verifier.verify(
        validation_input=_validation_input("Senior backend engineer with Python API experience."),
        source_context=source_context,
        selected_context=selected_context,
    )

    assert result.issues == []
    assert result.fallback_plan.safe_summary_text


def test_summary_verifier_flags_years_seniority_and_role_family_mismatch() -> None:
    verifier = SummaryVerifier()
    source_context = SourceContext.from_entire_profile(_profile())
    selected_context = SelectedContentContext.from_generation_payload(_payload())

    result = verifier.verify(
        validation_input=_validation_input(
            "Principal full-stack engineer with 15 years of experience."
        ),
        source_context=source_context,
        selected_context=selected_context,
    )

    categories = {issue.category for issue in result.issues}
    assert IssueCategory.UNSUPPORTED_YEARS_EXPERIENCE in categories
    assert IssueCategory.SENIORITY_MISMATCH in categories
    assert IssueCategory.ROLE_FAMILY_MISMATCH in categories
    assert result.fallback_plan.strategy == "rebuild_from_controlled_summary_inputs"


def test_summary_verifier_flags_breadth_and_ownership_inflation() -> None:
    verifier = SummaryVerifier()
    source_context = SourceContext.from_entire_profile(_profile())
    selected_context = SelectedContentContext.from_generation_payload(_payload())

    result = verifier.verify(
        validation_input=_validation_input(
            "Backend engineer with expertise in Python, Kubernetes, Snowflake, and machine learning plus end-to-end ownership."
        ),
        source_context=source_context,
        selected_context=selected_context,
    )

    categories = {issue.category for issue in result.issues}
    assert IssueCategory.BREADTH_INFLATION in categories
    assert IssueCategory.UNSUPPORTED_SCOPE in categories
    assert all(issue.suggested_fallback is FallbackAction.USE_SAFE_SUMMARY_FALLBACK for issue in result.issues)
