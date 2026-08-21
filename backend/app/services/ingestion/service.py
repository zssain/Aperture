"""Ingestion service: consent gate → adapter → snapshot → idempotent normalisation.

A parse failure never creates an application or a partial snapshot. A provider timeout
marks the connection UNAVAILABLE and returns a result (it does not abort a multi-source
run). Re-ingesting an identical source is an explicit ``ALREADY_INGESTED`` no-op — even
under a concurrency race, thanks to the snapshot uniqueness constraint (inserted with
ON CONFLICT DO NOTHING so no exception is raised mid-transaction).
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import Consent
from app.models.enums import (
    ConsentStatus,
    SourceConnectionStatus,
    SourceTier,
)
from app.models.source import SourceConnection, SourceSnapshot
from app.models.tenant import Tenant
from app.services.audit.canonical import canonical_json
from app.services.ingestion.normalizer import persist_events
from app.services.sources.base import (
    FetchPeriod,
    ProviderError,
    ProviderTimeoutError,
    SourceAdapter,
)
from app.services.sources.document import ParsedDocument

_SNAPSHOT_CONFLICT = ["tenant_id", "source_connection_id", "content_hash"]


class ConsentError(Exception):
    """Ingestion attempted outside an active, unexpired, in-scope consent."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class IngestionResult:
    status: str  # OK | ALREADY_INGESTED | UNAVAILABLE | FAILED
    snapshot_id: uuid.UUID | None = None
    tier: SourceTier | None = None
    already_ingested: bool = False
    ingested: int = 0
    deduplicated: int = 0
    rejected: int = 0
    rejected_reasons: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)


async def assert_active_consent(
    session: AsyncSession, connection: SourceConnection, *, now: datetime | None = None
) -> Consent:
    """Raise :class:`ConsentError` unless an active, unexpired, in-scope consent exists."""
    if connection.status == SourceConnectionStatus.REVOKED:
        raise ConsentError("CONSENT_REVOKED", "The source connection has been revoked.")
    if connection.consent_id is None:
        raise ConsentError("CONSENT_NOT_FOUND", "No consent is linked to this source.")

    consent = await session.get(Consent, connection.consent_id)
    if consent is None or consent.tenant_id != connection.tenant_id:
        raise ConsentError("CONSENT_NOT_FOUND", "No consent is linked to this source.")
    if consent.status == ConsentStatus.REVOKED or consent.revoked_at is not None:
        raise ConsentError("CONSENT_REVOKED", "Consent has been revoked.")
    if consent.status == ConsentStatus.EXPIRED:
        raise ConsentError("CONSENT_EXPIRED", "Consent has expired.")
    if consent.status != ConsentStatus.GRANTED:
        raise ConsentError("CONSENT_NOT_ACTIVE", "Consent is not active.")

    moment = now or datetime.now(UTC)
    if consent.expires_at is not None and consent.expires_at <= moment:
        raise ConsentError("CONSENT_EXPIRED", "Consent has expired.")

    scoped_sources = consent.scope.get("sources", [])
    if connection.source_type.value not in scoped_sources:
        raise ConsentError("OUT_OF_SCOPE", "This source type is outside the granted consent scope.")
    return consent


async def tenant_salt(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"tenant-salt:{tenant_id}")))
    )
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    await session.refresh(tenant)
    salt = tenant.config.get("counterparty_salt")
    if not isinstance(salt, str) or not salt:
        salt = secrets.token_hex(16)
        tenant.config = {**tenant.config, "counterparty_salt": salt}
        await session.flush()
    return salt


async def _existing_snapshot(
    session: AsyncSession, connection: SourceConnection, content_hash: str
) -> SourceSnapshot | None:
    result = await session.scalars(
        select(SourceSnapshot).where(
            SourceSnapshot.tenant_id == connection.tenant_id,
            SourceSnapshot.source_connection_id == connection.id,
            SourceSnapshot.content_hash == content_hash,
        )
    )
    return result.first()


