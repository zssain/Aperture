"""The provider-agnostic source-adapter boundary.

Adapters know provider formats. Nothing downstream of ``normalize`` may reference a
provider-specific field: the only currency between an adapter and the rest of the
system is :class:`NormalizedEvent`.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.models.enums import EventDirection, SourceTier, SourceType
from app.models.source import SourceConnection


@dataclass(frozen=True)
class FetchPeriod:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class RawSourcePayload:
    """Opaque provider payload. ``raw`` is provider-shaped and never leaves the adapter."""

    provider: str
    account_ref: str
    period: FetchPeriod
    raw: dict[str, Any]


@dataclass(frozen=True)
class NormalizedEvent:
    """The provider-agnostic evidence event. ``counterparty`` is a raw name held only
    in memory — the normalizer hashes it and never persists it in the clear."""

    occurred_at: datetime
    direction: EventDirection
    amount_paise: int
    description: str
    counterparty: str | None
    balance_paise: int | None
    external_id: str | None


class ProviderTimeoutError(Exception):
    """The provider did not respond in time; the connection becomes UNAVAILABLE."""


class ProviderError(Exception):
    """The provider returned an error."""


@runtime_checkable
class SourceAdapter(Protocol):
    source_type: SourceType
    tier: SourceTier

    async def fetch(
        self, connection: SourceConnection, period: FetchPeriod
    ) -> RawSourcePayload: ...

    def normalize(self, payload: RawSourcePayload) -> list[NormalizedEvent]: ...
