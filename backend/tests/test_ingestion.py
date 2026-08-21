"""Consent, source-adapter and ingestion tests."""

import asyncio
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.context import RequestContext
from app.models.applicant import Applicant
from app.models.audit import LedgerEntry
from app.models.consent import Consent
from app.models.enums import SourceConnectionStatus, SourceTier, SourceType, UserRole
from app.models.ledger import LedgerEvent
from app.models.source import SourceConnection, SourceSnapshot
from app.services.consent.service import create_consent, revoke_consent
from app.services.ingestion.normalizer import persist_events
from app.services.ingestion.service import (
    ConsentError,
    assert_active_consent,
    ingest_document,
    ingest_source,
)
from app.services.sources.base import FetchPeriod
from app.services.sources.document import (
    DocumentAdapter,
    RowCapExceededError,
    SchemaError,
)
from app.services.sources.mock_aa import MockAccountAggregatorAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.factories import create_user

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "statements"

# Counterparty names the mock AA emits — none may appear in the ledger in plaintext.
_COUNTERPARTY_NAMES = {
    "URBAN RENTALS",
    "HDFC EMI",
    "BESCOM",
    "ACME PAYROLL",
    "CLIENT SETTLEMENT",
    "GIG PLATFORM",
    "Zomato",
    "Swiggy",
    "Amazon",
    "BigBasket",
    "Uber",
}


async def _setup(
    session: AsyncSession,
    *,
    scope: tuple[SourceType, ...] = (SourceType.BANK,),
    expires_at: datetime | None = None,
) -> tuple[RequestContext, Applicant, Consent, list[SourceConnection]]:
    user, tenant = await create_user(session, role=UserRole.CREDIT_ANALYST)
    context = RequestContext(
        user_id=user.id,
        tenant_id=tenant.id,
        role="CREDIT_ANALYST",
        email=user.email,
        session_id=uuid.uuid4(),
        approval_ceilings_paise={},
    )
    applicant = Applicant(tenant_id=tenant.id, external_ref=f"app-{uuid.uuid4().hex[:8]}")
    session.add(applicant)
    await session.commit()
    consent, connections = await create_consent(
        session,
        context,
        applicant_id=applicant.id,
        purpose="underwriting",
        scope=list(scope),
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=30),
    )
    return context, applicant, consent, connections


def _period() -> FetchPeriod:
    end = datetime(2026, 3, 31, tzinfo=UTC)
    return FetchPeriod(start=datetime(2026, 1, 1, tzinfo=UTC), end=end)


# --------------------------------------------------------------------------- #
# Consent
# --------------------------------------------------------------------------- #
async def test_consent_creation_registers_connections_and_audit(
    db_session: AsyncSession,
) -> None:
    context, _applicant, consent, connections = await _setup(
        db_session, scope=(SourceType.BANK, SourceType.UPI)
    )
    assert consent.version == 1
    assert consent.artefact_hash is not None
    assert {c.source_type for c in connections} == {SourceType.BANK, SourceType.UPI}

    entry = await db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.tenant_id == context.tenant_id,
            LedgerEntry.event_type == "CONSENT_GRANTED",
        )
    )
    assert entry is not None
    assert entry.subject_id == consent.id


async def test_revoked_consent_blocks_ingestion(db_session: AsyncSession) -> None:
    context, _applicant, consent, connections = await _setup(db_session)
    await revoke_consent(db_session, context, consent_id=consent.id)

    connection = connections[0]
    with pytest.raises(ConsentError) as excinfo:
        await assert_active_consent(db_session, connection)
    assert excinfo.value.code == "CONSENT_REVOKED"


async def test_expired_consent_blocks_ingestion(db_session: AsyncSession) -> None:
    _context, _applicant, _consent, connections = await _setup(
        db_session, expires_at=datetime.now(UTC) - timedelta(days=1)
    )
    with pytest.raises(ConsentError) as excinfo:
        await assert_active_consent(db_session, connections[0])
    assert excinfo.value.code == "CONSENT_EXPIRED"


# --------------------------------------------------------------------------- #
# Mock AA adapter
# --------------------------------------------------------------------------- #
async def test_mock_aa_is_deterministic(db_session: AsyncSession) -> None:
    _context, _applicant, _consent, connections = await _setup(db_session)
    connection = connections[0]
    period = _period()

    first = MockAccountAggregatorAdapter()
    second = MockAccountAggregatorAdapter()
    payload_a = await first.fetch(connection, period)
    payload_b = await second.fetch(connection, period)

    assert payload_a.raw == payload_b.raw  # byte-identical provider payload
    assert first.normalize(payload_a) == second.normalize(payload_b)
    assert len(payload_a.raw["transactions"]) > 0


