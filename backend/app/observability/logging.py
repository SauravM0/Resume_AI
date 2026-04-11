"""Request tracing and structured JSON logging helpers."""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
import json
import logging
from typing import Any
from uuid import uuid4

from backend.app.privacy import sanitize_value
from resume_optimizer.config import DEFAULT_SETTINGS

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_RUN_ID: ContextVar[str | None] = ContextVar("run_id", default=None)
_DEFAULT_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())
_SENSITIVE_FIELD_NAMES = {
    "candidate_data",
    "full_candidate_data",
    "generated_summary",
    "headline_suggestion",
    "job_analysis",
    "job_description",
    "job_description_text",
    "llm_enrichment_payload",
    "phase3_result",
    "raw_job_description",
    "raw_resume",
    "resume",
    "resume_text",
    "source_profile",
    "summary",
}
_SENSITIVE_SUFFIXES = ("_text", "_content", "_payload")
_CONFIGURED = False


def generate_request_id() -> str:
    """Create a stable request-scoped identifier."""

    return f"req.{uuid4().hex}"


def set_request_id(request_id: str) -> Token[str | None]:
    """Bind a request id to the current execution context."""

    return _REQUEST_ID.set(request_id)


def bind_run_id(run_id: str | None) -> Token[str | None] | None:
    """Bind a pipeline run id to the current execution context."""

    return _RUN_ID.set(run_id)


def reset_trace_context(*tokens: Token[str | None] | None) -> None:
    """Reset previously bound trace tokens in reverse order."""

    if len(tokens) >= 1 and tokens[0] is not None:
        _RUN_ID.reset(tokens[0])
    if len(tokens) >= 2 and tokens[1] is not None:
        _REQUEST_ID.reset(tokens[1])


def get_request_id() -> str | None:
    """Return the current request id when present."""

    return _REQUEST_ID.get()


def get_run_id() -> str | None:
    """Return the current run id when present."""

    return _RUN_ID.get()


class JsonLogFormatter(logging.Formatter):
    """Render log records as one-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": getattr(record, "service", None) or record.name,
            "request_id": getattr(record, "request_id", None) or get_request_id(),
            "run_id": getattr(record, "run_id", None)
            or getattr(record, "pipeline_run_id", None)
            or get_run_id(),
            "stage_name": getattr(record, "stage_name", None),
            "event_name": getattr(record, "event_name", None) or _normalize_event_name(record.getMessage()),
            "outcome": getattr(record, "outcome", None) or _default_outcome(record),
            "duration_ms": getattr(record, "duration_ms", None),
            "error_code": getattr(record, "error_code", None),
        }

        metadata = _sanitize_metadata(getattr(record, "metadata", {}) or {})
        metadata.update(_sanitize_metadata(_extra_record_fields(record)))
        if record.exc_info:
            metadata["exception_type"] = record.exc_info[0].__name__
        if metadata:
            payload["metadata"] = metadata

        return json.dumps(_drop_none(payload), default=_json_default, separators=(",", ":"))


def configure_logging() -> None:
    """Initialize root logging with the shared JSON formatter."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, DEFAULT_SETTINGS.logging.level, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)
    _CONFIGURED = True


def log_event(
    logger: logging.Logger,
    *,
    event_name: str,
    outcome: str,
    level: int = logging.INFO,
    service: str | None = None,
    request_id: str | None = None,
    run_id: str | None = None,
    stage_name: str | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit one standardized structured log event."""

    extra = {
        "service": service or logger.name,
        "request_id": request_id,
        "run_id": run_id,
        "stage_name": stage_name,
        "event_name": event_name,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "error_code": error_code,
        "metadata": _sanitize_metadata(metadata or {}),
    }
    logger.log(level, event_name, extra=extra)


def _normalize_event_name(message: str) -> str:
    value = (message or "log").strip().lower().replace(" ", "_")
    return value or "log"


def _default_outcome(record: logging.LogRecord) -> str:
    if record.levelno >= logging.ERROR:
        return "failure"
    return "success"


def _extra_record_fields(record: logging.LogRecord) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _DEFAULT_LOG_RECORD_KEYS or key in {
            "service",
            "request_id",
            "run_id",
            "pipeline_run_id",
            "stage_name",
            "event_name",
            "outcome",
            "duration_ms",
            "error_code",
            "metadata",
            "message",
            "asctime",
            "args",
            "msg",
        }:
            continue
        extra[key] = value
    return extra


def _sanitize_metadata(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return sanitize_value(value, key=key)
    return sanitize_value(value, key=key)


def _is_sensitive_key(key: str) -> bool:
    if not DEFAULT_SETTINGS.logging.redact_sensitive_fields:
        return False
    lowered = key.lower()
    configured_fields = {
        *{value.casefold() for value in _SENSITIVE_FIELD_NAMES},
        *{value.casefold() for value in DEFAULT_SETTINGS.logging.additional_redacted_fields},
    }
    if lowered in configured_fields:
        return True
    suffixes = tuple(
        value.casefold()
        for value in [
            *_SENSITIVE_SUFFIXES,
            *DEFAULT_SETTINGS.logging.additional_redacted_suffixes,
        ]
    )
    return lowered.endswith(suffixes)


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value)
    return str(value)
