from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.schemas.verification import VerificationIssue, VerificationItemResult
from backend.app.services.verification.fallback_repair import FallbackRepairService
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    RepairExecutionStatus,
    VerificationDecisionOutcome,
    VerificationStatus,
)
from resume_optimizer.models import (
    BulletEntry,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    PersonalProfile,
    SkillEntry,
)
from resume_optimizer.phase3_models import (
    BulletRewriteStrategy,
    GeneratedBullet,
    GeneratedExperience,
    GeneratedSkillHighlight,
    GeneratedSummary,
    GenerationMetadata,
    Phase3GenerationPayload,
    Phase3RoleContext,
    Phase3SelectedSkillPayload,
    Phase3ValidationMetadata,
    SourceReference,
    SupportLevel,
)


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile.repair",
        personal_profile=PersonalProfile(
            id="personal.repair",
            full_name="Alex Repair",
            summary="Backend engineer with Python and AWS experience.",
        ),
        experience=[
            ExperienceEntry(
                id="exp.acme",
                organization="Acme",
                title="Backend Engineer",
                start_date={"raw_value": "2021-01"},
                tools=["Python", "AWS"],
                bullets=[
                    BulletEntry(
                        id="bullet.acme.1",
                        text="Built Python APIs for internal workflows.",
                        tools=["Python"],
                    )
                ],
            )
        ],
        skills=[
            SkillEntry(id="skill.python", name="Python", category="language"),
            SkillEntry(id="skill.aws", name="AWS", category="platform"),
        ],
    )


def _payload() -> Phase3GenerationPayload:
    return Phase3GenerationPayload(
        role_context=Phase3RoleContext(target_role_title="Backend Engineer"),
        matched_skills=[
            Phase3SelectedSkillPayload(
                id="skill.aws",
                skill_name="AWS",
                relevance_score=0.9,
                evidence_strength="strong",
                verified_status="corroborated",
            )
        ],
        validation_metadata=Phase3ValidationMetadata(profile_id="profile.repair"),
    )


def _result(*, bullet_text: str, summary_text: str = "Backend engineer with Python and AWS experience.", skill_name: str = "AWS", source_bullet_id: str = "bullet.acme.1"):
    reference = SourceReference(
        source_item_id="exp.acme",
        source_item_type=ItemType.EXPERIENCE,
        source_bullet_id=source_bullet_id,
        support_level=SupportLevel.DIRECT,
    )
    return GenerationMetadata(source_profile_id="profile.repair"), GeneratedSummary(
        text=summary_text,
        source_item_ids=["exp.acme"],
        source_bullet_ids=[source_bullet_id],
        provenance=[reference],
        support_level=SupportLevel.SYNTHESIZED,
    ), GeneratedExperience(
        source_item_id="exp.acme",
        organization="Acme",
        title="Backend Engineer",
        start_date={"raw_value": "2021-01"},
        generated_bullets=[
            GeneratedBullet(
                id="gen.bullet.1",
                source_item_id="exp.acme",
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_ids=[source_bullet_id],
                rewritten_text=bullet_text,
                rewrite_strategy=BulletRewriteStrategy.CONDENSED,
                provenance=[reference],
                support_level=SupportLevel.DIRECT,
            )
        ],
        support_level=SupportLevel.DIRECT,
    ), GeneratedSkillHighlight(
        skill_name=skill_name,
        source_item_ids=["exp.acme"],
        provenance=[reference],
        support_level=SupportLevel.SYNTHESIZED,
    )


def _phase3_result(*, bullet_text: str, summary_text: str = "Backend engineer with Python and AWS experience.", skill_name: str = "AWS", source_bullet_id: str = "bullet.acme.1"):
    metadata, summary, experience, skill = _result(
        bullet_text=bullet_text,
        summary_text=summary_text,
        skill_name=skill_name,
        source_bullet_id=source_bullet_id,
    )
    from resume_optimizer.phase3_models import Phase3GenerationResult

    return Phase3GenerationResult(
        summary=summary,
        selected_experiences=[experience],
        skills_to_highlight=[skill],
        metadata=metadata,
    )


def _issue(category: IssueCategory, severity: IssueSeverity, *, item_id: str) -> VerificationIssue:
    return VerificationIssue(
        id=f"issue.{category.value}.{item_id}",
        category=category,
        severity=severity,
        message=f"{category.value}: unsupported",
        generated_item_id=item_id,
        source_item_ids=["exp.acme"],
        source_bullet_ids=["bullet.acme.1"],
        validator_name="test_validator",
    )


def _item_result(
    *,
    item_id: str,
    item_type: str,
    fallback_action: FallbackAction,
    issues: list[VerificationIssue],
    fallback_preview: str | None = None,
) -> VerificationItemResult:
    return VerificationItemResult(
        item_id=item_id,
        item_type=item_type,
        status=VerificationStatus.FAILED if issues and any(issue.severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL} for issue in issues) else VerificationStatus.PASSED_WITH_WARNINGS,
        evidence_strength=EvidenceStrength.WEAK,
        issues=issues,
        fallback_action=fallback_action,
        fallback_preview=fallback_preview,
        decision_outcome=VerificationDecisionOutcome.REPAIR_AND_PASS,
    )


