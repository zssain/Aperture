"""Job runner tests: claim under SKIP LOCKED, retry/backoff then dead-letter, graceful
release, crash reclaim, and two-workers-exactly-one-effect (handler idempotency).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from app.core.context import RequestContext
from app.jobs.handlers import HANDLERS, system_context
from app.jobs.runner import Handler, claim_job, enqueue, release_claimed, run_next
from app.models.decision import Decision
from app.models.enums import JobStatus, JobType, UserRole
from app.models.job import Job
from app.services.risk.registry import REGISTRY_PATH
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.decision_fixtures import AS_OF, build_decidable, publish_seed
from tests.factories import create_user


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _isolate_jobs(db_session: AsyncSession) -> AsyncIterator[None]:
    # The runner claims globally; the module-scoped DB shares rows across tests, so start each
    # test from an empty queue.
    await db_session.execute(delete(Job))
    await db_session.commit()
    yield


async def test_enqueue_and_run_verify_chain(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    job = await enqueue(
        db_session,
        tenant_id=tenant.id,
        handler="verify_chain",
        job_type=JobType.DECISION,
        payload={},
    )
    await db_session.commit()

    outcome = await run_next(
        _factory(db_engine), handlers=HANDLERS, worker_id="w1", context_factory=system_context
    )
    assert outcome.status == JobStatus.SUCCEEDED.value

    refreshed = await db_session.get(Job, job.id)
    assert refreshed is not None
    await db_session.refresh(refreshed)
    assert refreshed.result == {"valid": True, "broken_at_seq": None}


async def test_claim_skips_a_locked_row(db_engine: AsyncEngine) -> None:
    factory = _factory(db_engine)
    async with factory() as setup:
        _user, tenant = await create_user(setup, role=UserRole.CREDIT_ANALYST)
        await enqueue(
            setup,
            tenant_id=tenant.id,
            handler="verify_chain",
            job_type=JobType.DECISION,
            payload={},
        )
        await setup.commit()

    async with factory() as a, factory() as b:
        claimed_a = await claim_job(a, worker_id="a")  # locks the row, not yet committed
        claimed_b = await claim_job(b, worker_id="b")  # must skip the locked row
        assert claimed_a is not None
        assert claimed_b is None
        await a.rollback()


async def test_failed_handler_retries_then_dead_letters(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    t0 = datetime(2026, 8, 1, tzinfo=UTC)
    job = await enqueue(
        db_session,
        tenant_id=tenant.id,
        handler="boom",
        job_type=JobType.DECISION,
        payload={},
        max_attempts=2,
        run_after=t0,
    )
    await db_session.commit()

    async def _boom(_s: AsyncSession, _j: Job, _c: RequestContext) -> dict[str, Any]:
        raise RuntimeError("handler blew up")

    handlers: dict[str, Handler] = {"boom": _boom}
    factory = _factory(db_engine)

    first = await run_next(
        factory,
        handlers=handlers,
        worker_id="w1",
        context_factory=system_context,
        now=t0,
    )
    assert first.status == JobStatus.PENDING.value  # retried, not dead yet

    later = t0 + timedelta(hours=1)
    second = await run_next(
        factory,
        handlers=handlers,
        worker_id="w1",
        context_factory=system_context,
        now=later,
    )
    assert second.status == JobStatus.DEAD.value

    refreshed = await db_session.get(Job, job.id)
    assert refreshed is not None
    await db_session.refresh(refreshed)
    assert refreshed.status is JobStatus.DEAD
    assert refreshed.error is not None and "handler blew up" in refreshed.error


async def test_release_claimed_returns_job_to_pending(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    await enqueue(
        db_session,
        tenant_id=tenant.id,
        handler="verify_chain",
        job_type=JobType.DECISION,
        payload={},
    )
    await db_session.commit()

    factory = _factory(db_engine)
    async with factory() as s:
        claimed = await claim_job(s, worker_id="w1")
        assert claimed is not None
        await s.commit()

    released = await release_claimed(factory, worker_id="w1")
    assert released == 1

    async with factory() as s:
        pending = await s.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.tenant_id == tenant.id, Job.status == JobStatus.PENDING)
        )
        assert pending == 1


async def test_crashed_worker_job_is_reclaimed_after_lease(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    job = await enqueue(
        db_session,
        tenant_id=tenant.id,
        handler="verify_chain",
        job_type=JobType.DECISION,
        payload={},
    )
    # Simulate a crashed worker: RUNNING with a stale lease.
    job.status = JobStatus.RUNNING
    job.locked_by = "dead-worker"
    job.locked_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()

    factory = _factory(db_engine)
    async with factory() as s:
        reclaimed = await claim_job(s, worker_id="w2", lease_seconds=60.0)
        assert reclaimed is not None
        assert reclaimed.id == job.id
        await s.rollback()


@pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="risk artifacts not built")
async def test_two_workers_produce_exactly_one_effect(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    job = await enqueue(
        db_session,
        tenant_id=d.tenant_id,
        handler="decide",
        job_type=JobType.DECISION,
        payload={
            "application_id": str(d.application.id),
            "as_of": AS_OF.isoformat(),
            "idempotency_key": "job-decide",
            "user_id": str(d.user_id),
        },
    )
    await db_session.commit()

    factory = _factory(db_engine)
    first = await run_next(
        factory, handlers=HANDLERS, worker_id="w1", context_factory=system_context
    )
    second = await run_next(
        factory, handlers=HANDLERS, worker_id="w2", context_factory=system_context
    )
    assert first.status == JobStatus.SUCCEEDED.value
    assert second.ran is False  # nothing left to claim

    async def _count() -> int:
        async with factory() as s:
            return int(
                await s.scalar(
                    select(func.count())
                    .select_from(Decision)
                    .where(Decision.tenant_id == d.tenant_id)
                )
                or 0
            )

    assert await _count() == 1

    # Redelivery of the same job must not double the effect (handler idempotency).
    async with factory() as s:
        redelivered = await s.get(Job, job.id)
        assert redelivered is not None
        redelivered.status = JobStatus.PENDING
        redelivered.locked_by = None
        redelivered.locked_at = None
        await s.commit()

    third = await run_next(
        factory, handlers=HANDLERS, worker_id="w3", context_factory=system_context
    )
    assert third.status == JobStatus.SUCCEEDED.value
    assert await _count() == 1
