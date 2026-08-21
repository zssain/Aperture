"""Normalisation: NormalizedEvent → immutable ledger_event, idempotently.

The idempotency key derivation and the counterparty HMAC are FROZEN (later stages and
the real-time path depend on them). Counterparty names are never stored in the clear.
"""

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EventDirection, EvidenceEventType, SourceType
from app.models.ledger import LedgerEvent
from app.services.classification.service import TxnEvent
from app.services.classification.vector import classify_for_ingest, normalize_narration
from app.services.sources.base import NormalizedEvent


@dataclass(frozen=True)
class NormalizationResult:
    ingested: int
    deduplicated: int
    total: int


def idempotency_key(source_type: SourceType, event: NormalizedEvent, snapshot_id: uuid.UUID) -> str:
    """sha256(source_type|external_id) when the provider gives an id; otherwise
    sha256(snapshot_id|occurred_at|amount|description). FROZEN derivation."""
    if event.external_id:
        basis = f"{source_type.value}|{event.external_id}"
    else:
        basis = (
            f"{snapshot_id}|{event.occurred_at.isoformat()}|"
            f"{event.amount_paise}|{event.description}"
        )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def counterparty_hash(salt: str, counterparty: str | None) -> str | None:
    if not counterparty:
        return None
    return hmac.new(
        salt.encode("utf-8"),
        counterparty.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def persist_events(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    applicant_id: uuid.UUID,
    connection_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    source_type: SourceType,
    salt: str,
    events: list[NormalizedEvent],
) -> NormalizationResult:
    """Insert events with ON CONFLICT DO NOTHING; report how many were deduplicated."""
    total = len(events)
    if total == 0:
        return NormalizationResult(0, 0, 0)

    received_at = datetime.now(UTC)
    rows: list[dict[str, object]] = []
    txns: list[TxnEvent] = []
    seen: set[str] = set()
    for event in events:
        # Point-in-time correctness requires an event time; refuse otherwise.
        if event.occurred_at is None:
            raise ValueError("event is missing occurred_at; source rejected")
        key = idempotency_key(source_type, event, snapshot_id)
        if key in seen:
            continue  # duplicate within the same batch → deduplicated
        seen.add(key)
        event_id = uuid.uuid4()
        row: dict[str, object] = {
            "id": event_id,
            "tenant_id": tenant_id,
            "applicant_id": applicant_id,
            "source_connection_id": connection_id,
            "source_snapshot_id": snapshot_id,
            "event_type": EvidenceEventType.TRANSACTION,
            "direction": event.direction,
            "amount_paise": event.amount_paise,
            "balance_paise": event.balance_paise,
            "currency": "INR",
            "description": event.description,
            "counterparty_hash": counterparty_hash(salt, event.counterparty),
            "external_id": event.external_id,
            "occurred_at": event.occurred_at,
            "received_at": received_at,
            "idempotency_key": key,
            "payload": {},
        }
        rows.append(row)
        txns.append(
            TxnEvent(
                event_id=event_id,
                occurred_at=event.occurred_at,
                direction=event.direction or EventDirection.DEBIT,
                amount_paise=event.amount_paise,
                balance_paise=event.balance_paise,
                description=event.description,
                counterparty_hash=str(row["counterparty_hash"])
                if row["counterparty_hash"]
                else None,
                source_connection_id=connection_id,
            )
        )

    classified = await classify_for_ingest(session, txns)
    trace = {item.event.event_id: item for item in classified.events}
    for row in rows:
        row_id = row["id"]
        assert isinstance(row_id, uuid.UUID)
        item = trace[row_id]
        row.update(
            {
                "normalized_narration": item.normalized_narration
                or (
                    normalize_narration(str(row["description"]))
                    if item.classification_method.value == "UNCLASSIFIED" and row["description"]
                    else None
                ),
                "classification_method": item.classification_method,
                "category": item.category.value,
                "classifier_version": classified.classifier_version,
                "catalog_version_id": item.catalog_version_id,
                "match_similarity": item.match_similarity,
                "matched_entry_id": item.matched_entry_id,
                "payload": {},
            }
        )

    stmt = (
        insert(LedgerEvent)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["tenant_id", "idempotency_key"])
        .returning(LedgerEvent.id)
    )
    result = await session.execute(stmt)
    inserted = len(result.scalars().all())
    return NormalizationResult(ingested=inserted, deduplicated=total - inserted, total=total)
