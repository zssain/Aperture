"""Schema-level tests: migration round-trip, immutability triggers, the live-policy
partial index, idempotency uniqueness, and a no-floating-point-money assertion.

These require a real PostgreSQL database (native enums, jsonb, triggers, partial
indexes). Set ``TEST_DATABASE_URL`` to a *throwaway* database — the migration is run
forward and backward against it. Tests are skipped (not failed) when it is unset.
"""

import argparse
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.db.repository import TenantScopedRepository
from app.models import (
    Applicant,
    Application,
    Decision,
    FeatureSnapshot,
    LedgerEntry,
    LedgerEvent,
    PolicyVersion,
    Tenant,
)
from app.models.enums import (
    DecisionAction,
    EvidenceEventType,
    PolicyStatus,
)
from sqlalchemy.engine import Inspector
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


class _ApplicantRepository(TenantScopedRepository[Applicant]):
    model = Applicant


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL not set — schema tests need a throwaway PostgreSQL",
)

EXPECTED_TABLES = {
    "tenants",
    "users",
    "applicants",
    "applications",
    "consents",
    "source_connections",
    "source_snapshots",
    "ledger_events",
    "feature_snapshots",
    "assessments",
    "manipulation_findings",
    "policy_versions",
    "decisions",
    "decision_reasons",
    "recourse_options",
    "human_reviews",
    "ledger_entries",
    "model_versions",
    "outcomes",
    "notices",
    "jobs",
}


def _alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.cmd_opts = argparse.Namespace(x=[f"db_url={url}"])
    return cfg


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(scope="module")
def migrated_url() -> Iterator[str]:
    """Run the migration forward against the throwaway DB; reverse it on teardown."""
    assert TEST_DATABASE_URL is not None
    cfg = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(cfg, "base")  # ensure a clean starting point
    command.upgrade(cfg, "head")
    yield TEST_DATABASE_URL
    command.downgrade(cfg, "base")


@pytest_asyncio.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_url, poolclass=sa.pool.NullPool)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        yield sess


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}")
    session.add(tenant)
    await session.commit()
    return tenant


# --------------------------------------------------------------------------- #
# Migration round-trip
# --------------------------------------------------------------------------- #
async def test_migration_creates_every_table(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: set(sa.inspect(sync_conn).get_table_names()))
    assert names >= EXPECTED_TABLES


