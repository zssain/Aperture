import pytest
from app.core.config import Settings
from app.core.providers.base import ProviderNotConfigured
from app.core.providers.noop import NoopEmbeddingProvider, NoopLLMProvider
from app.core.providers.registry import ProviderRegistry
from app.services.notices.validator import LLMNotice


def test_noop_embedding_raises() -> None:
    with pytest.raises(ProviderNotConfigured):
        NoopEmbeddingProvider().embed(["merchant"])


async def test_noop_llm_raises() -> None:
    with pytest.raises(ProviderNotConfigured):
        await NoopLLMProvider().complete("system", {}, LLMNotice)


def test_unknown_provider_fails_loudly() -> None:
    with pytest.raises(ProviderNotConfigured):
        ProviderRegistry.from_settings(
            Settings(
                database_url="postgresql+asyncpg://x:x@localhost/x",
                frontend_origin="http://localhost:5173",
                embedding_provider="unknown",
            )
        )


def test_external_embedding_requires_explicit_opt_in() -> None:
    with pytest.raises(ProviderNotConfigured):
        ProviderRegistry.from_settings(
            Settings(
                database_url="postgresql+asyncpg://x:x@localhost/x",
                frontend_origin="http://localhost:5173",
                embedding_provider="bedrock",
                allow_external_embeddings=False,
            )
        )
