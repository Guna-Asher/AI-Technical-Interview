"""Minimal OpenRouter chat client. All LLM requests go through here; credentials stay on the backend."""

import json
import logging
import re
from collections.abc import Callable
from typing import TypeVar

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LLMError(Exception):
    """Base class for LLM failures. Messages never contain credentials or prompt text."""


class LLMNotConfigured(LLMError):
    """OPENROUTER_API_KEY or OPENROUTER_MODEL is missing."""


class LLMRateLimited(LLMError):
    """OpenRouter or the underlying provider returned HTTP 429."""


class LLMTimeout(LLMError):
    """The request timed out."""


class LLMProviderError(LLMError):
    """OpenRouter or the provider failed (HTTP error, network error, or an error object in the body)."""


class LLMBadResponse(LLMError):
    """The reply was empty, not valid JSON, or failed validation."""


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_json_object(content: str) -> dict:
    """Parse the model's reply as a JSON object, tolerating Markdown code fences and surrounding prose."""
    text = content.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    candidates = [text]
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{") : text.rindex("}") + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
        raise LLMBadResponse("The model's reply was JSON but not a JSON object.")
    raise LLMBadResponse("The model's reply was not valid JSON.")


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None,
        model: str | None,
        base_url: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport  # only tests pass this

    def complete_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
        """Send one chat request and return the reply parsed as a JSON object."""
        if not self._api_key:
            raise LLMNotConfigured("OPENROUTER_API_KEY is not configured. Set it in .env and restart the backend.")
        if not self._model:
            raise LLMNotConfigured("OPENROUTER_MODEL is not configured. Set it in .env and restart the backend.")

        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=httpx.Timeout(self._timeout, connect=10.0), transport=self._transport) as client:
                response = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeout("The request to OpenRouter timed out.") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Could not reach OpenRouter ({type(exc).__name__}).") from exc

        if response.status_code == 429:
            raise LLMRateLimited("OpenRouter rate limit reached. Try again shortly.")
        if response.status_code in (401, 403):
            raise LLMProviderError(f"OpenRouter rejected the API key (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise LLMProviderError(f"OpenRouter returned HTTP {response.status_code}.{_provider_message(response)}")

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMBadResponse("OpenRouter returned a non-JSON response.") from exc
        if isinstance(body, dict) and body.get("error") and not body.get("choices"):
            raise LLMProviderError(f"OpenRouter reported an error.{_provider_message(response)}")
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMBadResponse("OpenRouter returned an unexpected response shape.") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMBadResponse("The model returned an empty reply.")

        logger.info("OpenRouter request ok (model=%s, reply_chars=%d)", self._model, len(content))
        return parse_json_object(content)


def _provider_message(response: httpx.Response) -> str:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return ""
    return f" Provider message: {str(message)[:200]}" if message else ""


def get_llm() -> OpenRouterClient:
    """FastAPI dependency. Built even without credentials; the check happens when a request is attempted."""
    settings = get_settings()
    return OpenRouterClient(
        settings.openrouter_api_key,
        settings.openrouter_model,
        settings.openrouter_base_url,
        settings.openrouter_timeout_seconds,
    )


def complete_validated(
    llm: OpenRouterClient,
    system: str,
    user: str,
    validate: Callable[[dict], T],
    *,
    temperature: float = 0.2,
    max_attempts: int | None = None,
) -> T:
    """Call the model and validate its reply. Invalid output is retried (the reason is added to the prompt).

    Configuration, rate-limit, timeout and provider errors are not retried.
    """
    attempts = max_attempts or get_settings().llm_max_attempts
    prompt = user
    reason = ""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return validate(llm.complete_json(system, prompt, temperature))
        except (LLMBadResponse, ValueError) as exc:
            last_error = exc
            reason = str(exc)[:300]
            logger.warning("Model output rejected on attempt %d of %d: %s", attempt, attempts, reason)
            prompt = (
                f"{user}\n\nYour previous reply was rejected: {reason}\n"
                "Reply again with corrected JSON only, following the required format exactly."
            )
    raise LLMBadResponse(f"The model did not return valid output after {attempts} attempt(s): {reason}") from last_error
