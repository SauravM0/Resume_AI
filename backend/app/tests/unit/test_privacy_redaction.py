from __future__ import annotations

import json
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.observability.logging import JsonLogFormatter
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import OrchestrationError
from backend.app.privacy import sanitize_exception_message


def test_json_logging_redacts_sensitive_metadata() -> None:
    formatter = JsonLogFormatter()
    logger = logging.getLogger("resume_optimizer.privacy_test")
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        1,
        "privacy_test",
        (),
        None,
        extra={
            "event_name": "privacy_test",
            "outcome": "success",
            "metadata": {
                "job_description_text": "Build APIs for fintech resumes.",
                "email": "user@example.com",
                "phone": "+1 555 123 4567",
                "notes": "contact at user@example.com",
            },
        },
    )

    rendered = formatter.format(record)

    assert "Build APIs for fintech resumes." not in rendered
    assert "user@example.com" not in rendered
    assert "555 123 4567" not in rendered
    payload = json.loads(rendered)
    assert payload["metadata"]["job_description_text"]["redacted"] is True
    assert payload["metadata"]["email"]["data_class"] == "contact_info"
    assert payload["metadata"]["notes"] == "contact at [REDACTED_EMAIL]"


def test_orchestration_error_sanitizes_exception_text() -> None:
    error = OrchestrationError(
        "provider leaked sk-test-123 and raw resume text",
        failure_type=OrchestrationFailureType.GENERATION_PROVIDER,
        stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
        operator_diagnostic_message="raw resume text in provider trace",
    )

    assert "sk-test-123" not in str(error)
    assert "raw resume text" not in str(error)
    assert "raw resume text" not in error.operator_diagnostic_message
    assert error.to_safe_api_detail()["message"] == "Structured resume generation is temporarily unavailable."


def test_sanitize_exception_message_redacts_inline_contact_data() -> None:
    sanitized = sanitize_exception_message("failure while calling https://example.com for alex@example.com")

    assert "https://example.com" not in sanitized
    assert "alex@example.com" not in sanitized
    assert "[REDACTED_URL]" in sanitized or "Sensitive error details" in sanitized