def test_bullet_repair_falls_back_to_source_bullet() -> None:
    service = FallbackRepairService()
    result = service.apply(
        phase3_result=_phase3_result(bullet_text="Built Python APIs and reduced latency by 40%."),
        source_profile=_profile(),
        generation_payload=_payload(),
        item_results=[
            _item_result(
                item_id="gen.bullet.1",
                item_type="experience_bullet",
                fallback_action=FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                issues=[_issue(IssueCategory.UNSUPPORTED_METRIC, IssueSeverity.HIGH, item_id="gen.bullet.1")],
            )
        ],
    )

    record = result.repair_audit.records[0]
    assert record.status is RepairExecutionStatus.APPLIED
    assert record.strategy == "fallback_to_source_bullet"
    assert result.repaired_result.selected_experiences[0].generated_bullets[0].rewritten_text == "Built Python APIs for internal workflows."


def test_bullet_repair_can_downgrade_risky_language() -> None:
    service = FallbackRepairService()
    result = service.apply(
        phase3_result=_phase3_result(bullet_text="Led backend migrations for internal workflows."),
        source_profile=_profile(),
        generation_payload=_payload(),
        item_results=[
            _item_result(
                item_id="gen.bullet.1",
                item_type="experience_bullet",
                fallback_action=FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                issues=[_issue(IssueCategory.UNSUPPORTED_LEADERSHIP, IssueSeverity.HIGH, item_id="gen.bullet.1")],
            )
        ],
    )

    record = result.repair_audit.records[0]
    assert record.status is RepairExecutionStatus.APPLIED
    assert record.strategy == "fallback_to_lighter_rewrite"
    assert result.repaired_result.selected_experiences[0].generated_bullets[0].rewritten_text.startswith("contributed to")


def test_summary_repair_uses_safe_fallback_preview() -> None:
    service = FallbackRepairService()
    result = service.apply(
        phase3_result=_phase3_result(
            bullet_text="Built Python APIs for internal workflows.",
            summary_text="Principal engineer with 15 years of experience and distributed systems expertise.",
        ),
        source_profile=_profile(),
        generation_payload=_payload(),
        item_results=[
            _item_result(
                item_id="summary",
                item_type="summary",
                fallback_action=FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
                issues=[_issue(IssueCategory.UNSUPPORTED_YEARS_EXPERIENCE, IssueSeverity.CRITICAL, item_id="summary")],
                fallback_preview="Backend engineer with Python/AWS.",
            )
        ],
    )

    record = result.repair_audit.records[0]
    assert record.strategy == "rebuild_summary_from_controlled_inputs"
    assert result.repaired_result.summary is not None
    assert result.repaired_result.summary.text == "Backend engineer with Python/AWS."


def test_skill_repair_replaces_supported_alias_or_drops_skill() -> None:
    service = FallbackRepairService()
    alias_result = service.apply(
        phase3_result=_phase3_result(
            bullet_text="Built Python APIs for internal workflows.",
            skill_name="Amazon Web Services",
        ),
        source_profile=_profile(),
        generation_payload=_payload(),
        item_results=[
            _item_result(
                item_id="skill.amazon.web.services",
                item_type="skill_statement",
                fallback_action=FallbackAction.REMOVE_CLAIM,
                issues=[_issue(IssueCategory.UNSUPPORTED_CLAIM, IssueSeverity.HIGH, item_id="skill.amazon.web.services")],
            )
        ],
    )
    assert alias_result.repaired_result.skills_to_highlight[0].skill_name == "AWS"
    assert alias_result.repair_audit.records[0].strategy == "replace_with_supported_skill_alias"

    drop_result = service.apply(
        phase3_result=_phase3_result(
            bullet_text="Built Python APIs for internal workflows.",
            skill_name="Snowflake",
        ),
        source_profile=_profile(),
        generation_payload=_payload(),
        item_results=[
            _item_result(
                item_id="skill.snowflake",
                item_type="skill_statement",
                fallback_action=FallbackAction.REMOVE_CLAIM,
                issues=[_issue(IssueCategory.UNSUPPORTED_CLAIM, IssueSeverity.HIGH, item_id="skill.snowflake")],
            )
        ],
    )
    assert drop_result.repaired_result.skills_to_highlight == []
    assert drop_result.repair_audit.records[0].strategy == "drop_unsupported_skill_highlight"


def test_missing_source_bullet_escalates_to_regeneration() -> None:
    service = FallbackRepairService()
    result = service.apply(
        phase3_result=_phase3_result(
            bullet_text="Built Python APIs and reduced latency by 40%.",
            source_bullet_id="bullet.missing",
        ),
        source_profile=_profile(),
        generation_payload=_payload(),
        item_results=[
            _item_result(
                item_id="gen.bullet.1",
                item_type="experience_bullet",
                fallback_action=FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET,
                issues=[_issue(IssueCategory.UNSUPPORTED_METRIC, IssueSeverity.HIGH, item_id="gen.bullet.1")],
            )
        ],
    )

    record = result.repair_audit.records[0]
    assert record.status is RepairExecutionStatus.FAILED
    assert record.requires_regeneration is True
    assert result.repair_audit.requires_regeneration_item_ids == ["gen.bullet.1"]
