"""Central privacy helpers for logs, metrics, diagnostics, and exceptions."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Any

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]*)?(?:\(?\d{3}\)?[-.\s]+){2}\d{4}\b")
URL_PATTERN = re.compile(r"\bhttps?://[^\s]+", re.IGNORECASE)
OPENAI_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
DEFAULT_EXCEPTION_MESSAGE = "Sensitive error details were redacted."


class SensitiveDataClass(StrEnum):
    """Operationally sensitive data classes that must not leak."""

    RAW_JOB_DESCRIPTION = "raw_job_description"
    RAW_CANDIDATE_PROFILE = "raw_candidate_profile"
    CONTACT_INFO = "contact_info"
    GENERATED_SUMMARY = "generated_summary"
    FINAL_LATEX_BODY = "final_latex_body"
    RESUME_PDF_CONTENT = "resume_pdf_content"
    INTERNAL_RAW_MODEL_RESPONSE = "internal_raw_model_response"


SENSITIVE_KEY_MAP: dict[str, SensitiveDataClass] = {
    "candidate_data": SensitiveDataClass.RAW_CANDIDATE_PROFILE,
    "email": SensitiveDataClass.CONTACT_INFO,
    "full_candidate_data": SensitiveDataClass.RAW_CANDIDATE_PROFILE,
    "generated_bullets": SensitiveDataClass.GENERATED_SUMMARY,
    "generated_summary": SensitiveDataClass.GENERATED_SUMMARY,
    "headline_suggestion": SensitiveDataClass.GENERATED_SUMMARY,
    "job_analysis": SensitiveDataClass.RAW_JOB_DESCRIPTION,
    "job_description": SensitiveDataClass.RAW_JOB_DESCRIPTION,
    "job_description_text": SensitiveDataClass.RAW_JOB_DESCRIPTION,
    "latex_body": SensitiveDataClass.FINAL_LATEX_BODY,
    "llm_enrichment_payload": SensitiveDataClass.INTERNAL_RAW_MODEL_RESPONSE,
    "openai_response": SensitiveDataClass.INTERNAL_RAW_MODEL_RESPONSE,
    "pdf_content": SensitiveDataClass.RESUME_PDF_CONTENT,
    "phase3_result": SensitiveDataClass.GENERATED_SUMMARY,
    "phone": SensitiveDataClass.CONTACT_INFO,
    "raw_job_description": SensitiveDataClass.RAW_JOB_DESCRIPTION,
    "raw_model_response": SensitiveDataClass.INTERNAL_RAW_MODEL_RESPONSE,
    "raw_resume": SensitiveDataClass.RAW_CANDIDATE_PROFILE,
    "resume": SensitiveDataClass.RAW_CANDIDATE_PROFILE,
    "resume_pdf": SensitiveDataClass.RESUME_PDF_CONTENT,
    "resume_text": SensitiveDataClass.RAW_CANDIDATE_PROFILE,
    "source_profile": SensitiveDataClass.RAW_CANDIDATE_PROFILE,
    "summary": SensitiveDataClass.GENERATED_SUMMARY,
    "tex_content": SensitiveDataClass.FINAL_LATEX_BODY,
}


def sanitize_value(value: Any, *, key: str | None = None) -> Any:
    """Return a JSON-safe privacy-sanitized value."""

    data_class = classify_sensitive_key(key) if key is not None else None
    if data_class is not None:
        return redact_for_storage(value, data_class=data_class)
    if isinstance(value, dict):
        return {item_key: sanitize_value(item_value, key=item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    if isinstance(value, bytes):
        return redact_for_storage(value, data_class=SensitiveDataClass.RESUME_PDF_CONTENT)
    if isinstance(value, str):
        return _sanitize_inline_text(value)
    return value


def sanitize_exception_message(message: str, *, default: str = DEFAULT_EXCEPTION_MESSAGE) -> str:
    """Return a safe exception string suitable for logs and persistence."""

    cleaned = _sanitize_inline_text(message).strip()
    if not cleaned:
        return default
    if _looks_like_sensitive_freeform(message):
        return default
    if len(cleaned) > 240:
        return cleaned[:240] + "...[truncated]"
    return cleaned


def sanitize_diagnostic_text(message: str, *, default: str = DEFAULT_EXCEPTION_MESSAGE) -> str:
    """Return a compact diagnostic string without raw user content."""

    cleaned = sanitize_exception_message(message, default=default)
    if cleaned == default:
        return f"{default} ref={fingerprint_text(message)}"
    return cleaned


def redact_for_storage(value: Any, *, data_class: SensitiveDataClass) -> dict[str, Any]:
    """Return a metadata-only redaction summary for sensitive content."""

    if isinstance(value, bytes):
        digest = sha256(value).hexdigest()
        return {
            "redacted": True,
            "data_class": data_class.value,
            "byte_count": len(value),
            "sha256_prefix": digest[:12],
        }
    if isinstance(value, str):
        return {
            "redacted": True,
            "data_class": data_class.value,
            "char_count": len(value),
            "sha256_prefix": fingerprint_text(value).removeprefix("sha256:")[:12],
        }
    if isinstance(value, dict):
        return {
            "redacted": True,
            "data_class": data_class.value,
            "field_count": len(value),
            "sha256_prefix": fingerprint_object(value).removeprefix("sha256:")[:12],
        }
    if isinstance(value, (list, tuple, set)):
        return {
            "redacted": True,
            "data_class": data_class.value,
            "item_count": len(value),
            "sha256_prefix": fingerprint_object(list(value)).removeprefix("sha256:")[:12],
        }
    return {
        "redacted": True,
        "data_class": data_class.value,
        "value_type": type(value).__name__,
    }


def classify_sensitive_key(key: str | None) -> SensitiveDataClass | None:
    """Map a metadata key to a sensitive data class when it must be redacted."""

    if key is None:
        return None
    lowered = key.casefold()
    mapped = SENSITIVE_KEY_MAP.get(lowered)
    if mapped is not None:
        return mapped
    if any(token in lowered for token in {"email", "phone", "address", "linkedin", "github", "portfolio", "url", "link"}):
        return SensitiveDataClass.CONTACT_INFO
    if any(token in lowered for token in {"job_description", "jd_text"}):
        return SensitiveDataClass.RAW_JOB_DESCRIPTION
    if any(token in lowered for token in {"profile", "candidate", "resume_text"}):
        return SensitiveDataClass.RAW_CANDIDATE_PROFILE
    if any(token in lowered for token in {"summary", "bullet", "headline"}):
        return SensitiveDataClass.GENERATED_SUMMARY
    if any(token in lowered for token in {"latex", "tex_content"}):
        return SensitiveDataClass.FINAL_LATEX_BODY
    if any(token in lowered for token in {"pdf", "pdf_bytes"}):
        return SensitiveDataClass.RESUME_PDF_CONTENT
    if any(token in lowered for token in {"model_response", "llm_response", "openai_response"}):
        return SensitiveDataClass.INTERNAL_RAW_MODEL_RESPONSE
    return None


def fingerprint_text(value: str) -> str:
    """Return a stable digest string for one text payload."""

    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def fingerprint_object(value: Any) -> str:
    """Return a stable digest for a JSON-serializable object."""

    serialized = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return fingerprint_text(serialized)


def _sanitize_inline_text(value: str) -> str:
    sanitized = OPENAI_KEY_PATTERN.sub("[REDACTED_API_KEY]", value)
    sanitized = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)
    sanitized = PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    sanitized = URL_PATTERN.sub("[REDACTED_URL]", sanitized)
    return sanitized


def _looks_like_sensitive_freeform(value: str) -> bool:
    lowered = value.casefold()
    if "\n" in value or len(value) > 160:
        return True
    if OPENAI_KEY_PATTERN.search(value) or EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value):
        return True
    return any(
        token in lowered
        for token in {
            "raw resume",
            "resume text",
            "job description",
            "source profile",
            "candidate profile",
            "generated summary",
            "generated bullet",
            "latex body",
            "model response",
        }
    )
