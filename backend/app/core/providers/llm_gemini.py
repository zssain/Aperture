"""Google Gemini text-generation provider for optional applicant notices.

Mirrors the Bedrock provider's contract: a temperature-0 structured-JSON completion
over an allow-listed decision context, validated against the caller's schema. The
notices pipeline treats any failure here as an honest miss and falls back to the
deterministic template, so this provider never becomes a correctness dependency.
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

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Only these decision-facing fields are ever sent to the model — the same PII/scope
# discipline the Bedrock provider enforces.
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

# Force the {subject, body, language} shape the notice validator expects.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "subject": {"type": "STRING"},
        "body": {"type": "STRING"},
        "language": {"type": "STRING"},
    },
    "required": ["subject", "body", "language"],
}


class GeminiLLMProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.gemini_api_key:
            raise ProviderNotConfigured(
                "LLM_PROVIDER=gemini requires a Gemini API key (Gemini_api_Key)"
            )
        self.model_id = settings.gemini_model_id
        self._max_tokens = settings.llm_max_tokens
        self._api_key = settings.gemini_api_key
        self._url = _ENDPOINT.format(model=self.model_id)
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
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(payload, sort_keys=True, default=str)}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self._max_tokens,
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
            },
        }
        try:
            response = await self._client.post(
                self._url,
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json=body,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Gemini request failed: {exc}") from exc
        if response.status_code in {429, 503}:
            raise ProviderThrottled(f"Gemini throttled (HTTP {response.status_code})")
        if response.status_code != 200:
            raise ProviderResponseError(f"Gemini returned HTTP {response.status_code}")
        try:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("Gemini returned malformed structured output") from exc
        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            raise ProviderResponseError("Gemini output failed schema validation") from exc