async def _insert_snapshot(session: AsyncSession, values: dict[str, Any]) -> uuid.UUID | None:
    """Insert a snapshot; return its id, or None if an identical one already exists
    (ON CONFLICT DO NOTHING — the race is resolved without raising)."""
    stmt = (
        pg_insert(SourceSnapshot)
        .values(**values)
        .on_conflict_do_nothing(index_elements=_SNAPSHOT_CONFLICT)
        .returning(SourceSnapshot.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _already_ingested(
    session: AsyncSession, connection: SourceConnection, content_hash: str
) -> IngestionResult:
    await session.commit()
    existing = await _existing_snapshot(session, connection, content_hash)
    assert existing is not None
    return IngestionResult(
        status="ALREADY_INGESTED",
        snapshot_id=existing.id,
        tier=existing.tier,
        already_ingested=True,
    )


async def ingest_source(
    session: AsyncSession,
    connection: SourceConnection,
    adapter: SourceAdapter,
    period: FetchPeriod,
) -> IngestionResult:
    """Pull from a provider adapter (e.g. the mock AA) and normalise into the ledger."""
    await assert_active_consent(session, connection)

    try:
        payload = await adapter.fetch(connection, period)
    except ProviderTimeoutError:
        connection.status = SourceConnectionStatus.UNAVAILABLE
        await session.commit()
        return IngestionResult(status="UNAVAILABLE", tier=adapter.tier)
    except ProviderError:
        connection.status = SourceConnectionStatus.FAILED
        await session.commit()
        return IngestionResult(status="FAILED", tier=adapter.tier)

    content_hash = hashlib.sha256(canonical_json(payload.raw).encode("utf-8")).hexdigest()

    existing = await _existing_snapshot(session, connection, content_hash)
    if existing is not None:
        return IngestionResult(
            status="ALREADY_INGESTED",
            snapshot_id=existing.id,
            tier=existing.tier,
            already_ingested=True,
        )

    events = adapter.normalize(payload)
    salt = await tenant_salt(session, connection.tenant_id)
    now = datetime.now(UTC)

    snapshot_id = await _insert_snapshot(
        session,
        {
            "id": uuid.uuid4(),
            "tenant_id": connection.tenant_id,
            "source_connection_id": connection.id,
            "applicant_id": connection.applicant_id,
            "tier": adapter.tier,
            "fetched_at": now,
            "period_start": period.start,
            "period_end": period.end,
            "content_hash": content_hash,
            "record_count": len(events),
        },
    )
    if snapshot_id is None:
        return await _already_ingested(session, connection, content_hash)

    result = await persist_events(
        session,
        tenant_id=connection.tenant_id,
        applicant_id=connection.applicant_id,
        connection_id=connection.id,
        snapshot_id=snapshot_id,
        source_type=adapter.source_type,
        salt=salt,
        events=events,
    )
    await session.execute(
        update(SourceSnapshot)
        .where(SourceSnapshot.id == snapshot_id)
        .values(ingested_count=result.ingested, deduplicated_count=result.deduplicated)
    )
    connection.status = SourceConnectionStatus.CONNECTED
    connection.tier = adapter.tier
    await session.commit()

    return IngestionResult(
        status="OK",
        snapshot_id=snapshot_id,
        tier=adapter.tier,
        ingested=result.ingested,
        deduplicated=result.deduplicated,
    )


async def ingest_document(
    session: AsyncSession,
    connection: SourceConnection,
    file_bytes: bytes,
    filename: str,
) -> IngestionResult:
    """Parse and normalise an uploaded statement (CSV/PDF). Parse failures raise before
    any snapshot is created (the caller translates them to a 4xx)."""
    await assert_active_consent(session, connection)

    content_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = await _existing_snapshot(session, connection, content_hash)
    if existing is not None:
        return IngestionResult(
            status="ALREADY_INGESTED",
            snapshot_id=existing.id,
            tier=existing.tier,
            already_ingested=True,
        )

    from app.services.sources.upload_security import parse_document_securely, store_raw_upload

    parsed: ParsedDocument = parse_document_securely(file_bytes, filename)
    raw_ref = store_raw_upload(file_bytes)

    salt = await tenant_salt(session, connection.tenant_id)
    rejected_reasons = [{"row": r.row, "reason": r.reason} for r in parsed.rejected]

    snapshot_id = await _insert_snapshot(
        session,
        {
            "id": uuid.uuid4(),
            "tenant_id": connection.tenant_id,
            "source_connection_id": connection.id,
            "applicant_id": connection.applicant_id,
            "tier": SourceTier.DECLARED_DOCUMENT,
            "fetched_at": datetime.now(UTC),
            "content_hash": content_hash,
            "record_count": parsed.row_count,
            "rejected_count": len(parsed.rejected),
            "rejected_reasons": rejected_reasons,
            "provenance": parsed.provenance,
            "raw_ref": raw_ref,
        },
    )
    if snapshot_id is None:
        import os

        os.unlink(raw_ref)
        return await _already_ingested(session, connection, content_hash)

    from app.services.retention.policy import RETENTION_WINDOWS, RetentionClass
    from app.services.retention.purge import schedule_raw_purge

    await schedule_raw_purge(
        session,
        tenant_id=connection.tenant_id,
        applicant_id=connection.applicant_id,
        storage_path=raw_ref,
        subject_id=snapshot_id,
        expires_at=datetime.now(UTC) + RETENTION_WINDOWS[RetentionClass.RAW_EVIDENCE],
    )

    result = await persist_events(
        session,
        tenant_id=connection.tenant_id,
        applicant_id=connection.applicant_id,
        connection_id=connection.id,
        snapshot_id=snapshot_id,
        source_type=connection.source_type,
        salt=salt,
        events=parsed.events,
    )
    await session.execute(
        update(SourceSnapshot)
        .where(SourceSnapshot.id == snapshot_id)
        .values(ingested_count=result.ingested, deduplicated_count=result.deduplicated)
    )
    connection.status = SourceConnectionStatus.CONNECTED
    connection.tier = SourceTier.DECLARED_DOCUMENT
    await session.commit()

    return IngestionResult(
        status="OK",
        snapshot_id=snapshot_id,
        tier=SourceTier.DECLARED_DOCUMENT,
        ingested=result.ingested,
        deduplicated=result.deduplicated,
        rejected=len(parsed.rejected),
        rejected_reasons=rejected_reasons,
        provenance=parsed.provenance,
    )
