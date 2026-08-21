from typing import Any

from app.core.providers.base import ProviderNotConfigured, SchemaT


class NoopEmbeddingProvider:
    model_id = "noop"
    dimension = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise ProviderNotConfigured("embedding provider is not configured")


class NoopLLMProvider:
    model_id = "noop"

    async def complete(
        self, system: str, payload: dict[str, Any], schema: type[SchemaT]
    ) -> SchemaT:
        del system, payload, schema
        raise ProviderNotConfigured("LLM provider is not configured")
