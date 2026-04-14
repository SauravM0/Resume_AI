from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.api.idempotency import (
    ResumeGenerationIdempotencyRegistry,
    build_in_flight_duplicate_response,
)
from backend.app.cache.keys import build_cache_key, stable_model_hash
from backend.app.metrics.storage import JsonlStageMetricsStore, record_stage_metric
from backend.app.observability import bind_run_id, reset_trace_context, set_request_id
from backend.app.observability.logging import JsonLogFormatter
from backend.app.models.render_models import RenderOutputStatus
from backend.app.orchestration.confidence import InternalConfidenceLevel, assess_run_confidence
from backend.app.orchestration.enums import OrchestrationFailureType, PipelineStatus, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.result_builder import GenerateResumePipelineResponse
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.orchestration.stage_executor import StageExecutor
from backend.app.services.verification.types import SemanticVerificationStatus, VerificationDecisionOutcome
from backend.app.support.tooling import build_health_snapshot, build_run_detail
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.phase2_models import Phase2Status


pytestmark = pytest.mark.phase8


def _recorder(run_id: str = "run.phase8") -> PipelineRunRecorder:
    recorder = PipelineRunRecorder(event_emitter=None)
    recorder.create_run(
        run_id=run_id,
        requested_template="ats_standard",
        requested_mode="resume_pdf",
        job_description_hash="sha256:phase8",
        source_profile_id="profile.phase8",
    )
    return recorder


def test_phase8_success_path_emits_structured_logs_and_complete_stage_metrics(tmp_path: Path) -> None:
    formatter = JsonLogFormatter()
    logger_record = logging.getLogger("phase8.logging").makeRecord(
        "phase8.logging",
        20,
        __file__,
        1,
        "phase8_success",
        (),
        None,
        extra={
            "service": "resume_optimizer.phase8",
            "event_name": "request_received",
            "outcome": "success",
            "request_id": "req.phase8.success",
            "run_id": "run.phase8.success",
            "metadata": {
                "job_description_text": "Sensitive JD text",
                "notes": "contact alex@example.com",
            },
        },
    )
    rendered = formatter.format(logger_record)
    payload = json.loads(rendered)

    assert payload["event_name"] == "request_received"
    assert payload["request_id"] == "req.phase8.success"
    assert payload["run_id"] == "run.phase8.success"
    assert payload["metadata"]["job_description_text"]["redacted"] is True
    assert "Sensitive JD text" not in rendered
    assert "alex@example.com" not in rendered

    store = JsonlStageMetricsStore(tmp_path / "stage_metrics.jsonl")
    request_token = set_request_id("req.phase8.success")
    run_token = bind_run_id("run.phase8.success")
    try:
        started_at = datetime(2026, 4, 10, tzinfo=UTC)
        ended_at = started_at + timedelta(milliseconds=125)
        record_stage_metric(
            stage_name="request_validation",
            started_at=started_at,
            ended_at=ended_at,
            success=True,
            output_metadata={"status": "validated"},
            store=store,
        )
    finally:
        reset_trace_context(run_token, request_token)

    records = store.load()
    assert len(records) == 1
    record = records[0]
    assert record.request_id == "req.phase8.success"
    assert record.run_id == "run.phase8.success"
    assert record.duration_ms == 125
    assert record.success is True
    assert record.output_metadata["status"] == "validated"


def test_phase8_retryable_transient_failure_retries_but_configuration_failure_fails_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = JsonlStageMetricsStore(tmp_path / "stage_metrics.jsonl")
    monkeypatch.setattr("backend.app.metrics.storage.DEFAULT_STAGE_METRICS_STORE", store)
    recorder = _recorder("run.phase8.retry")
    request_token = set_request_id("req.phase8.retry")
    run_token = bind_run_id(recorder.run_id)
    try:
        calls = {"verification": 0, "config": 0}

        def transient_verifier() -> str:
            calls["verification"] += 1
            if calls["verification"] == 1:
                raise StageExecutionError(
                    "temporary verifier outage",
                    failure_type=OrchestrationFailureType.VERIFICATION_RETRYABLE,
                    stage_name=StageName.VERIFY_GENERATED_CONTENT,
                    retryable=True,
                )
            return "verified"

        result = StageExecutor(recorder).execute(StageName.VERIFY_GENERATED_CONTENT, transient_verifier)
        assert result == "verified"

        def broken_config() -> str:
            calls["config"] += 1
            raise StageExecutionError(
                "invalid profile normalization config",
                failure_type=OrchestrationFailureType.SOURCE_PROFILE_NORMALIZATION,
                stage_name=StageName.NORMALIZE_SOURCE_DATA,
            )

        with pytest.raises(StageExecutionError):
            StageExecutor(recorder).execute(StageName.NORMALIZE_SOURCE_DATA, broken_config)
    finally:
        reset_trace_context(run_token, request_token)

    assert calls["verification"] == 2
    assert calls["config"] == 1
    verification_record = next(
        record for record in store.load() if record.stage_name == StageName.VERIFY_GENERATED_CONTENT.value
    )
    config_record = next(
        record for record in store.load() if record.stage_name == StageName.NORMALIZE_SOURCE_DATA.value
    )
    assert verification_record.retry_count == 1
    assert verification_record.success is True
    assert config_record.success is False
    assert config_record.failure_type == OrchestrationFailureType.SOURCE_PROFILE_NORMALIZATION.value


