"""AI provider abstraction layer."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AIProviderConfig(BaseModel):
    """Base configuration for AI providers."""

    provider: str
    model: str


class AIResponse(BaseModel):
    """Standardized AI response wrapper."""

    text: str
    raw_response: Any


class AIProvider(ABC):
    """Abstract interface for AI providers."""

    def __init__(self, config: AIProviderConfig):
        self.config = config

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> AIResponse:
        """Execute a text completion request."""
        pass

    @abstractmethod
    def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Execute a JSON completion request."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider has required credentials."""
        pass

    @abstractmethod
    def get_api_key_status(self) -> dict[str, bool]:
        """Return which API keys are configured."""
        pass


class GeminiProvider(AIProvider):
    """Google Gemini provider implementation."""

    def __init__(self, config: AIProviderConfig, api_key: str | None):
        super().__init__(config)
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        """Lazy-load Gemini client."""
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self._api_key)
            except ImportError:
                raise RuntimeError("google-genai package required for Gemini provider")
        return self._client

    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> AIResponse:
        client = self._get_client()

        response = client.models.generate_content(
            model=self.config.model,
            contents=prompt,
            config={
                "temperature": temperature,
                "system_instruction": system_prompt,
            },
        )
        return AIResponse(
            text=response.text or "",
            raw_response=response,
        )

    def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        client = self._get_client()

        response = client.models.generate_content(
            model=self.config.model,
            contents=prompt,
            config={
                "temperature": temperature,
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
            },
        )
        
        import json
        text = response.text or "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "Failed to parse JSON response", "text": text}

    def is_configured(self) -> bool:
        return self._api_key is not None and len(self._api_key or "") > 0

    def get_api_key_status(self) -> dict[str, bool]:
        return {"gemini_api_key_configured": self.is_configured()}


def build_ai_provider(
    provider: str,
    model: str,
    gemini_api_key: str | None = None,
) -> AIProvider:
    """Build an AI provider based on configuration."""
    from pydantic import ValidationError

    config = AIProviderConfig(provider=provider, model=model)

    if provider.lower() == "gemini":
        return GeminiProvider(config, gemini_api_key)
    else:
        raise ValueError(
            f"Unsupported AI provider: {provider}. Supported: gemini"
        )
