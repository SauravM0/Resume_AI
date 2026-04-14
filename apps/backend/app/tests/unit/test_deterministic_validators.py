from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.services.verification.deterministic_validators import (
    DeterministicValidationInput,
    DeterministicValidator,
)
from backend.app.services.verification.provenance_service import ProvenanceMatch
from backend.app.services.verification.types import (
    EvidenceStrength,
    IssueCategory,
    ProvenanceRelationType,
)
from resume_optimizer.models import (
    AwardEntry,
    BulletEntry,
    CertificationEntry,
    EducationEntry,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    PersonalProfile,
    ProjectEntry,
    SkillEntry,
)
from resume_optimizer.phase3_models import (
    Phase3GenerationPayload,
    Phase3RoleContext,
    Phase3SelectedCertificationPayload,
    Phase3SelectedProjectPayload,
    Phase3SelectedSkillPayload,
    Phase3ValidationMetadata,
    SupportLevel,
)

FIXTURE_PATH = REPO_ROOT / "backend" / "app" / "tests" / "fixtures" / "deterministic_validator_cases.json"


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile.validator",
        personal_profile=PersonalProfile(
            id="personal.validator",
            full_name="Alex Validator",
            summary="Backend engineer with platform workflow experience.",
        ),
        experience=[
            ExperienceEntry(
                id="exp.platform",
                organization="Acme",
                title="Backend Engineer",
                start_date={"raw_value": "2021-01"},
                tools=["Python", "PostgreSQL"],
                bullets=[
                    BulletEntry(
                        id="bullet.platform.1",
                        text="Implemented Python APIs that reduced latency by 25% for internal workflows.",
                        tools=["Python"],
                    ),
                    BulletEntry(
                        id="bullet.platform.2",
                        text="Contributed to PostgreSQL reliability improvements for data services.",
                        tools=["PostgreSQL"],
                    ),
                    BulletEntry(
                        id="bullet.platform.3",
                        text="Partnered with product and design stakeholders to ship internal developer tooling for platform workflows.",
                        tools=["Python"],
                    ),
                ],
            )
        ],
        projects=[
            ProjectEntry(
                id="project.design-system-rollout",
                name="Design System Rollout",
                role="FE Lead",
                start_date={"raw_value": "2023-01"},
                end_date={"raw_value": "2023-09"},
                summary="Cross-team effort to standardize shared UI components and reduce duplicated frontend patterns.",
                tools=["React", "TypeScript", "Storybook"],
                bullets=[
                    BulletEntry(
                        id="bullet.project-design-system-adoption",
                        text="Led adoption of a shared component library across three product surfaces.",
                        tools=["React", "TypeScript", "Storybook"],
                    )
                ],
            )
        ],
        education=[
            EducationEntry(
                id="edu.uw",
                institution="University of Washington",
                degree="B.S.",
                field_of_study="Informatics",
                start_date={"raw_value": "2015-09"},
                end_date={"raw_value": "2019-06"},
                honors=["Dean's List"],
            )
        ],
        certifications=[
            CertificationEntry(
                id="cert.aws",
                name="AWS Certified Solutions Architect - Associate",
                issuer="Amazon Web Services",
                issue_date={"raw_value": "2023-11"},
            )
        ],
        awards=[
            AwardEntry(
                id="award.customer-impact",
                title="Customer Impact Award",
                awarder="Acme",
                summary="Recognized for improving internal platform delivery quality.",
            )
        ],
        skills=[
            SkillEntry(
                id="skill.python",
                name="Python",
                category="language",
            ),
            SkillEntry(
                id="skill.platform",
                name="Platform Engineering",
                category="domain",
            ),
        ],
    )


def _generation_payload() -> Phase3GenerationPayload:
    return Phase3GenerationPayload(
        role_context=Phase3RoleContext(
            target_role_title="Backend Engineer",
            must_have_skills=["Python"],
        ),
        selected_projects=[
            Phase3SelectedProjectPayload(
                id="project.design-system-rollout",
                evidence_unit_ids=["evidence.project.1"],
                name="Design System Rollout",
                role="FE Lead",
                summary="Cross-team effort to standardize shared UI components.",
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
        selected_certifications=[
            Phase3SelectedCertificationPayload(
                id="cert.aws",
                evidence_unit_ids=["evidence.cert.1"],
                name="AWS Certified Solutions Architect - Associate",
                issuer="Amazon Web Services",
                relevance_score=0.7,
            )
        ],
        validation_metadata=Phase3ValidationMetadata(profile_id="profile.validator"),
    )


def _match(case: dict[str, object]) -> list[ProvenanceMatch]:
    match_kind = case.get("match_kind", "experience")
    if match_kind == "summary":
        return [
            ProvenanceMatch(
                generated_item_key="summary",
                generated_item_type="summary",
                generated_text=str(case["generated_text"]),
                source_entity_type=ItemType.EXPERIENCE,
                source_entity_id="exp.platform",
                relation_type=ProvenanceRelationType.INFERRED_FROM_MULTIPLE_SUPPORTED_SOURCES,
                evidence_strength=EvidenceStrength.MODERATE,
                support_level=SupportLevel.SYNTHESIZED,
            )
        ]

    source_item_type = ItemType.EXPERIENCE if match_kind == "experience" else ItemType.PROJECT
    return [
        ProvenanceMatch(
            generated_item_key="gen.item",
            generated_item_type=str(case["item_type"]),
            generated_text=str(case["generated_text"]),
            source_entity_type=source_item_type,
            source_entity_id=str(case["match_item_id"]),
            source_bullet_id=str(case["match_bullet_id"]),
            relation_type=ProvenanceRelationType.DIRECT_REWRITE,
            evidence_strength=EvidenceStrength.STRONG,
            support_level=SupportLevel.DIRECT,
        )
    ]


def _load_cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: str(case["id"]))
def test_deterministic_validator_fixture_cases(case: dict[str, object]) -> None:
    issues = DeterministicValidator().validate_item(
        DeterministicValidationInput(
            item_id="summary" if case["item_type"] == "summary" else "gen.item",
            item_type=str(case["item_type"]),
            generated_text=str(case["generated_text"]),
            provenance_matches=_match(case),
            source_profile=_profile(),
            job_keywords=list(case.get("job_keywords", [])),
            generation_payload=_generation_payload(),
        )
    )

    actual_validator_names = sorted({issue.validator_name for issue in issues})
    expected_validator_names = sorted(case["expected_validator_names"])
    assert actual_validator_names == expected_validator_names


def test_skill_statement_without_source_support_fails() -> None:
    issues = DeterministicValidator().validate_item(
        DeterministicValidationInput(
            item_id="skill.ml",
            item_type="skill_statement",
            generated_text="Machine Learning",
            provenance_matches=_match(
                {
                    "item_type": "skill_statement",
                    "match_kind": "summary",
                    "generated_text": "Machine Learning",
                }
            ),
            source_profile=_profile(),
            generation_payload=_generation_payload(),
        )
    )

    assert len(issues) == 1
    assert issues[0].validator_name == "skill_drift_validator"
    assert issues[0].category is IssueCategory.UNSUPPORTED_CLAIM


def test_skill_statement_with_selected_source_support_passes() -> None:
    issues = DeterministicValidator().validate_item(
        DeterministicValidationInput(
            item_id="skill.python",
            item_type="skill_statement",
            generated_text="Python",
            provenance_matches=_match(
                {
                    "item_type": "skill_statement",
                    "match_kind": "summary",
                    "generated_text": "Python",
                }
            ),
            source_profile=_profile(),
            generation_payload=_generation_payload(),
        )
    )

    assert not issues
