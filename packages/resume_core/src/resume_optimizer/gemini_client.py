"""Small shared Gemini Responses API helpers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from google.genai.client import Client


def build_gemini_client() -> "Client":
    """Build the default Gemini client used by AI-backed phases."""

    try:
        from google.genai import client as genai_client

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is required.")
        
        return genai_client.Client(api_key=api_key)
    except ImportError as exc:
        raise RuntimeError("The google-genai package is required to run AI-backed phases.") from exc


def create_json_response_text(
    *,
    client: "Client",
    model: str,
    input_payload: str | list[dict[str, Any]],
) -> str:
    """Execute one JSON-only Gemini API call and return the raw text payload."""

    # If input_payload is a list of dicts (chat format), convert to string
    if isinstance(input_payload, list):
        # Extract the content from user messages
        prompt_parts = []
        for item in input_payload:
            if isinstance(item, dict):
                role = item.get("role", "user")
                content = item.get("content", "")
                prompt_parts.append(f"[{role}]: {content}")
        prompt = "\n".join(prompt_parts)
    else:
        prompt = input_payload

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )
    
    response_text = response.text or ""
    if not response_text.strip():
        raise RuntimeError("AI model returned an empty response.")
    return response_text