def test_phase8_duplicate_request_and_cache_invalidation_after_profile_change() -> None:
    registry = ResumeGenerationIdempotencyRegistry()
    first = registry.begin(
        canonical_key="canonical:phase8",
        immutable_input_hash="immutable:a",
        requested_run_id="run.phase8.dup",
        idempotency_key="phase8-key",
    )
    duplicate = registry.begin(
        canonical_key="canonical:phase8",
        immutable_input_hash="immutable:a",
        requested_run_id=None,
        idempotency_key="phase8-key",
    )

    assert first.outcome == "new"
    assert duplicate.outcome == "in_flight_duplicate"
    response = build_in_flight_duplicate_response(run_id=first.run_id)
    registry.mark_completed(
        canonical_key="canonical:phase8",
        response=GenerateResumePipelineResponse(
            run_id=first.run_id,
            status=PipelineStatus.SUCCEEDED,
            warnings=[],
            available_outputs=[],
            final_file_reference="artifacts/resume.pdf",
            artifact_manifest=[],
            stage_events=[],
        ),
        idempotency_key="phase8-key",
    )
    completed = registry.begin(
        canonical_key="canonical:phase8",
        immutable_input_hash="immutable:a",
        requested_run_id=None,
        idempotency_key="phase8-key",
    )

    assert response.status == PipelineStatus.RUNNING
    assert completed.outcome == "completed_duplicate"

    profile_one = load_and_normalize_master_profile("data/master_profile.example.json")
    profile_two = profile_one.model_copy(update={"id": "profile.phase8.variant"})
    key_one = build_cache_key(
        "phase2_candidate_artifacts",
        {"source_profile_hash": stable_model_hash(profile_one)},
    )
    key_two = build_cache_key(
        "phase2_candidate_artifacts",
        {"source_profile_hash": stable_model_hash(profile_two)},
    )

    assert key_one != key_two


def test_phase8_render_failure_confidence_and_safe_operator_views() -> None:
    assessment = assess_run_confidence(
        parsed=SimpleNamespace(final_analysis=SimpleNamespace(parser_confidence=0.85)),
        ranked=SimpleNamespace(
            selection_result=SimpleNamespace(
                diagnostics=SimpleNamespace(
                    status=Phase2Status.SUCCESS,
                    candidate_evidence_count=6,
                    weak_coverage_areas=[],
                    selected_experience_count=2,
                    selected_project_count=1,
                    selected_skill_count=2,
                    warnings=[],
                )
            )
        ),
        generated=SimpleNamespace(
            validation_report=SimpleNamespace(severe_failure=False, issues=[], applied_fallbacks=[])
        ),
        verified=SimpleNamespace(
            verification_report=SimpleNamespace(
                decision_outcome=VerificationDecisionOutcome.PASS,
                decision_confidence=0.92,
                renderable=True,
                semantic_verification=SimpleNamespace(status=SemanticVerificationStatus.COMPLETED),
                repair_audit=SimpleNamespace(repaired_item_ids=[]),
            )
        ),
        rendered=SimpleNamespace(
            render_output=SimpleNamespace(status=RenderOutputStatus.FAILED, warnings=[], diagnostics=None)
        ),
        compiled=SimpleNamespace(
            compile_result=SimpleNamespace(
                compile_success=False,
                warnings_detected=[],
                errors_detected=["latex error"],
            )
        ),
        terminal_failure_stage=StageName.COMPILE_PDF.value,
    )

    assert assessment.final_confidence_level is InternalConfidenceLevel.UNSAFE
    assert "render_or_compile_failed" in assessment.gating_reasons

    detail = build_run_detail(
        [
            SimpleNamespace(
                request_id="req.phase8.safe",
                run_id="run.phase8.safe",
                stage_name="verification",
                started_at=datetime(2026, 4, 10, tzinfo=UTC),
                ended_at=datetime(2026, 4, 10, tzinfo=UTC) + timedelta(milliseconds=50),
                duration_ms=50,
                success=False,
                failure_type="verification_error",
                retry_count=0,
                fallback_used=False,
                output_metadata={"summary": "Sensitive generated summary", "status": "blocked"},
            )
        ],
        run_id="run.phase8.safe",
    )
    snapshot = build_health_snapshot()
    rendered_detail = json.dumps(detail)

    assert detail is not None
    assert detail["stages"][0]["output_metadata"]["summary"]["redacted"] is True
    assert "Sensitive generated summary" not in rendered_detail
    assert "sk-" not in json.dumps(snapshot)
