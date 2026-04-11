"""Small shared OpenAI Responses API helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai import OpenAI


def build_openai_client() -> OpenAI:
    """Build the default OpenAI client used by AI-backed phases."""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required to run AI-backed phases.") from exc

    return OpenAI()


def create_json_response_text(
    *,
    client: OpenAI,
    model: str,
    input_payload: str | list[dict[str, Any]],
) -> str:
    """Execute one JSON-only Responses API call and return the raw text payload."""

    response = client.responses.create(
        model=model,
        input=input_payload,
        text={"format": {"type": "json_object"}},
    )
    response_text = getattr(response, "output_text", "")
    if not response_text.strip():
        raise RuntimeError("AI model returned an empty response.")
    return response_text
