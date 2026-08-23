"""Point-in-time feature service.

``compute_snapshot`` loads ONLY events with ``occurred_at <= as_of`` (the single most
important rule in the system), classifies them, computes the registry's features,
validates against the schema, and freezes an immutable :class:`FeatureSnapshot` with
values, null_map, lineage and a reproducible ``input_hash``.

The SAME code path is used for training and serving — there is no separate path.
"""

import hashlib
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import EventDirection, EvidenceEventType
from app.models.feature import FeatureSnapshot
from app.models.ledger import LedgerEvent
from app.services.audit.canonical import canonical_json
from app.services.classification.rules import TxnCategory
from app.services.classification.service import (
    ClassifiedEvent,
    TxnEvent,
    classify,
)
from app.services.features.registry import REGISTRY, BureauRecord, FeatureContext
from app.services.features.schema import SCHEMA_VERSION, validate


class ApplicationNotFoundError(Exception):
    pass


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _latest_bureau_record(events: list[LedgerEvent]) -> BureauRecord | None:
    """The most recent BUREAU_RECORD event's payload, as a BureauRecord (or None).
    Point-in-time: ``events`` are already filtered to occurred_at <= as_of."""
    bureau_events = [e for e in events if e.event_type == EvidenceEventType.BUREAU_RECORD]
    if not bureau_events:
        return None
    latest = max(bureau_events, key=lambda e: (e.occurred_at, str(e.id)))
    payload = latest.payload or {}
    return BureauRecord(
        event_id=str(latest.id),
        score=_coerce_int(payload.get("bureau_score")),
        active_loans=_coerce_int(payload.get("bureau_active_loans")),
        delinquencies_12m=_coerce_int(payload.get("bureau_delinquencies_12m")),
    )


def compute_input_hash(
    event_ids: list[str],
    as_of: datetime,
    schema_version: str,
    catalog_version_id: str | None = None,
    classifier_version: str | None = None,
) -> str:
    """Reproducible fingerprint over the contributing event ids + as_of + schema."""
    payload = {
        "event_ids": sorted(event_ids),
        "as_of": as_of,
        "schema_version": schema_version,
        "catalog_version_id": catalog_version_id,
        "classifier_version": classifier_version,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _to_txn(event: LedgerEvent) -> TxnEvent:
    raw_category = event.category
    try:
        stored_category = TxnCategory(str(raw_category)) if raw_category else None
    except ValueError:
        stored_category = None
    return TxnEvent(
        event_id=event.id,
        occurred_at=event.occurred_at,
        direction=event.direction or EventDirection.DEBIT,
        amount_paise=event.amount_paise or 0,
        balance_paise=event.balance_paise,
        description=event.description,
        counterparty_hash=event.counterparty_hash,
        source_connection_id=event.source_connection_id,
        stored_category=stored_category,
        stored_method=event.classification_method,
        stored_classifier_version=event.classifier_version,
        stored_normalized_narration=event.normalized_narration,
        stored_catalog_version_id=event.catalog_version_id,
        stored_matched_entry_id=event.matched_entry_id,
        stored_match_similarity=event.match_similarity,
    )


def compute_feature_values(
    as_of: datetime,
    classified: tuple[ClassifiedEvent, ...],
    bureau: BureauRecord | None = None,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Compute (values, null_map, lineage) and validate. Pure — no DB, no imputation."""
    ctx = FeatureContext(as_of=as_of, events=list(classified), bureau=bureau)
    values: dict[str, Any] = {}
    null_map: dict[str, str] = {}
    lineage: dict[str, Any] = {}
    for spec in REGISTRY:
        result = spec.compute(ctx)
        if result.value is None:
            null_map[spec.key] = result.null_reason or "unspecified"
        else:
            values[spec.key] = result.value
        lineage[spec.key] = {"events": result.lineage, "clamped": result.clamped}
    validate(values, null_map)
    return values, null_map, lineage


async def _load_events(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    applicant_id: uuid.UUID,
    as_of: datetime,
) -> list[LedgerEvent]:
    # THE point-in-time filter. Never load without `occurred_at <= as_of`.
    stmt = (
        select(LedgerEvent)
        .where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.applicant_id == applicant_id,
            LedgerEvent.occurred_at <= as_of,
        )
        .order_by(LedgerEvent.occurred_at.asc(), LedgerEvent.id.asc())
    )
    return list(await session.scalars(stmt))


async def compute_snapshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    application_id: uuid.UUID,
    as_of: datetime,
    schema_version: str = SCHEMA_VERSION,
) -> FeatureSnapshot:
    application = await session.get(Application, application_id)
    if application is None or application.tenant_id != tenant_id:
        raise ApplicationNotFoundError("application not found")
    applicant_id = application.applicant_id

    events = await _load_events(session, tenant_id, applicant_id, as_of)
    # Only transactions feed cash-flow classification; a bureau record is not a
    # transaction and must not become a ₹0 ghost event in the cash-flow features.
    txn_events = [e for e in events if e.event_type == EvidenceEventType.TRANSACTION]
    classification = classify([_to_txn(event) for event in txn_events])
    values, null_map, lineage = compute_feature_values(
        as_of, classification.events, bureau=_latest_bureau_record(events)
    )

    contributing = [str(event.id) for event in events]
    catalog_ids = sorted(
        {
            str(item.catalog_version_id)
            for item in classification.events
            if item.catalog_version_id is not None
        }
    )
    catalog_version = catalog_ids[0] if len(catalog_ids) == 1 else None
    input_hash = compute_input_hash(
        contributing,
        as_of,
        schema_version,
        catalog_version,
        classification.classifier_version,
    )

    snapshot = FeatureSnapshot(
        tenant_id=tenant_id,
        applicant_id=applicant_id,
        application_id=application_id,
        as_of=as_of,
        schema_version=schema_version,
        values=values,
        null_map=null_map,
        lineage=lineage,
        classifier_version=classification.classifier_version,
        catalog_version_id=uuid.UUID(catalog_version) if catalog_version else None,
        input_hash=input_hash,
    )
    session.add(snapshot)
    await session.commit()
    return snapshot