async def test_mock_aa_ingests_and_is_idempotent(db_session: AsyncSession) -> None:
    _context, applicant, _consent, connections = await _setup(db_session)
    connection = connections[0]
    period = _period()

    result = await ingest_source(db_session, connection, MockAccountAggregatorAdapter(), period)
    assert result.status == "OK"
    assert result.ingested > 0

    count_first = await db_session.scalar(
        select(func.count())
        .select_from(LedgerEvent)
        .where(LedgerEvent.applicant_id == applicant.id)
    )
    assert count_first == result.ingested

    # Re-ingesting the identical source is an explicit no-op with zero new rows.
    again = await ingest_source(db_session, connection, MockAccountAggregatorAdapter(), period)
    assert again.already_ingested is True
    assert again.status == "ALREADY_INGESTED"

    count_second = await db_session.scalar(
        select(func.count())
        .select_from(LedgerEvent)
        .where(LedgerEvent.applicant_id == applicant.id)
    )
    assert count_second == count_first


async def test_reingestion_reports_deduplicated_count(db_session: AsyncSession) -> None:
    _context, applicant, _consent, connections = await _setup(db_session)
    connection = connections[0]
    adapter = MockAccountAggregatorAdapter()
    payload = await adapter.fetch(connection, _period())
    events = adapter.normalize(payload)

    snapshot = SourceSnapshot(
        tenant_id=connection.tenant_id,
        source_connection_id=connection.id,
        applicant_id=applicant.id,
        tier=SourceTier.AA_VERIFIED,
        fetched_at=datetime.now(UTC),
        content_hash=f"hash-{uuid.uuid4().hex}",
        record_count=len(events),
    )
    db_session.add(snapshot)
    await db_session.flush()

    first = await persist_events(
        db_session,
        tenant_id=connection.tenant_id,
        applicant_id=applicant.id,
        connection_id=connection.id,
        snapshot_id=snapshot.id,
        source_type=SourceType.BANK,
        salt="fixed-salt",
        events=events,
    )
    assert first.ingested == len(events)
    assert first.deduplicated == 0

    # AA events key off external_id, so a second insert deduplicates every event.
    second = await persist_events(
        db_session,
        tenant_id=connection.tenant_id,
        applicant_id=applicant.id,
        connection_id=connection.id,
        snapshot_id=snapshot.id,
        source_type=SourceType.BANK,
        salt="fixed-salt",
        events=events,
    )
    assert second.ingested == 0
    assert second.deduplicated == len(events)


async def test_provider_timeout_marks_unavailable_without_failing(
    db_session: AsyncSession,
) -> None:
    _context, _applicant, _consent, connections = await _setup(db_session)
    connection = connections[0]
    result = await ingest_source(
        db_session,
        connection,
        MockAccountAggregatorAdapter(failure_mode="timeout"),
        _period(),
    )
    assert result.status == "UNAVAILABLE"
    await db_session.refresh(connection)
    assert connection.status == SourceConnectionStatus.UNAVAILABLE


async def test_counterparty_is_stored_hashed(db_session: AsyncSession) -> None:
    _context, applicant, _consent, connections = await _setup(db_session)
    await ingest_source(db_session, connections[0], MockAccountAggregatorAdapter(), _period())
    rows = (
        await db_session.execute(
            select(LedgerEvent.description, LedgerEvent.counterparty_hash).where(
                LedgerEvent.applicant_id == applicant.id
            )
        )
    ).all()
    assert rows
    for description, counterparty_hash in rows:
        assert description not in _COUNTERPARTY_NAMES
        if counterparty_hash is not None:
            assert len(counterparty_hash) == 64  # sha256 hex, not a plaintext name
            assert counterparty_hash not in _COUNTERPARTY_NAMES


# --------------------------------------------------------------------------- #
# Document adapter: rejection matrix + provenance
# --------------------------------------------------------------------------- #
def test_malformed_columns_names_expected_columns() -> None:
    data = (FIXTURES / "malformed_columns.csv").read_bytes()
    with pytest.raises(SchemaError) as excinfo:
        DocumentAdapter().parse(data, "malformed_columns.csv")
    message = str(excinfo.value)
    assert "Date" in message and "Description" in message and "Amount" in message


async def test_malformed_columns_creates_no_rows(db_session: AsyncSession) -> None:
    _context, _applicant, _consent, connections = await _setup(
        db_session, scope=(SourceType.UTILITY,)
    )
    data = (FIXTURES / "malformed_columns.csv").read_bytes()
    with pytest.raises(SchemaError):
        await ingest_document(db_session, connections[0], data, "malformed_columns.csv")
    snapshots = await db_session.scalar(
        select(func.count())
        .select_from(SourceSnapshot)
        .where(SourceSnapshot.source_connection_id == connections[0].id)
    )
    assert snapshots == 0


def test_huge_file_rejected_at_row_cap() -> None:
    data = (FIXTURES / "huge_50k_rows.csv").read_bytes()
    with pytest.raises(RowCapExceededError) as excinfo:
        DocumentAdapter().parse(data, "huge_50k_rows.csv")
    assert "20,000" in str(excinfo.value)


