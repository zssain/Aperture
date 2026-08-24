"""Strict provider protocols. Unconfigured infrastructure never fabricates values."""

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ProviderNotConfigured(RuntimeError):  # noqa: N818 - required public contract name
    pass


class ProviderUnavailable(RuntimeError):  # noqa: N818 - provider state, not a domain error
    pass


class ProviderThrottled(ProviderUnavailable):
    pass


class ProviderResponseError(ProviderUnavailable):
    pass


class EmbeddingDimensionError(ValueError):
    pass


# Fields that must never leave the process for an LLM — raw ledger text, counterparty
# identity, embeddings, credentials. This deny-list is checked at every nesting depth, so any
# grounded caller (notices, the decision explainer, the architecture guide) may send safe
# structured facts, but a forbidden key appearing anywhere raises. Applicant name is
# intentionally NOT forbidden: a decision notice must be able to address the applicant.
FORBIDDEN_LLM_FIELDS = frozenset(
    {
        "counterparty",
        "counterparty_hash",
        "narration",
        "normalized_narration",
        "description",
        "embedding",
        "vector",
        "account_number",
        "session_token",
        "password",
        "file",
        "file_contents",
        "document_text",
        "raw",
    }
)


def assert_llm_payload_safe(payload: dict[str, Any]) -> None:
    """Raise :class:`ProviderResponseError` if a forbidden field appears at any depth."""

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).casefold() in FORBIDDEN_LLM_FIELDS:
                    raise ProviderResponseError(f"LLM payload contains a forbidden field: {key}")
                walk(child)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(payload)


class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LLMProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    async def complete(
        self, system: str, payload: dict[str, Any], schema: type[SchemaT]
    ) -> SchemaT: ...
