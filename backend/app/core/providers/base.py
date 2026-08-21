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
