"""The job runner: a ``SELECT ... FOR UPDATE SKIP LOCKED`` claim loop.

At-least-once delivery: a claimed job runs to SUCCEEDED, or on failure retries with exponential
backoff up to ``max_attempts``, then dead-letters with the last error preserved. Handlers must be
idempotent (they are keyed by an idempotency key), so a redelivery after a worker crash produces
no double effect. A crashed worker's claim expires after a lease and another worker reclaims it.
On graceful shutdown the runner releases any job it still holds back to PENDING.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import RequestContext
from app.models.enums import JobStatus, JobType
from app.models.job import Job

# handler(session, job, context) -> result dict. Handlers own their own idempotency.
Handler = Callable[[AsyncSession, Job, RequestContext], Awaitable[dict[str, Any]]]

_LEASE_SECONDS = 60.0
_BASE_BACKOFF_SECONDS = 2.0
_MAX_BACKOFF_SECONDS = 300.0


def _now() -> datetime:
    return datetime.now(UTC)


def _backoff_seconds(attempts: int) -> float:
    return float(min(_MAX_BACKOFF_SECONDS, _BASE_BACKOFF_SECONDS * (2 ** max(0, attempts - 1))))


async def enqueue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    handler: str,
    job_type: JobType,
    payload: dict[str, Any],
    run_after: datetime | None = None,
    max_attempts: int = 5,
) -> Job:
    """Create a PENDING job. The handler name is stored in the payload and dispatches the runner."""
    job = Job(
        tenant_id=tenant_id,
        job_type=job_type,
        status=JobStatus.PENDING,
        payload={**payload, "handler": handler},
        run_after=run_after or _now(),
        max_attempts=max_attempts,
    )
    session.add(job)
    await session.flush()
    return job


async def claim_job(
    session: AsyncSession,
    *,
    worker_id: str,
    now: datetime | None = None,
    lease_seconds: float = _LEASE_SECONDS,
) -> Job | None:
    """Claim one runnable job under FOR UPDATE SKIP LOCKED. Does not commit - the caller does.

    Runnable = PENDING and due, OR RUNNING with an expired lease (a crashed worker's job).
    """
    now = now or _now()
    cutoff = now - timedelta(seconds=lease_seconds)
    stmt = (
        select(Job)
        .where(
            or_(
                and_(Job.status == JobStatus.PENDING, Job.run_after <= now),
                and_(Job.status == JobStatus.RUNNING, Job.locked_at < cutoff),
            )
        )
        .order_by(Job.run_after.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = await session.scalar(stmt)
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts += 1
    await session.flush()
    return job


@dataclass(frozen=True)
class RunOutcome:
    ran: bool
    job_id: uuid.UUID | None = None
    status: str | None = None


async def run_next(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    handlers: dict[str, Handler],
    worker_id: str,
    context_factory: Callable[[Job], RequestContext],
    now: datetime | None = None,
) -> RunOutcome:
    """Claim and execute at most one job. Claim commits first (releasing the row lock while the
    job is RUNNING); execution runs in a fresh transaction so its writes are atomic per attempt."""
    now = now or _now()
    async with session_factory() as session:
        job = await claim_job(session, worker_id=worker_id, now=now)
        if job is None:
            await session.rollback()
            return RunOutcome(ran=False)
        job_id = job.id
        handler_name = str(job.payload.get("handler", ""))
        await session.commit()

    async with session_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        handler = handlers.get(handler_name)
        if handler is None:
            job.status = JobStatus.DEAD
            job.error = f"no handler registered: {handler_name!r}"
            await session.commit()
            return RunOutcome(ran=True, job_id=job_id, status=JobStatus.DEAD.value)
        try:
            result = await handler(session, job, context_factory(job))
        except Exception as exc:
            await session.rollback()
            return await _record_failure(session_factory, job_id, exc, now)

        job.status = JobStatus.SUCCEEDED
        job.result = result
        job.error = None
        await session.commit()
        return RunOutcome(ran=True, job_id=job_id, status=JobStatus.SUCCEEDED.value)


async def _record_failure(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: uuid.UUID,
    exc: Exception,
    now: datetime,
) -> RunOutcome:
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.DEAD
        else:
            job.status = JobStatus.PENDING
            job.run_after = now + timedelta(seconds=_backoff_seconds(job.attempts))
        job.error = repr(exc)
        job.locked_by = None
        job.locked_at = None
        await session.commit()
        return RunOutcome(ran=True, job_id=job_id, status=job.status.value)


async def release_claimed(
    session_factory: async_sessionmaker[AsyncSession], *, worker_id: str
) -> int:
    """Graceful shutdown: return jobs this worker still holds to PENDING for another worker."""
    async with session_factory() as session:
        held = list(
            await session.scalars(
                select(Job).where(Job.status == JobStatus.RUNNING, Job.locked_by == worker_id)
            )
        )
        for job in held:
            job.status = JobStatus.PENDING
            job.locked_by = None
            job.locked_at = None
        await session.commit()
        return len(held)
