"""Append-only, hash-chained audit ledger.

``append`` runs inside the *caller's* transaction (it flushes but never commits), so a
domain write and its audit entry commit atomically. ``seq`` is allocated per tenant
under a row lock, so concurrent appends cannot collide or reorder. ``verify_chain``
recomputes every hash to detect tampering.
"""

import hashlib
import uuid
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.db.repository import TenantScopedRepository
from app.models.audit import LedgerEntry
from app.models.tenant import Tenant
from app.services.audit.canonical import canonical_json

ZERO_HASH = "0" * 64


class ChainVerification(TypedDict):
    valid: bool
    broken_at_seq: int | None


class LedgerEntryRepository(TenantScopedRepository[LedgerEntry]):
    model = LedgerEntry


def compute_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


async def append(
    session: AsyncSession,
    context: RequestContext,
    event_type: str,
    subject_type: str | None,
    subject_id: uuid.UUID | None,
    payload: dict[str, Any],
) -> LedgerEntry:
    """Append one entry to the tenant's chain within the caller's transaction.

    Never opens or commits a transaction — the caller controls atomicity.
    """
    tenant_id = context.tenant_id
    # Serialise appends for this tenant by locking its tenant row; the lock is held
    # until the caller commits or rolls back.
    await session.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
    last = await session.scalar(
        select(LedgerEntry)
        .where(LedgerEntry.tenant_id == tenant_id)
        .order_by(LedgerEntry.seq.desc())
        .limit(1)
    )
    seq = 1 if last is None else last.seq + 1
    prev_hash = ZERO_HASH if last is None else last.payload_hash

    entry = LedgerEntry(
        tenant_id=tenant_id,
        seq=seq,
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        actor_id=context.user_id,
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        prev_hash=prev_hash,
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession, tenant_id: uuid.UUID) -> ChainVerification:
    """Walk the tenant's chain, recomputing hashes; report the first broken ``seq``."""
    entries = await session.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.tenant_id == tenant_id)
        .order_by(LedgerEntry.seq.asc())
    )
    prev_hash = ZERO_HASH
    expected_seq = 1
    for entry in entries:
        if entry.seq != expected_seq:
            return {"valid": False, "broken_at_seq": entry.seq}
        if entry.prev_hash != prev_hash:
            return {"valid": False, "broken_at_seq": entry.seq}
        if entry.payload_hash != compute_payload_hash(entry.payload):
            return {"valid": False, "broken_at_seq": entry.seq}
        prev_hash = entry.payload_hash
        expected_seq += 1
    return {"valid": True, "broken_at_seq": None}
