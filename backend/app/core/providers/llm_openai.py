"""OpenAI chat-completions provider for optional applicant notices.

Mirrors the Bedrock/Gemini contract: a temperature-0 structured-JSON completion over
a PII-guarded context (see ``assert_llm_payload_safe``), validated against the caller's
schema. Any failure falls back to deterministic output, so this is never a correctness
dependency. The json_schema response format is derived from the caller's own schema, so
notices and the grounded assistants each get exactly the shape they expect.
"""

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.providers.base import (
    ProviderNotConfigured,
    ProviderResponseError,
    ProviderThrottled,
    ProviderUnavailable,
    SchemaT,
    assert_llm_payload_safe,
)

_ENDPOINT = "https://api.openai.com/v1/chat/completions"


def _response_format(schema: type[SchemaT]) -> dict[str, Any]:
    """Ask OpenAI for JSON matching the caller's schema (notice or assistant)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__.lstrip("_").lower() or "structured_output",
            "strict": False,
            "schema": schema.model_json_schema(),
        },
    }


class OpenAILLMProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.openai_api_key:
            raise ProviderNotConfigured("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        self.model_id = settings.openai_model_id
        self._max_tokens = settings.llm_max_tokens
        self._api_key = settings.openai_api_key
        self._client = client or httpx.AsyncClient(timeout=settings.llm_notice_timeout_seconds)

    async def complete(
        self, system: str, payload: dict[str, Any], schema: type[SchemaT]
    ) -> SchemaT:
        assert_llm_payload_safe(payload)
        body = {
            "model": self.model_id,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "response_format": _response_format(schema),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, sort_keys=True, default=str)},
            ],
        }
        try:
            response = await self._client.post(
                _ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"OpenAI request failed: {exc}") from exc
        if response.status_code in {429, 503}:
            raise ProviderThrottled(f"OpenAI throttled (HTTP {response.status_code})")
        if response.status_code != 200:
            raise ProviderResponseError(f"OpenAI returned HTTP {response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("OpenAI returned malformed structured output") from exc
        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            raise ProviderResponseError("OpenAI output failed schema validation") from exc
