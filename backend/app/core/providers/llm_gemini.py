"""Google Gemini text-generation provider for optional applicant notices.

Mirrors the Bedrock provider's contract: a temperature-0 structured-JSON completion
over a PII-guarded context (see ``assert_llm_payload_safe``), validated against the
caller's schema. Every grounded caller (notices, the decision explainer, the
architecture guide) treats any failure here as an honest miss and falls back to
deterministic output, so this provider never becomes a correctness dependency.
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

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_JSON_TO_GEMINI_TYPE = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _to_gemini_schema(node: dict[str, Any]) -> dict[str, Any]:
    """Convert a (flat) pydantic JSON schema into Gemini's responseSchema shape."""
    node_type = node.get("type", "string")
    if node_type == "object":
        out: dict[str, Any] = {
            "type": "OBJECT",
            "properties": {
                name: _to_gemini_schema(prop)
                for name, prop in node.get("properties", {}).items()
            },
        }
        if node.get("required"):
            out["required"] = node["required"]
        return out
    if node_type == "array":
        return {"type": "ARRAY", "items": _to_gemini_schema(node.get("items", {"type": "string"}))}
    return {"type": _JSON_TO_GEMINI_TYPE.get(node_type, "STRING")}


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
        assert_llm_payload_safe(payload)
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
                "responseSchema": _to_gemini_schema(schema.model_json_schema()),
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
