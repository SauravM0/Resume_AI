from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.models import Base
from backend.app.db.models.provenance_link import ProvenanceLinkModel
from backend.app.db.models.verification_issue import VerificationIssueModel
from backend.app.db.models.verification_item import VerificationItemModel
from backend.app.db.repositories.verification_repository import (
    ProvenanceLinkCreate,
    VerificationIssueCreate,
    VerificationRepository,
)
from backend.app.schemas.verification import SemanticVerificationAudit
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    ProvenanceRelationType,
    VerificationDecisionOutcome,
    SemanticVerificationStatus,
    VerificationStatus,
)
from resume_optimizer.models import ItemType


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def test_repository_inserts_and_fetches_verification_report(session: Session) -> None:
    repository = VerificationRepository(session)
    run = repository.create_verification_run(
        generation_id="generation.1",
        pipeline_run_id="pipeline.1",
        candidate_id="candidate.1",
        job_id="job.1",
        jd_hash="jdhash.1",
        raw_artifact_refs={"phase3_result_id": "phase3.result.1"},
    )
    item = repository.add_verification_item(
        verification_run_id=run.id,
        item_type="experience_bullet",
        item_key="gen.bullet.1",
        generated_text="Built Python APIs backed by PostgreSQL.",
        status=VerificationStatus.PASSED,
        confidence=0.91,
        evidence_strength=EvidenceStrength.STRONG,
    )
    repository.add_provenance_links(
        verification_item_id=item.id,
        links=[
            ProvenanceLinkCreate(
                source_entity_type=ItemType.EXPERIENCE,
                source_entity_id="exp.acme",
                source_bullet_id="bullet.acme.1",
                relation_type=ProvenanceRelationType.DIRECT_REWRITE,
                evidence_strength=EvidenceStrength.STRONG,
                matched_tokens_json=["Python", "PostgreSQL"],
            )
        ],
    )
    repository.finalize_run(
        verification_run_id=run.id,
        status=VerificationStatus.PASSED,
        overall_score=0.94,
        summary_status=VerificationStatus.PASSED,
        raw_artifact_refs_update={
            "semantic_verification": SemanticVerificationAudit(
                enabled=True,
                strict_mode=True,
                fallback_behavior="block",
                status=SemanticVerificationStatus.COMPLETED,
                required_item_ids=["gen.bullet.1"],
                attempted_item_ids=["gen.bullet.1"],
                completed_item_ids=["gen.bullet.1"],
            ).model_dump(mode="json"),
            "decision_audit": {
                "outcome": "pass",
                "confidence": 0.94,
                "semantic_coverage": 1.0,
                "degraded_semantic": False,
                "issue_counts_by_severity": {},
                "issue_counts_by_scope": {},
                "reasons": [],
            },
        },
    )
    session.commit()

    report = repository.fetch_report_by_run_id(run.id)

    assert report is not None
    assert report.verification_run_id == run.id
    assert report.source_profile_id == "candidate.1"
    assert report.status is VerificationStatus.PASSED
    assert report.renderable is True
    assert report.item_results[0].item_id == "gen.bullet.1"
    assert report.item_results[0].provenance[0].source_item_id == "exp.acme"
    assert report.decision_outcome is VerificationDecisionOutcome.PASS
    assert report.semantic_verification.status is SemanticVerificationStatus.COMPLETED


def test_repository_persists_issues_and_failed_finalize_state(session: Session) -> None:
    repository = VerificationRepository(session)
    run = repository.create_verification_run(candidate_id="candidate.1")
    item = repository.add_verification_item(
        verification_run_id=run.id,
        item_type="experience_bullet",
        item_key="gen.bullet.metric",
        generated_text="Reduced latency by 90%.",
        status=VerificationStatus.FAILED,
        fallback_action=FallbackAction.REQUIRE_HUMAN_REVIEW,
        evidence_strength=EvidenceStrength.NONE,
    )
    repository.add_issues(
        verification_item_id=item.id,
        issues=[
            VerificationIssueCreate(
                category=IssueCategory.UNSUPPORTED_METRIC,
                severity=IssueSeverity.HIGH,
                message="The generated 90% latency metric is not present in the source bullets.",
                source_span_json={
                    "source_item_ids": ["exp.acme"],
                    "source_bullet_ids": ["bullet.acme.1"],
                },
                generated_span_json={"text": "90%"},
                details_json={
                    "generated_item_id": "gen.bullet.metric",
                    "source_item_ids": ["exp.acme"],
                    "source_bullet_ids": ["bullet.acme.1"],
                    "evidence_strength": EvidenceStrength.NONE.value,
                    "suggested_fallback": FallbackAction.REQUIRE_HUMAN_REVIEW.value,
                    "validator_name": "metric_support",
                },
            )
        ],
    )
    repository.finalize_run(
        verification_run_id=run.id,
        status=VerificationStatus.FAILED,
        overall_score=0.2,
        fallback_applied=True,
    )

    report = repository.fetch_report_by_run_id(run.id)

    assert report is not None
    assert report.status is VerificationStatus.FAILED
    assert report.renderable is False
    assert report.item_results[0].issues[0].category is IssueCategory.UNSUPPORTED_METRIC
    assert report.item_results[0].issues[0].validator_name == "metric_support"
    assert report.item_results[0].issues[0].source_bullet_ids == ["bullet.acme.1"]


def test_repository_indexes_support_required_query_dimensions(session: Session) -> None:
    item_indexes = {index.name for index in VerificationItemModel.__table__.indexes}
    issue_indexes = {index.name for index in VerificationIssueModel.__table__.indexes}
    link_indexes = {index.name for index in ProvenanceLinkModel.__table__.indexes}

    assert "ix_verification_items_run_id" in item_indexes
    assert "ix_verification_items_status" in item_indexes
    assert "ix_verification_items_item_type" in item_indexes
    assert "ix_verification_issues_category" in issue_indexes
    assert "ix_provenance_links_item_id" in link_indexes


def test_finalize_run_updates_aggregate_fields(session: Session) -> None:
    repository = VerificationRepository(session)
    run = repository.create_verification_run(candidate_id="candidate.1")

    finalized = repository.finalize_run(
        verification_run_id=run.id,
        status=VerificationStatus.PASSED,
        overall_score=0.88,
        fallback_applied=False,
        summary_status=VerificationStatus.PASSED,
    )

    assert finalized.finished_at is not None
    assert finalized.status == VerificationStatus.PASSED.value
    assert float(finalized.overall_score or Decimal("0")) == 0.88
    assert finalized.summary_status == VerificationStatus.PASSED.value


def test_fetch_report_returns_none_for_unknown_run(session: Session) -> None:
    repository = VerificationRepository(session)

    assert repository.fetch_report_by_run_id("missing.run") is None


def test_finalize_run_rejects_unknown_run(session: Session) -> None:
    repository = VerificationRepository(session)

    with pytest.raises(ValueError, match="verification run not found"):
        repository.finalize_run(
            verification_run_id="missing.run",
            status=VerificationStatus.FAILED,
        )