def test_password_protected_pdf_is_a_clean_schema_error() -> None:
    """A user-password-encrypted statement (banks do this) must be a 4xx with an
    actionable message — never an unhandled 500 from pypdf."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")  # a user password we cannot guess
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(SchemaError) as excinfo:
        DocumentAdapter().parse(buffer.getvalue(), "bank statement.pdf")
    assert "password-protected" in str(excinfo.value)


def test_owner_only_encrypted_pdf_unlocks_with_empty_password() -> None:
    """A PDF carrying only an owner password unlocks with an empty user password."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="", owner_password="owner")
    buffer = io.BytesIO()
    writer.write(buffer)

    result = DocumentAdapter().parse(buffer.getvalue(), "statement.pdf")
    assert result.events == []  # blank page → no transactions, but no crash


async def test_tampered_pdf_ingests_with_provenance_and_capped_tier(
    db_session: AsyncSession,
) -> None:
    _context, _applicant, _consent, connections = await _setup(
        db_session, scope=(SourceType.UTILITY,)
    )
    data = (FIXTURES / "tampered.pdf").read_bytes()
    result = await ingest_document(db_session, connections[0], data, "tampered.pdf")
    assert result.status == "OK"
    assert result.tier == SourceTier.DECLARED_DOCUMENT
    codes = {finding["code"] for finding in result.provenance}
    assert "EDITOR_PRODUCED" in codes
    assert result.ingested >= 1


async def test_partial_valid_rows_ingested_and_rejections_reported(
    db_session: AsyncSession,
) -> None:
    _context, _applicant, _consent, connections = await _setup(
        db_session, scope=(SourceType.UTILITY,)
    )
    rows = ["Date,Description,Amount,Balance"]
    balance = 100000.0
    for i in range(100):
        balance -= 1
        rows.append(f"2026-01-01,Row {i},-1.00,{balance:.2f}")
    rows += [
        "not-a-date,Bad date,-1.00,10.00",
        "2026-01-01,Bad amount,notanumber,10.00",
        "2026-01-01,Missing amount",
        ",Missing date,-1.00,10.00",
        "2026-13-45,Impossible date,-1.00,10.00",
    ]
    data = ("\n".join(rows) + "\n").encode("utf-8")

    result = await ingest_document(db_session, connections[0], data, "mixed.csv")
    assert result.ingested == 100
    assert result.rejected == 5
    assert len(result.rejected_reasons) == 5


async def test_same_file_twice_is_already_ingested(db_session: AsyncSession) -> None:
    _context, _applicant, _consent, connections = await _setup(
        db_session, scope=(SourceType.UTILITY,)
    )
    data = (FIXTURES / "clean_salaried.csv").read_bytes()
    first = await ingest_document(db_session, connections[0], data, "clean_salaried.csv")
    assert first.status == "OK" and first.ingested > 0
    second = await ingest_document(db_session, connections[0], data, "clean_salaried.csv")
    assert second.already_ingested is True


# --------------------------------------------------------------------------- #
# Concurrency: same file ingested twice at once → one copy of events
# --------------------------------------------------------------------------- #
async def test_concurrent_same_file_ingestion_is_idempotent(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    _context, applicant, _consent, connections = await _setup(
        db_session, scope=(SourceType.UTILITY,)
    )
    connection_id = connections[0].id
    tenant_id = connections[0].tenant_id
    data = (FIXTURES / "clean_gig.csv").read_bytes()
    url = db_engine.url.render_as_string(hide_password=False)

    def ingest_in_own_loop() -> str:
        # Each task runs in its own thread + event loop + engine, so two genuinely
        # concurrent transactions race on the unique constraint (no greenlet interleave).
        async def _run() -> str:
            engine = create_async_engine(url, poolclass=NullPool)
            try:
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    connection = await session.get(SourceConnection, connection_id)
                    assert connection is not None
                    result = await ingest_document(session, connection, data, "clean_gig.csv")
                    return result.status
            finally:
                await engine.dispose()

        return asyncio.run(_run())

    statuses = await asyncio.gather(
        asyncio.to_thread(ingest_in_own_loop),
        asyncio.to_thread(ingest_in_own_loop),
    )
    assert sorted(statuses) == ["ALREADY_INGESTED", "OK"]

    total = await db_session.scalar(
        select(func.count())
        .select_from(LedgerEvent)
        .where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.applicant_id == applicant.id,
        )
    )
    # clean_gig.csv has 7 valid rows; concurrent runs must not double-insert.
    snapshots = await db_session.scalar(
        select(func.count())
        .select_from(SourceSnapshot)
        .where(SourceSnapshot.source_connection_id == connection_id)
    )
    assert snapshots == 1
    assert total == 7
