"""OpenAI chat-completions provider for optional applicant notices.

Mirrors the Bedrock/Gemini contract: a temperature-0 structured-JSON completion over
an allow-listed decision context, validated against the caller's schema. Any failure
falls back to the deterministic notice template, so this is never a correctness
dependency. Uses strict json_schema response formatting so the {subject, body,
language} shape is guaranteed by the API.
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
)

_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Only these decision-facing fields are ever sent to the model — the same PII/scope
# discipline the Bedrock and Gemini providers enforce.
NOTICE_CONTEXT_ALLOWLIST = frozenset(
    {
        "outcome",
        "terms",
        "reasons",
        "recourse",
        "expiry_date",
        "applicant_display_name",
        "language",
    }
)

_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "applicant_notice",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["subject", "body", "language"],
            "additionalProperties": False,
        },
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
        extras = set(payload) - NOTICE_CONTEXT_ALLOWLIST
        if extras:
            raise ProviderResponseError(
                f"LLM payload contains non-allow-listed fields: {sorted(extras)}"
            )
        body = {
            "model": self.model_id,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "response_format": _RESPONSE_FORMAT,
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
