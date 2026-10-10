"""AI provider adapters.

Only providers with documented, stable API formats are implemented:
- `openai_compatible`: POST {base_url}/chat/completions (OpenAI, OpenRouter,
  Groq, local gateways, etc.)
- `anthropic`: POST https://api.anthropic.com/v1/messages

The adapter interface is provider-agnostic so another compatible provider can
be configured without rewriting the analysis pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class AiError(Exception):
    """Raised when an AI provider call fails."""

    def __init__(self, message: str, *, code: str = "ai_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class AiUnavailableError(AiError):
    """Raised when the provider is not configured or unreachable."""


@dataclass
class AiCompletion:
    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class BaseAiAdapter:
    """Minimal chat interface: give instructions + evidence, get text back."""

    provider_name = "base"

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 3000,
    ) -> AiCompletion:
        raise NotImplementedError


class OpenAiCompatibleAdapter(BaseAiAdapter):
    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 45.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 3000,
    ) -> AiCompletion:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # Documented OpenAI response_format; tolerated by most compatible servers.
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise AiUnavailableError(
                "The AI provider did not respond in time.", code="ai_timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise AiUnavailableError(
                "The AI provider could not be reached.", code="ai_unreachable"
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            logger.warning("AI provider rejected credentials (status %s)", response.status_code)
            raise AiUnavailableError(
                "The configured AI credentials were rejected. Check AI_API_KEY.",
                code="ai_auth_failed",
            )
        if response.status_code == 429:
            raise AiUnavailableError(
                "The AI provider rate limit was reached.", code="ai_rate_limited"
            )
        if response.status_code >= 500:
            raise AiUnavailableError(
                "The AI provider is currently unavailable.", code="ai_provider_error"
            )
            
        if response.status_code >= 400:
            logger.warning(
                "AI provider error details (status %s): %s",
                response.status_code,
                response.text[:1000],
            )
            raise AiUnavailableError(
                "The AI request was rejected by the provider.",
                code="ai_bad_request",
            )


        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AiUnavailableError(
                "The AI provider returned an unreadable response.", code="ai_bad_response"
            ) from exc

        usage = data.get("usage") or {}
        return AiCompletion(
            text=str(text),
            model=self._model,
            provider=self.provider_name,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


class AnthropicAdapter(BaseAiAdapter):
    """Anthropic Messages API — https://docs.anthropic.com/en/api/messages"""

    provider_name = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"

    def __init__(self, *, api_key: str, model: str, timeout: float = 45.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 3000,
    ) -> AiCompletion:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": 0.2,
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise AiUnavailableError(
                "The AI provider did not respond in time.", code="ai_timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise AiUnavailableError(
                "The AI provider could not be reached.", code="ai_unreachable"
            ) from exc

        if response.status_code in (401, 403):
            raise AiUnavailableError(
                "The configured AI credentials were rejected. Check AI_API_KEY.",
                code="ai_auth_failed",
            )
        if response.status_code == 429:
            raise AiUnavailableError(
                "The AI provider rate limit was reached.", code="ai_rate_limited"
            )
        
        if response.status_code >= 400:
            raise AiUnavailableError(
                "The AI request was rejected by the provider.",
                code="ai_bad_request",
            )


        try:
            data = response.json()
            blocks = data.get("content", [])
            text = "".join(
                b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
            )
        except (ValueError, TypeError) as exc:
            raise AiUnavailableError(
                "The AI provider returned an unreadable response.", code="ai_bad_response"
            ) from exc
        if not text.strip():
            raise AiUnavailableError(
                "The AI provider returned an empty response.", code="ai_empty_response"
            )

        usage = data.get("usage") or {}
        return AiCompletion(
            text=text,
            model=self._model,
            provider=self.provider_name,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )


def build_adapter(
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout: float,
) -> BaseAiAdapter:
    """Create an adapter for a configured provider, or raise AiUnavailableError."""
    if provider == "anthropic":
        if not api_key or not model:
            raise AiUnavailableError("AI provider is not configured.", code="ai_not_configured")
        return AnthropicAdapter(api_key=api_key, model=model, timeout=timeout)
    if provider == "openai_compatible":
        if not model:
            raise AiUnavailableError("AI model is not configured.", code="ai_not_configured")
        return OpenAiCompatibleAdapter(
            api_key=api_key, model=model, base_url=base_url, timeout=timeout
        )
    raise AiUnavailableError(
        "AI analysis is currently unavailable. Your collected search results are preserved.",
        code="ai_not_configured",
    )
