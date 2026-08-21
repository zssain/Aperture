"""Atomic Postgres-backed sliding-window rate limiter."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import RateLimitEvent


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


LIMITS = {
    "login": RateLimit(5, 60),
    "decide": RateLimit(30, 60),
    "upload": RateLimit(10, 60),
    "recourse": RateLimit(20, 3600),
    "events": RateLimit(1000, 60),
    "policy_simulate": RateLimit(10, 3600),
    "notice_render": RateLimit(60, 3600),
}


class PostgresRateLimitExceededError(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


async def hit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    bucket: str,
    principal: str,
    now: datetime | None = None,
) -> None:
    policy = LIMITS[bucket]
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=policy.window_seconds)
    principal_hash = hashlib.sha256(principal.encode()).hexdigest()
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"rate:{bucket}:{principal_hash}")))
    )
    await session.execute(delete(RateLimitEvent).where(RateLimitEvent.created_at < cutoff))
    first = await session.scalar(
        select(func.min(RateLimitEvent.created_at)).where(
            RateLimitEvent.tenant_id == tenant_id,
            RateLimitEvent.bucket == bucket,
            RateLimitEvent.principal_hash == principal_hash,
        )
    )
    count = int(
        await session.scalar(
            select(func.count())
            .select_from(RateLimitEvent)
            .where(
                RateLimitEvent.tenant_id == tenant_id,
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.principal_hash == principal_hash,
                RateLimitEvent.created_at >= cutoff,
            )
        )
        or 0
    )
    if count >= policy.limit:
        await session.rollback()
        retry = (
            max(1, int(policy.window_seconds - (now - first).total_seconds()))
            if first
            else policy.window_seconds
        )
        raise PostgresRateLimitExceededError(retry)
    session.add(
        RateLimitEvent(
            tenant_id=tenant_id, bucket=bucket, principal_hash=principal_hash, created_at=now
        )
    )
    await session.commit()


async def hit_many(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    bucket: str,
    principals: tuple[str, ...],
) -> None:
    """Enforce the same policy independently for each supplied dimension."""
    for principal in principals:
        await hit(session, tenant_id=tenant_id, bucket=bucket, principal=principal)
