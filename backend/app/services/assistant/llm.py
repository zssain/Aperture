"""Provider fallback for the grounded assistants.

The assistants try the configured primary LLM first and, if it errors, a best-effort
backup (Gemini by default) before the caller drops to its deterministic summary. This
keeps "Ask AI" answering through a single-provider outage without ever becoming a hard
dependency — every provider still enforces the same egress guard and schema validation.
"""

from typing import TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger
from app.core.providers.base import (
    ProviderNotConfigured,
    ProviderUnavailable,
)
from app.core.providers.registry import configured_registry

logger = get_logger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _provider_chain() -> list[str]:
    """Primary then backup, de-duplicated, skipping the noop provider."""
    chain: list[str] = []
    for name in (settings.llm_provider, settings.llm_backup_provider):
        if name and name != "noop" and name not in chain:
            chain.append(name)
    return chain


async def complete_with_fallback(
    system: str, payload: dict[str, object], schema: type[SchemaT]
) -> SchemaT | None:
    """Return the first provider's validated output, or None if the LLM is disabled or
    every provider in the chain errors (the caller then uses its deterministic fallback)."""
    if not settings.llm_notices_enabled:
        return None
    try:
        registry = configured_registry()
    except (ProviderNotConfigured, ProviderUnavailable, RuntimeError):
        return None
    for name in _provider_chain():
        try:
            provider = registry.llm(name)
        except ProviderNotConfigured:
            continue  # backup not registered (e.g. no credentials)
        try:
            return await provider.complete(system, payload, schema)
        except Exception as exc:  # provider/timeout/parse — try the next in the chain
            logger.info("assistant_llm_fallback", provider=name, reason=type(exc).__name__)
            continue
    return None
