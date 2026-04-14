"""Backwards compatibility - redirects to gemini_client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Re-export from gemini_client for backwards compatibility
from .gemini_client import build_gemini_client as build_openai_client
from .gemini_client import create_json_response_text

__all__ = ["build_openai_client", "create_json_response_text"]

if TYPE_CHECKING:
    from google.genai.client import Client as OpenAI
