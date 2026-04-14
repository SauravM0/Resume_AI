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

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.models import Base
from backend.app.db.repositories.verification_repository import VerificationRepository
from backend.app.tests.unit.test_verification_orchestrator import _verification_input
from backend.app.services.verification.orchestrator import VerificationOrchestrator
from backend.app.services.verification.types import FallbackAction, VerificationStatus


def test_verification_pipeline_persists_mixed_fallback_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = VerificationRepository(session)
        result = VerificationOrchestrator(repository=repository).run(
            _verification_input(
                generated_bullet_text="Implemented Python APIs that reduced latency by 40%."
            ),
            verification_run_id="verify.persisted",
            generation_id="generation.persisted",
            pipeline_run_id="pipeline.persisted",
        )
        session.commit()

        persisted_report = repository.fetch_report_by_run_id(result.verification_run_id)

    assert sqlalchemy is not None
    assert result.report.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert result.report.renderable is True
    assert persisted_report is not None
    assert persisted_report.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert persisted_report.item_results[0].fallback_action is FallbackAction.FALLBACK_TO_ORIGINAL_SOURCE_BULLET
    assert persisted_report.item_results[0].provenance[0].source_bullet_id == "bullet.platform.1"
