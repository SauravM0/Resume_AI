"""Shared serializable support types for Phase 6 orchestration contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from backend.app.orchestration.enums import (
    ArtifactKind,
    ArtifactStorageBackend,
    FallbackEligibility,
    OrchestrationFailureType,
    RetryEligibility,
    StageName,
)
from resume_optimizer.models import NonEmptyStr, StableId, StrictModel


class PipelineArtifactRef(StrictModel):
    """Reference to a persisted or inline orchestration artifact."""

    artifact_id: StableId
    kind: ArtifactKind
    stage_name: StageName
    storage_backend: ArtifactStorageBackend = ArtifactStorageBackend.INLINE
    schema_version: NonEmptyStr
    uri: NonEmptyStr | None = None
    sha256: NonEmptyStr | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    content_type: NonEmptyStr = "application/json"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_location(self) -> "PipelineArtifactRef":
        """Require a URI for non-inline artifact references."""

        if self.storage_backend != ArtifactStorageBackend.INLINE and self.uri is None:
            raise ValueError("non-inline artifacts require uri")
        return self


class StageError(StrictModel):
    """Structured, persistence-safe stage failure."""

    error_id: StableId
    stage_name: StageName
    failure_type: OrchestrationFailureType
    message: NonEmptyStr
    retryable: bool = False
    fallback_eligible: bool = False
    provider_error_code: NonEmptyStr | None = None
    exception_type: NonEmptyStr | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RetryPolicy(StrictModel):
    """Declarative retry limits for a stage contract."""

    eligibility: RetryEligibility = RetryEligibility.NOT_RETRYABLE
    max_attempts: int = Field(default=1, ge=1, le=10)
    backoff_seconds: float = Field(default=0.0, ge=0.0)
    retryable_failure_types: list[OrchestrationFailureType] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_retry_shape(self) -> "RetryPolicy":
        """Keep retry settings internally coherent."""

        if self.eligibility == RetryEligibility.NOT_RETRYABLE and self.max_attempts != 1:
            raise ValueError("not-retryable stages must use max_attempts=1")
        if self.eligibility != RetryEligibility.NOT_RETRYABLE and self.max_attempts < 2:
            raise ValueError("retryable stages require max_attempts >= 2")
        return self


class FallbackPolicy(StrictModel):
    """Declarative fallback behavior for a stage contract."""

    eligibility: FallbackEligibility = FallbackEligibility.NOT_ALLOWED
    fallback_failure_types: list[OrchestrationFailureType] = Field(default_factory=list)
    description: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_fallback_shape(self) -> "FallbackPolicy":
        """Require an explanation when fallback is available."""

        if self.eligibility != FallbackEligibility.NOT_ALLOWED and self.description is None:
            raise ValueError("fallback-enabled stages require description")
        return self


class StageTiming(StrictModel):
    """Timing metadata for one stage result."""

    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_duration(self) -> "StageTiming":
        """Prevent contradictory explicit timestamps."""

        if self.started_at is not None and self.finished_at is not None:
            if self.finished_at < self.started_at:
                raise ValueError("finished_at cannot be earlier than started_at")
        return self


class StageIORef(StrictModel):
    """Named artifact dependency or output produced by a stage contract."""

    name: NonEmptyStr
    artifact_kind: ArtifactKind
    schema_ref: NonEmptyStr
    required: bool = True


class StageEvent(StrictModel):
    """Frontend-safe event emitted from a stage result."""

    event_id: StableId
    pipeline_run_id: StableId
    stage_name: StageName
    status: NonEmptyStr
    message: NonEmptyStr
    created_at: datetime
    artifact_refs: list[PipelineArtifactRef] = Field(default_factory=list)
