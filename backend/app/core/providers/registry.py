"""Small explicit provider registry; business services depend only on protocols."""

from dataclasses import dataclass, field

from app.core.config import Settings, settings
from app.core.providers.base import EmbeddingProvider, LLMProvider, ProviderNotConfigured
from app.core.providers.noop import NoopEmbeddingProvider, NoopLLMProvider


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
        if config.llm_provider == "bedrock":
            from app.core.providers.llm_bedrock import BedrockLLMProvider

            registry.llms["bedrock"] = BedrockLLMProvider(config)
        elif config.llm_provider != "noop":
            raise ProviderNotConfigured(f"unknown LLM provider: {config.llm_provider}")
        return registry


providers = ProviderRegistry(
    embeddings={"noop": NoopEmbeddingProvider()}, llms={"noop": NoopLLMProvider()}
)


def configured_registry() -> ProviderRegistry:
    return ProviderRegistry.from_settings(settings)
