from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.services.verification.matchers import SourceIndex
from backend.app.services.verification.provenance_service import ProvenanceService
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    ProvenanceRelationType,
    VerificationStatus,
)
from resume_optimizer.models import (
    BulletEntry,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    PersonalProfile,
    ProjectEntry,
    SkillEntry,
)
from resume_optimizer.phase3_models import (
    BulletRewriteStrategy,
    GeneratedBullet,
    GeneratedExperience,
    GeneratedProject,
    GeneratedSkillHighlight,
    GeneratedSummary,
    GenerationMetadata,
    Phase3GenerationResult,
    SourceReference,
    SupportLevel,
)


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile.test",
        personal_profile=PersonalProfile(
            id="personal.test",
            full_name="Alex Test",
        ),
        experience=[
            ExperienceEntry(
                id="exp.acme",
                organization="Acme",
                title="Backend Engineer",
                start_date={"raw_value": "2021-01"},
                tools=["Python", "PostgreSQL"],
                bullets=[
                    BulletEntry(
                        id="bullet.exp.1",
                        text="Built Python APIs for internal backend platform.",
                        tools=["Python"],
                    ),
                    BulletEntry(
                        id="bullet.exp.2",
                        text="Improved PostgreSQL reliability for customer workflows.",
                        tools=["PostgreSQL"],
                    ),
                ],
            )
        ],
        projects=[
            ProjectEntry(
                id="project.migration",
                name="Platform Migration",
                summary="Migrated services to a reliable platform.",
                bullets=[
                    BulletEntry(
                        id="bullet.project.1",
                        text="Migrated services to Kubernetes and improved release reliability.",
                        tools=["Kubernetes"],
                    )
                ],
            )
        ],
        skills=[
            SkillEntry(
                id="skill.python",
                name="Python",
                category="language",
            )
        ],
    )


def test_exact_id_based_mapping_uses_direct_copy_relation() -> None:
    source_index = SourceIndex(_profile())
    bullet = GeneratedBullet(
        id="gen.bullet.copy",
        source_item_id="exp.acme",
        source_item_type=ItemType.EXPERIENCE,
        source_bullet_ids=["bullet.exp.1"],
        rewritten_text="Built Python APIs for internal backend platform.",
        rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
        provenance=[
            SourceReference(
                source_item_id="exp.acme",
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_id="bullet.exp.1",
                support_level=SupportLevel.DIRECT,
            )
        ],
        support_level=SupportLevel.DIRECT,
    )

    matches = ProvenanceService().map_generated_experience_bullet(
        bullet=bullet,
        source_index=source_index,
    )

    assert len(matches) == 1
    assert matches[0].source_bullet_id == "bullet.exp.1"
    assert matches[0].relation_type is ProvenanceRelationType.DIRECT_COPY
    assert matches[0].evidence_strength is EvidenceStrength.EXACT
    assert "python" in matches[0].matched_tokens


def test_merged_bullet_mapping_preserves_multiple_source_bullets() -> None:
    source_index = SourceIndex(_profile())
    bullet = GeneratedBullet(
        id="gen.bullet.merged",
        source_item_id="exp.acme",
        source_item_type=ItemType.EXPERIENCE,
        source_bullet_ids=["bullet.exp.1", "bullet.exp.2"],
        rewritten_text="Built Python APIs and improved PostgreSQL reliability.",
        rewrite_strategy=BulletRewriteStrategy.MERGED,
        provenance=[
            SourceReference(
                source_item_id="exp.acme",
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_id="bullet.exp.1",
                support_level=SupportLevel.SYNTHESIZED,
            ),
            SourceReference(
                source_item_id="exp.acme",
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_id="bullet.exp.2",
                support_level=SupportLevel.SYNTHESIZED,
            ),
        ],
        support_level=SupportLevel.SYNTHESIZED,
    )

    matches = ProvenanceService().map_generated_experience_bullet(
        bullet=bullet,
        source_index=source_index,
    )

    assert {match.source_bullet_id for match in matches} == {"bullet.exp.1", "bullet.exp.2"}
    assert {match.relation_type for match in matches} == {
        ProvenanceRelationType.MERGED_FROM_MULTIPLE
    }


def test_summary_mapping_from_multiple_entities_is_inferred() -> None:
    source_index = SourceIndex(_profile())
    summary = GeneratedSummary(
        text="Backend engineer with Python API and platform migration experience.",
        source_item_ids=["exp.acme", "project.migration"],
        source_bullet_ids=["bullet.exp.1", "bullet.project.1"],
        provenance=[
            SourceReference(
                source_item_id="exp.acme",
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_id="bullet.exp.1",
                support_level=SupportLevel.SYNTHESIZED,
            ),
            SourceReference(
                source_item_id="project.migration",
                source_item_type=ItemType.PROJECT,
                source_bullet_id="bullet.project.1",
                support_level=SupportLevel.SYNTHESIZED,
            ),
        ],
        support_level=SupportLevel.SYNTHESIZED,
    )

    matches = ProvenanceService().map_generated_summary(
        summary=summary,
        source_index=source_index,
    )

    assert {match.source_entity_id for match in matches} == {"exp.acme", "project.migration"}
    assert {match.relation_type for match in matches} == {
        ProvenanceRelationType.INFERRED_FROM_MULTIPLE_SUPPORTED_SOURCES
    }


