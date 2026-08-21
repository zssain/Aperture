"""Audit-ledger tests: chain construction, tamper detection, concurrency, canonical
stability across processes, and transaction participation."""

import asyncio
import pathlib
import subprocess
import sys
import uuid
from datetime import UTC, datetime

from app.core.context import RequestContext
from app.models.audit import LedgerEntry
from app.models.enums import UserRole
from app.models.ledger import LedgerEvent  # noqa: F401  (ensure model graph imports)
from app.services.audit.canonical import canonical_json
from app.services.audit.ledger import ZERO_HASH, append, compute_payload_hash, verify_chain
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.factories import create_user

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]


async def _context(
    session: AsyncSession, role: UserRole = UserRole.CREDIT_ANALYST
) -> RequestContext:
    user, tenant = await create_user(session, role=role)
    return RequestContext(
        user_id=user.id,
        tenant_id=tenant.id,
        role=role.value,
        email=user.email,
        session_id=uuid.uuid4(),
        approval_ceilings_paise={},
    )


# --------------------------------------------------------------------------- #
# Chain construction
# --------------------------------------------------------------------------- #
async def test_chain_construction_links_hashes(db_session: AsyncSession) -> None:
    ctx = await _context(db_session)
    for i in range(3):
        await append(db_session, ctx, "EVENT", "thing", None, {"i": i})
    await db_session.commit()

    entries = list(
        await db_session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.tenant_id == ctx.tenant_id)
            .order_by(LedgerEntry.seq.asc())
        )
    )
    assert [e.seq for e in entries] == [1, 2, 3]
    assert entries[0].prev_hash == ZERO_HASH
    assert entries[1].prev_hash == entries[0].payload_hash
    assert entries[2].prev_hash == entries[1].payload_hash

    result = await verify_chain(db_session, ctx.tenant_id)
    assert result == {"valid": True, "broken_at_seq": None}


# --------------------------------------------------------------------------- #
# Tamper detection (bypass the immutability trigger via replication role)
# --------------------------------------------------------------------------- #
async def test_tamper_detected_at_exact_seq(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    ctx = await _context(db_session)
    for i in range(3):
        await append(db_session, ctx, "EVENT", "thing", None, {"i": i})
    await db_session.commit()

    # Tamper seq 2's payload directly, bypassing the BEFORE UPDATE trigger.
    async with db_engine.begin() as conn:
        await conn.execute(text("SET session_replication_role = replica"))
        await conn.execute(
            text(
                "UPDATE ledger_entries SET payload = '{\"i\": 999}'::jsonb "
                "WHERE tenant_id = :tid AND seq = 2"
            ),
            {"tid": ctx.tenant_id},
        )
        await conn.execute(text("SET session_replication_role = DEFAULT"))

    async with AsyncSession(db_engine, expire_on_commit=False) as fresh:
        result = await verify_chain(fresh, ctx.tenant_id)
    assert result == {"valid": False, "broken_at_seq": 2}


# --------------------------------------------------------------------------- #
# Concurrency: 50 concurrent appends → 50 sequential seq, no gaps or duplicates
# --------------------------------------------------------------------------- #
async def test_fifty_concurrent_appends_are_sequential(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    ctx = await _context(db_session)

    async def one(i: int) -> None:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await append(session, ctx, "CONCURRENT", "thing", None, {"i": i})
            await session.commit()

    await asyncio.gather(*(one(i) for i in range(50)))

    seqs = list(
        await db_session.scalars(
            select(LedgerEntry.seq)
            .where(LedgerEntry.tenant_id == ctx.tenant_id)
            .order_by(LedgerEntry.seq.asc())
        )
    )
    assert seqs == list(range(1, 51))
    assert len(set(seqs)) == 50


# --------------------------------------------------------------------------- #
# Transaction participation: a rolled-back caller leaves no ledger row
# --------------------------------------------------------------------------- #
async def test_append_participates_in_caller_transaction(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    ctx = await _context(db_session)

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        await append(session, ctx, "ROLLED_BACK", "thing", None, {"i": 1})
        await session.rollback()

    async with AsyncSession(db_engine, expire_on_commit=False) as fresh:
        count = await fresh.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.tenant_id == ctx.tenant_id)
        )
    assert count == 0


# --------------------------------------------------------------------------- #
# Canonical serialisation: unit behaviour + cross-process stability
# --------------------------------------------------------------------------- #
def test_canonical_sorts_keys_and_omits_none() -> None:
    assert canonical_json({"b": 1, "a": 2, "c": None}) == '{"a":2,"b":1}'


def test_canonical_bool_before_int_and_float_fixed() -> None:
    assert canonical_json({"a": True, "b": 1, "r": 1.5}) == '{"a":true,"b":1,"r":1.5000000000}'


def test_canonical_datetime_is_utc_z() -> None:
    ts = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert canonical_json({"ts": ts}) == '{"ts":"2026-01-02T03:04:05.000000Z"}'


def test_canonical_stable_across_processes() -> None:
    payload = {
        "amount_paise": 123456,
        "ratio": 0.3333333333,
        "flag": True,
        "missing": None,
        "ts": datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC),
        "items": [3, 1, 2],
        "nested": {"z": 1, "a": 2},
    }
    in_process = canonical_json(payload)

    code = (
        "from datetime import datetime, UTC\n"
        "from app.services.audit.canonical import canonical_json\n"
        "p = {"
        "'amount_paise': 123456, 'ratio': 0.3333333333, 'flag': True, "
        "'missing': None, 'ts': datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC), "
        "'items': [3, 1, 2], 'nested': {'z': 1, 'a': 2}}\n"
        "print(canonical_json(p), end='')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout == in_process
    assert compute_payload_hash(payload) == compute_payload_hash(payload)  # deterministic
