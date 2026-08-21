import pytest
from app.core.config import Settings
from app.core.providers.base import ProviderNotConfigured, ProviderResponseError
from app.core.providers.llm_bedrock import BedrockLLMProvider
from app.core.providers.registry import ProviderRegistry


class Client:
    def converse(self, **request: object) -> dict[str, object]:
        raise AssertionError(f"egress should not occur: {request}")


def base_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        frontend_origin="http://localhost:5173",
    )


def test_external_embedding_default_blocks_applicant_text_egress() -> None:
    with pytest.raises(ProviderNotConfigured):
        ProviderRegistry.from_settings(
            Settings(
                database_url="postgresql+asyncpg://x:x@localhost/x",
                frontend_origin="http://localhost:5173",
                embedding_provider="bedrock",
                allow_external_embeddings=False,
            )
        )


def test_llm_runtime_allowlist_rejects_ledger_field() -> None:
    with pytest.raises(ProviderResponseError):
        BedrockLLMProvider(base_settings(), Client())._converse(
            "system", {"outcome": "DECLINE", "normalized_narration": "private"}
        )
