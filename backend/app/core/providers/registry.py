"""Small explicit provider registry; business services depend only on protocols."""

import contextlib
from dataclasses import dataclass, field

from app.core.config import Settings, settings
from app.core.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderNotConfigured,
    ProviderUnavailable,
)
from app.core.providers.noop import NoopEmbeddingProvider, NoopLLMProvider


def _build_llm(name: str, config: Settings) -> LLMProvider:
    """Construct one LLM provider by name (each validates its own credentials)."""
    if name == "bedrock":
        from app.core.providers.llm_bedrock import BedrockLLMProvider

        return BedrockLLMProvider(config)
    if name == "gemini":
        from app.core.providers.llm_gemini import GeminiLLMProvider

        return GeminiLLMProvider(config)
    if name == "openai":
        from app.core.providers.llm_openai import OpenAILLMProvider

        return OpenAILLMProvider(config)
    raise ProviderNotConfigured(f"unknown LLM provider: {name}")


@dataclass
class ProviderRegistry:
    embeddings: dict[str, EmbeddingProvider] = field(default_factory=dict)
    llms: dict[str, LLMProvider] = field(default_factory=dict)

    def embedding(self, name: str) -> EmbeddingProvider:
        try:
            return self.embeddings[name]
        except KeyError as exc:
            raise ProviderNotConfigured(f"unknown embedding provider: {name}") from exc

    def llm(self, name: str) -> LLMProvider:
        try:
            return self.llms[name]
        except KeyError as exc:
            raise ProviderNotConfigured(f"unknown LLM provider: {name}") from exc

    @classmethod
    def from_settings(cls, config: Settings) -> "ProviderRegistry":
        registry = cls(
            embeddings={"noop": NoopEmbeddingProvider()},
            llms={"noop": NoopLLMProvider()},
        )
        if config.embedding_provider == "local":
            from app.core.providers.embeddings_local import LocalEmbeddingProvider

            registry.embeddings["local"] = LocalEmbeddingProvider(
                config.embedding_model_id, config.embedding_dimension
            )
        elif config.embedding_provider == "bedrock":
            if not config.allow_external_embeddings:
                raise ProviderNotConfigured(
                    "EMBEDDING_PROVIDER=bedrock requires ALLOW_EXTERNAL_EMBEDDINGS=true"
                )
            from app.core.providers.embeddings_bedrock import BedrockEmbeddingProvider

            registry.embeddings["bedrock"] = BedrockEmbeddingProvider(config)
        elif config.embedding_provider == "gemini":
            if not config.allow_external_embeddings:
                raise ProviderNotConfigured(
                    "EMBEDDING_PROVIDER=gemini requires ALLOW_EXTERNAL_EMBEDDINGS=true"
                )
            from app.core.providers.embeddings_gemini import GeminiEmbeddingProvider

            registry.embeddings["gemini"] = GeminiEmbeddingProvider(config)
        elif config.embedding_provider != "noop":
            raise ProviderNotConfigured(f"unknown embedding provider: {config.embedding_provider}")
        if config.llm_provider != "noop":
            # The primary is strict: a misconfigured primary should fail loudly.
            registry.llms[config.llm_provider] = _build_llm(config.llm_provider, config)
        # The backup is best-effort: the assistants try it only if the primary errors,
        # so a missing key or unreachable backup must never break the registry itself.
        backup = config.llm_backup_provider
        if backup and backup not in {"noop", config.llm_provider}:
            with contextlib.suppress(ProviderNotConfigured, ProviderUnavailable):
                registry.llms[backup] = _build_llm(backup, config)
        return registry


providers = ProviderRegistry(
    embeddings={"noop": NoopEmbeddingProvider()}, llms={"noop": NoopLLMProvider()}
)


def configured_registry() -> ProviderRegistry:
    return ProviderRegistry.from_settings(settings)
