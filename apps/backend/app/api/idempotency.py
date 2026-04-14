"""Local idempotency registry for duplicate resume-generation requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from backend.app.cache.keys import build_cache_key, stable_file_hash, stable_json_hash, stable_model_hash, stable_text_hash
from backend.app.orchestration.enums import PipelineStatus
from backend.app.orchestration.result_builder import GenerateResumePipelineResponse
from backend.app.services.template_registry import load_template
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.models import MasterProfile

COMPLETED_REUSE_TTL_SECONDS = DEFAULT_SETTINGS.cache.idempotency_completed_ttl_seconds
IN_FLIGHT_STALE_TTL_SECONDS = DEFAULT_SETTINGS.cache.idempotency_in_flight_ttl_seconds


@dataclass(slots=True)
class InFlightRequest:
    canonical_key: str
    run_id: str
    immutable_input_hash: str
    started_at: datetime
    idempotency_key: str | None = None


@dataclass(slots=True)
class CompletedRequest:
    canonical_key: str
    run_id: str
    immutable_input_hash: str
    response: GenerateResumePipelineResponse
    completed_at: datetime
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    outcome: Literal["new", "in_flight_duplicate", "completed_duplicate"]
    run_id: str
    canonical_key: str
    immutable_input_hash: str
    response: GenerateResumePipelineResponse | None = None


class ResumeGenerationIdempotencyRegistry:
    """Process-local duplicate request registry with conservative replay rules."""

    def __init__(
        self,
        *,
        completed_ttl_seconds: int = COMPLETED_REUSE_TTL_SECONDS,
        in_flight_ttl_seconds: int = IN_FLIGHT_STALE_TTL_SECONDS,
    ) -> None:
        self.completed_ttl_seconds = completed_ttl_seconds
        self.in_flight_ttl_seconds = in_flight_ttl_seconds
        self._lock = Lock()
        self._in_flight: dict[str, InFlightRequest] = {}
        self._completed: dict[str, CompletedRequest] = {}

    def begin(
        self,
        *,
        canonical_key: str,
        immutable_input_hash: str,
        requested_run_id: str | None,
        idempotency_key: str | None,
    ) -> IdempotencyDecision:
        """Reserve execution for a request or return duplicate handling guidance."""

        now = datetime.now(timezone.utc)
        with self._lock:
            self._prune(now)
            completed = self._completed.get(canonical_key)
            if completed is not None:
                return IdempotencyDecision(
                    outcome="completed_duplicate",
                    run_id=completed.run_id,
                    canonical_key=canonical_key,
                    immutable_input_hash=immutable_input_hash,
                    response=completed.response,
                )
            in_flight = self._in_flight.get(canonical_key)
            if in_flight is not None:
                return IdempotencyDecision(
                    outcome="in_flight_duplicate",
                    run_id=in_flight.run_id,
                    canonical_key=canonical_key,
                    immutable_input_hash=immutable_input_hash,
                )
            run_id = requested_run_id or f"run.{uuid4().hex}"
            self._in_flight[canonical_key] = InFlightRequest(
                canonical_key=canonical_key,
                run_id=run_id,
                immutable_input_hash=immutable_input_hash,
                started_at=now,
                idempotency_key=idempotency_key,
            )
            return IdempotencyDecision(
                outcome="new",
                run_id=run_id,
                canonical_key=canonical_key,
                immutable_input_hash=immutable_input_hash,
            )

    def mark_completed(
        self,
        *,
        canonical_key: str,
        response: GenerateResumePipelineResponse,
        idempotency_key: str | None,
    ) -> None:
        """Promote an in-flight request to a recent completed replay candidate."""

        with self._lock:
            inflight = self._in_flight.pop(canonical_key, None)
            if inflight is None:
                return
            if response.status not in {
                PipelineStatus.SUCCEEDED,
                PipelineStatus.SUCCEEDED_WITH_WARNINGS,
            }:
                return
            self._completed[canonical_key] = CompletedRequest(
                canonical_key=canonical_key,
                run_id=response.run_id,
                immutable_input_hash=inflight.immutable_input_hash,
                response=response,
                completed_at=datetime.now(timezone.utc),
                idempotency_key=idempotency_key,
            )

    def release(
        self,
        *,
        canonical_key: str,
    ) -> None:
        """Release a failed or abandoned in-flight request."""

        with self._lock:
            self._in_flight.pop(canonical_key, None)

    def reset(self) -> None:
        """Clear all state for tests or local resets."""

        with self._lock:
            self._in_flight.clear()
            self._completed.clear()

    def _prune(self, now: datetime) -> None:
        completed_cutoff = now - timedelta(seconds=self.completed_ttl_seconds)
        inflight_cutoff = now - timedelta(seconds=self.in_flight_ttl_seconds)
        self._completed = {
            key: value
            for key, value in self._completed.items()
            if value.completed_at >= completed_cutoff
        }
        self._in_flight = {
            key: value
            for key, value in self._in_flight.items()
            if value.started_at >= inflight_cutoff
        }


def build_generation_request_fingerprint(
    request,
    *,
    idempotency_key: str | None,
) -> tuple[str, str]:
    """Return canonical idempotency and immutable input hashes for generation requests."""

    template = load_template(request.template_id)
    immutable_input_hash = stable_json_hash(
        {
            "job_description_hash": stable_text_hash(request.job_description_text),
            "job_posting_url": request.job_posting_url,
            "source_profile_hash": _source_profile_hash(request),
            "source_profile_id": request.source_profile_id
            or (request.source_profile.id if request.source_profile is not None else None),
            "template_id": request.template_id,
            "template_version": template.metadata.version,
            "template_checksum": template.checksum_sha256,
            "generation_preferences": (
                request.generation_preferences.model_dump(mode="json", exclude_none=True)
                if request.generation_preferences is not None
                else None
            ),
            "persist_intermediate_artifacts": request.persist_intermediate_artifacts,
            "config_hash": stable_json_hash(
                {
                    "default_profile_path": str(DEFAULT_SETTINGS.default_profile_path),
                    "phase1_job_analysis_model": DEFAULT_SETTINGS.phase1_job_analysis_model,
                    "phase3_generation_model": DEFAULT_SETTINGS.phase3_generation_model,
                    "phase6_semantic_model": DEFAULT_SETTINGS.phase6_semantic_model,
                    "phase6_semantic_verification_enabled": DEFAULT_SETTINGS.phase6_semantic_verification_enabled,
                    "phase6_semantic_verification_strict_mode": DEFAULT_SETTINGS.phase6_semantic_verification_strict_mode,
                    "phase6_semantic_verifier_unavailable_behavior": DEFAULT_SETTINGS.phase6_semantic_verifier_unavailable_behavior,
                }
            ),
        }
    )
    canonical_key = build_cache_key(
        "resume_generation_idempotency",
        {
            "idempotency_key": idempotency_key,
            "immutable_input_hash": immutable_input_hash,
        },
    )
    return canonical_key, immutable_input_hash


def build_in_flight_duplicate_response(*, run_id: str) -> GenerateResumePipelineResponse:
    """Build a safe response for an already running duplicate request."""

    return GenerateResumePipelineResponse(
        run_id=run_id,
        status=PipelineStatus.RUNNING,
        warnings=["An equivalent resume generation request is already in progress."],
        available_outputs=[],
        final_file_reference=None,
        artifact_manifest=[],
        stage_events=[],
    )


def _source_profile_hash(request) -> str:
    if request.source_profile is not None:
        return stable_model_hash(request.source_profile)
    if request.source_profile_path is not None:
        return stable_file_hash(Path(request.source_profile_path).resolve())
    default_path = Path(DEFAULT_SETTINGS.default_profile_path).resolve()
    if default_path.exists():
        return stable_file_hash(default_path)
    return stable_text_hash(request.source_profile_id or "default-profile")