def test_skill_highlight_maps_to_explicit_skill_record() -> None:
    source_index = SourceIndex(_profile())
    skill = GeneratedSkillHighlight(
        skill_name="Python",
        source_item_ids=["skill.python"],
        provenance=[
            SourceReference(
                source_item_id="skill.python",
                source_item_type=ItemType.SKILL,
                support_level=SupportLevel.DIRECT,
            )
        ],
        support_level=SupportLevel.DIRECT,
    )

    matches = ProvenanceService().map_generated_skill_highlight(
        skill=skill,
        source_index=source_index,
    )

    assert len(matches) == 1
    assert matches[0].source_entity_type is ItemType.SKILL
    assert matches[0].source_entity_id == "skill.python"


def test_weak_mapping_fallback_uses_similarity_when_ids_are_missing() -> None:
    source_index = SourceIndex(_profile())
    bullet = GeneratedBullet(
        id="gen.bullet.fallback",
        source_item_id="exp.missing",
        source_item_type=ItemType.EXPERIENCE,
        source_bullet_ids=["bullet.missing"],
        rewritten_text="backend chocolate espresso nebula",
        rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
        provenance=[
            SourceReference(
                source_item_id="exp.missing",
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_id="bullet.missing",
                support_level=SupportLevel.INFERRED,
            )
        ],
        support_level=SupportLevel.INFERRED,
    )

    matches = ProvenanceService().map_generated_experience_bullet(
        bullet=bullet,
        source_index=source_index,
    )

    assert len(matches) == 1
    assert matches[0].source_bullet_id == "bullet.exp.1"
    assert matches[0].relation_type is ProvenanceRelationType.DIRECT_REWRITE
    assert matches[0].evidence_strength is EvidenceStrength.WEAK
    assert matches[0].matched_tokens == ["backend"]


def test_no_source_found_behavior_records_unmatched_item() -> None:
    phase3_result = Phase3GenerationResult(
        selected_experiences=[
            GeneratedExperience(
                source_item_id="exp.missing",
                organization="Acme",
                title="Backend Engineer",
                start_date={"raw_value": "2021-01"},
                generated_bullets=[
                    GeneratedBullet(
                        id="gen.bullet.unmatched",
                        source_item_id="exp.missing",
                        source_item_type=ItemType.EXPERIENCE,
                        source_bullet_ids=["bullet.missing"],
                        rewritten_text="zephyr quartz obsidian xylophone",
                        rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
                        provenance=[
                            SourceReference(
                                source_item_id="exp.missing",
                                source_item_type=ItemType.EXPERIENCE,
                                source_bullet_id="bullet.missing",
                                support_level=SupportLevel.INFERRED,
                            )
                        ],
                        support_level=SupportLevel.INFERRED,
                    )
                ],
                support_level=SupportLevel.DIRECT,
            )
        ],
        metadata=GenerationMetadata(source_profile_id="profile.test"),
    )

    provenance_map = ProvenanceService().build_for_phase3_result(
        source_profile=_profile(),
        phase3_result=phase3_result,
    )

    assert provenance_map.matches == []
    assert provenance_map.unmatched_item_keys == ["gen.bullet.unmatched"]


def test_provenance_matches_persist_through_repository() -> None:
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.app.db.models import Base
    from backend.app.db.repositories.verification_repository import VerificationRepository

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = ProvenanceService()
    source_index = SourceIndex(_profile())
    bullet = GeneratedBullet(
        id="gen.bullet.persist",
        source_item_id="exp.acme",
        source_item_type=ItemType.EXPERIENCE,
        source_bullet_ids=["bullet.exp.1"],
        rewritten_text="Built Python APIs for internal backend platform.",
        rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
        provenance=[
            SourceReference(
                source_item_id="exp.acme",
                source_item_type=ItemType.EXPERIENCE,
                source_bullet_id="bullet.exp.1",
                support_level=SupportLevel.DIRECT,
            )
        ],
        support_level=SupportLevel.DIRECT,
    )
    matches = service.map_generated_experience_bullet(
        bullet=bullet,
        source_index=source_index,
    )

    with Session(engine) as session:
        repository = VerificationRepository(session)
        run = repository.create_verification_run(
            candidate_id="profile.test",
            status=VerificationStatus.PENDING,
        )
        item = repository.add_verification_item(
            verification_run_id=run.id,
            item_type="experience_bullet",
            item_key="gen.bullet.persist",
            generated_text="Built Python APIs for internal backend platform.",
            status=VerificationStatus.PASSED,
            fallback_action=FallbackAction.ACCEPT,
            evidence_strength=EvidenceStrength.EXACT,
        )
        service.persist_matches(
            repository=repository,
            verification_item_id=item.id,
            matches=matches,
        )

        report = repository.fetch_report_by_run_id(run.id)

    assert sqlalchemy is not None
    assert report is not None
    assert report.item_results[0].provenance[0].relation_type is ProvenanceRelationType.DIRECT_COPY
