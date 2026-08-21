"""The manipulation engine's input - and the type-level guarantee of independence.

``ManipulationContext`` is the ONLY thing a detector or the service is handed. It carries
ledger events, declared application data, source metadata and cross-applicant signals -
and nothing else. There is deliberately no field whose type could hold a PD, a risk
assessment, a coverage score or an affordability result, so a later edit that tries to
feed the fraud engine the credit score is a type-check failure, not a runtime check
(invariant 5: fraud never reads risk).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.models.enums import EventDirection


@dataclass(frozen=True)
class LedgerEventView:
    """A purified, provider-agnostic view of one ledger event."""

    event_id: uuid.UUID
    occurred_at: datetime
    direction: EventDirection
    amount_paise: int
    balance_paise: int | None
    description: str | None
    counterparty_hash: str | None
    source_snapshot_id: uuid.UUID | None


@dataclass(frozen=True)
class DeclaredApplication:
    """What the applicant asserted - never what a model inferred."""

    application_id: uuid.UUID | None
    occupation: str | None
    claimed_period_start: datetime | None
    claimed_period_end: datetime | None


@dataclass(frozen=True)
class ProvenanceView:
    code: str
    severity: str  # LOW | MEDIUM | HIGH
    detail: str


@dataclass(frozen=True)
class SourceMetadataView:
    """A source snapshot's provenance plus the ledger events it produced."""

    source_snapshot_id: uuid.UUID | None
    tier: str | None
    provenance: tuple[ProvenanceView, ...]
    event_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class CrossApplicantSignal:
    """A counterparty/device fingerprint seen across multiple applications."""

    fingerprint_hash: str
    kind: str  # COUNTERPARTY | DEVICE
    application_count: int
    window_days: int
    event_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class ManipulationContext:
    as_of: datetime
    events: tuple[LedgerEventView, ...]
    declared: DeclaredApplication
    sources: tuple[SourceMetadataView, ...]
    cross_applicant: tuple[CrossApplicantSignal, ...]
    # Ledger event ids the deterministic classifier tagged as income (SALARY / GIG /
    # BUSINESS). Derived by the classifier, which reads no risk score.
    income_event_ids: frozenset[uuid.UUID]
    config_version: str
