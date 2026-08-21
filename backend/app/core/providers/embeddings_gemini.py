"""Google Gemini embedding provider. All Gemini HTTP stays inside this boundary.

``gemini-embedding-001`` natively emits 3072-dimensional vectors but honours
``outputDimensionality``; it is reduced to the configured ``embedding_dimension`` so
the vectors line up with the merchant-catalogue pgvector column. Reduced-dimension
Gemini vectors are not unit-normalised at source, so we L2-normalise here — matching
the ``normalize=true`` treatment the Bedrock provider requests.

The public Gemini tier is rate-limited, so 429/503 responses are retried with a
bounded backoff that honours the server's suggested delay (``Retry-After`` header or
the ``RetryInfo.retryDelay`` in the error body).
"""

import math
import re
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.providers.base import (
    EmbeddingDimensionError,
    ProviderNotConfigured,
    ProviderResponseError,
    ProviderThrottled,
)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 8
_MAX_BACKOFF_SECONDS = 30.0
_DELAY_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)s")


def _suggested_delay(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        for detail in response.json().get("error", {}).get("details", []):
            raw = detail.get("retryDelay")
            if isinstance(raw, str):
                match = _DELAY_RE.search(raw)
                if match:
                    return float(match.group(1))
    except (ValueError, AttributeError):
        pass
    return min(2.0**attempt, _MAX_BACKOFF_SECONDS)


class GeminiEmbeddingProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.allow_external_embeddings:
            raise RuntimeError("external embeddings are disabled")
        if not settings.gemini_api_key:
            raise ProviderNotConfigured(
                "EMBEDDING_PROVIDER=gemini requires a Gemini API key (Gemini_api_Key)"
            )
        self.model_id = settings.gemini_embedding_model_id
        self.dimension = settings.embedding_dimension
        self._api_key = settings.gemini_api_key
        self._url = _ENDPOINT.format(model=self.model_id)
        self._client = client or httpx.Client(timeout=30.0)

    def _embed_one(self, text: str) -> list[float]:
        last_status = 0
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.post(
                    self._url,
                    headers={
                        "x-goog-api-key": self._api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "content": {"parts": [{"text": text}]},
                        "outputDimensionality": self.dimension,
                    },
                )
            except httpx.HTTPError as exc:  # network / timeout
                raise ProviderResponseError(f"Gemini embedding request failed: {exc}") from exc
            if response.status_code == 200:
                body: dict[str, Any] = response.json()
                values = body.get("embedding", {}).get("values")
                if not isinstance(values, list) or len(values) != self.dimension:
                    raise EmbeddingDimensionError(
                        f"Gemini returned {len(values) if isinstance(values, list) else 0} "
                        f"dimensions; expected {self.dimension}"
                    )
                norm = math.sqrt(sum(float(v) * float(v) for v in values)) or 1.0
                return [round(float(v) / norm, 8) for v in values]
            last_status = response.status_code
            if response.status_code in _RETRYABLE and attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_suggested_delay(response, attempt))
                continue
            raise ProviderResponseError(f"Gemini embedding returned HTTP {response.status_code}")
        raise ProviderThrottled(f"Gemini embedding throttled after retries (HTTP {last_status})")

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = [self._embed_one(text) for text in texts]
        if len(result) != len(texts):
            raise ProviderResponseError("Gemini omitted an embedding")
        return result