# --------------------------------------------------------------------------- #
# Immutability triggers
# --------------------------------------------------------------------------- #
async def test_update_on_ledger_entries_raises(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    entry = LedgerEntry(
        tenant_id=tenant.id,
        seq=1,
        event_type="DECISION_WRITTEN",
        payload={"k": "v"},
        payload_hash="hash-1",
        prev_hash="GENESIS",
    )
    session.add(entry)
    await session.commit()

    entry.payload_hash = "tampered"
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_delete_on_decisions_raises(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    applicant = Applicant(tenant_id=tenant.id, external_ref="ext-1")
    session.add(applicant)
    await session.flush()

    application = Application(tenant_id=tenant.id, applicant_id=applicant.id)
    snapshot = FeatureSnapshot(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        as_of=_now(),
        schema_version="v1",
        values={},
        null_map={},
        input_hash="ihash",
    )
    policy = PolicyVersion(tenant_id=tenant.id, version=1, status=PolicyStatus.LIVE)
    session.add_all([application, snapshot, policy])
    await session.flush()

    decision = Decision(
        tenant_id=tenant.id,
        application_id=application.id,
        applicant_id=applicant.id,
        feature_snapshot_id=snapshot.id,
        policy_version_id=policy.id,
        action=DecisionAction.DECLINE,
        terms={},
        fired_rules=[],
    )
    session.add(decision)
    await session.commit()

    await session.delete(decision)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


# --------------------------------------------------------------------------- #
# Partial unique index: at most one LIVE policy per tenant
# --------------------------------------------------------------------------- #
async def test_two_live_policies_cannot_coexist(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    session.add(PolicyVersion(tenant_id=tenant.id, version=1, status=PolicyStatus.LIVE))
    await session.commit()

    session.add(PolicyVersion(tenant_id=tenant.id, version=2, status=PolicyStatus.LIVE))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_two_draft_policies_are_allowed(session: AsyncSession) -> None:
    """The partial index only constrains LIVE rows — drafts may coexist."""
    tenant = await _make_tenant(session)
    session.add_all(
        [
            PolicyVersion(tenant_id=tenant.id, version=1, status=PolicyStatus.DRAFT),
            PolicyVersion(tenant_id=tenant.id, version=2, status=PolicyStatus.DRAFT),
        ]
    )
    await session.commit()  # must not raise


# --------------------------------------------------------------------------- #
# Idempotency uniqueness on ledger_events
# --------------------------------------------------------------------------- #
async def test_duplicate_idempotency_key_raises(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    applicant = Applicant(tenant_id=tenant.id, external_ref="ext-idem")
    session.add(applicant)
    await session.flush()

    def _event() -> LedgerEvent:
        return LedgerEvent(
            tenant_id=tenant.id,
            applicant_id=applicant.id,
            event_type=EvidenceEventType.TRANSACTION,
            occurred_at=_now(),
            received_at=_now(),
            idempotency_key="dup-key",
            payload={},
        )

    session.add(_event())
    await session.commit()

    session.add(_event())
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


# --------------------------------------------------------------------------- #
# No floating-point money anywhere
# --------------------------------------------------------------------------- #
async def test_no_floating_point_money_columns(engine: AsyncEngine) -> None:
    def _collect(sync_conn: sa.Connection) -> tuple[list[str], list[str]]:
        inspector: Inspector = sa.inspect(sync_conn)
        float_cols: list[str] = []
        bad_paise: list[str] = []
        for table in inspector.get_table_names():
            for column in inspector.get_columns(table):
                col_type = column["type"]
                qualified = f"{table}.{column['name']}"
                if isinstance(col_type, sa.Float | sa.Numeric):
                    float_cols.append(qualified)
                if column["name"].endswith("_paise") and not isinstance(col_type, sa.BigInteger):
                    bad_paise.append(qualified)
        return float_cols, bad_paise

    async with engine.connect() as conn:
        float_cols, bad_paise = await conn.run_sync(_collect)

        assert float_cols == ["ledger_events.match_similarity"], (
            f"unexpected floating-point columns found: {float_cols}"
        )
    assert bad_paise == [], f"*_paise columns that are not BigInteger: {bad_paise}"


# --------------------------------------------------------------------------- #
# TenantScopedRepository: structural tenant isolation
# --------------------------------------------------------------------------- #
async def test_repository_scopes_reads_to_its_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session)
    tenant_b = await _make_tenant(session)
    applicant_a = Applicant(tenant_id=tenant_a.id, external_ref="A")
    applicant_b = Applicant(tenant_id=tenant_b.id, external_ref="B")
    session.add_all([applicant_a, applicant_b])
    await session.commit()

    repo_a = _ApplicantRepository(session, tenant_a.id)

    assert (await repo_a.get(applicant_a.id)) is not None
    # A cross-tenant row is invisible through the scoped repository.
    assert (await repo_a.get(applicant_b.id)) is None
    listed = await repo_a.list()
    assert listed and all(item.tenant_id == tenant_a.id for item in listed)


async def test_repository_stamps_tenant_on_write(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = _ApplicantRepository(session, tenant.id)
    # Note: no tenant_id passed — the repository stamps it structurally.
    applicant = repo.add(Applicant(external_ref="stamped"))
    await session.commit()
    assert applicant.tenant_id == tenant.id


def test_repository_exposes_no_unscoped_query_builder() -> None:
    """The only query builder (``_scoped_select``) is private; nothing public
    hands out an unscoped query."""
    public_members = [name for name in dir(_ApplicantRepository) if not name.startswith("_")]
    assert {"get", "list", "add", "model", "tenant_id"} <= set(public_members)
    assert not any("select" in name.lower() for name in public_members)
