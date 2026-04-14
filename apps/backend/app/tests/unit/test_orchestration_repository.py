from __future__ import annotations

from datetime import datetime, timezone
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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.models import Base
from backend.app.db.models.pipeline_artifact import PipelineArtifactModel
from backend.app.db.models.pipeline_run import PipelineRunModel
from backend.app.db.models.pipeline_stage_event import PipelineStageEventModel
from backend.app.db.models.retry_attempt import RetryAttemptModel
from backend.app.db.models.verification_issue import VerificationIssueModel
from backend.app.db.repositories.orchestration_repository import (
    OrchestrationRepository,
    PipelineArtifactCreate,
    PipelineOutputCreate,
    PipelineRunCreate,
    PipelineRunUpdate,
    PipelineVerificationIssueCreate,
    RetryAttemptCreate,
    StageEventCreate,
)
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName, StageStatus


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def test_repository_creates_run_events_artifacts_output_and_retry(session: Session) -> None:
    repository = OrchestrationRepository(session)
    started_at = datetime.now(timezone.utc)

    run = repository.create_pipeline_run(
        PipelineRunCreate(
            status=PipelineStatus.RUNNING,
            requested_template="ats_standard",
            requested_mode="resume_pdf",
            job_description_hash="sha256:job",
            source_profile_id="master.example",
            started_at=started_at,
        )
    )
    event = repository.add_stage_event(
        StageEventCreate(
            run_id=run.id,
            stage_name=StageName.PARSE_JOB_DESCRIPTION,
            status=StageStatus.SUCCEEDED,
            attempt_number=1,
            message="Phase 1 parsed job description.",
            machine_payload_json={"skills_count": 3},
        )
    )
    artifact = repository.add_artifact(
        PipelineArtifactCreate(
            run_id=run.id,
            stage_name=StageName.PARSE_JOB_DESCRIPTION,
            artifact_type=ArtifactKind.JOB_ANALYSIS,
            storage_kind="inline",
            inline_json={"role_type": "backend"},
            content_hash="sha256:artifact",
        )
    )
    output = repository.add_output(
        PipelineOutputCreate(
            run_id=run.id,
            compile_status="succeeded",
            pdf_path_or_storage_key="outputs/resume.pdf",
            latex_path_or_storage_key="outputs/resume.tex",
            page_count=1,
            output_metadata_json={"template": "ats_standard"},
        )
    )
    retry = repository.add_retry_attempt(
        RetryAttemptCreate(
            run_id=run.id,
            stage_name=StageName.COMPILE_PDF,
            attempt_number=2,
            reason="pdflatex timeout",
            retry_strategy="fixed_backoff",
            result_status=StageStatus.SUCCEEDED,
        )
    )
    finalized = repository.update_pipeline_run(
        run.id,
        PipelineRunUpdate(
            status=PipelineStatus.SUCCEEDED,
            completed_at=datetime.now(timezone.utc),
            duration_ms=1234,
        ),
    )
    session.commit()

    fetched = repository.get_pipeline_run(run.id)

    assert fetched is not None
    assert finalized.status == PipelineStatus.SUCCEEDED.value
    assert fetched.requested_template == "ats_standard"
    assert fetched.stage_events[0].id == event.id
    assert fetched.stage_events[0].machine_payload_json == {"skills_count": 3}
    assert fetched.artifacts[0].id == artifact.id
    assert fetched.artifacts[0].inline_json == {"role_type": "backend"}
    assert fetched.outputs[0].id == output.id
    assert fetched.outputs[0].pdf_path_or_storage_key == "outputs/resume.pdf"
    assert fetched.retry_attempts[0].id == retry.id
    assert fetched.retry_attempts[0].attempt_number == 2


def test_repository_adds_run_level_verification_issue(session: Session) -> None:
    repository = OrchestrationRepository(session)
    run = repository.create_pipeline_run(PipelineRunCreate(source_profile_id="master.example"))

    issue = repository.add_verification_issue(
        PipelineVerificationIssueCreate(
            run_id=run.id,
            output_item_ref="gen.bullet.1",
            issue_type="unsupported_metric",
            severity="error",
            description="Generated metric was not present in source evidence.",
            source_refs_json={"source_bullet_ids": ["bullet.1"]},
            resolution_status="blocked",
        )
    )
    session.commit()

    fetched = repository.get_pipeline_run(run.id)

    assert fetched is not None
    assert fetched.verification_issues[0].id == issue.id
    assert fetched.verification_issues[0].run_id == run.id
    assert fetched.verification_issues[0].verification_item_id is None
    assert fetched.verification_issues[0].issue_type == "unsupported_metric"
    assert fetched.verification_issues[0].category == "unsupported_metric"
    assert fetched.verification_issues[0].message == "Generated metric was not present in source evidence."


def test_repository_indexes_support_pipeline_debug_queries() -> None:
    run_indexes = {index.name for index in PipelineRunModel.__table__.indexes}
    event_indexes = {index.name for index in PipelineStageEventModel.__table__.indexes}
    artifact_indexes = {index.name for index in PipelineArtifactModel.__table__.indexes}
    retry_indexes = {index.name for index in RetryAttemptModel.__table__.indexes}
    issue_indexes = {index.name for index in VerificationIssueModel.__table__.indexes}

    assert "ix_pipeline_runs_status" in run_indexes
    assert "ix_pipeline_runs_job_description_hash" in run_indexes
    assert "ix_pipeline_stage_events_run_stage_attempt" in event_indexes
    assert "ix_pipeline_artifacts_artifact_type" in artifact_indexes
    assert "ix_retry_attempts_run_stage_attempt" in retry_indexes
    assert "ix_verification_issues_run_id" in issue_indexes


def test_repository_rejects_unknown_run_for_child_records(session: Session) -> None:
    repository = OrchestrationRepository(session)

    with pytest.raises(ValueError, match="pipeline run not found"):
        repository.add_stage_event(
            StageEventCreate(
                run_id="missing",
                stage_name=StageName.COMPILE_PDF,
                status=StageStatus.FAILED,
            )
        )
