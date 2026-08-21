"""Idempotency for ``decide``: one decision per ``(tenant, idempotency_key)``.

A repeated key returns the existing decision with no new work and no new ledger entry. The
uniqueness is also enforced at the database level (a partial unique index), so two concurrent
calls cannot both create a decision - the loser catches the integrity error and returns the
winner's decision.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision import Decision


async def find_existing_decision(
    session: AsyncSession, *, tenant_id: uuid.UUID, idempotency_key: str
) -> Decision | None:
    result: Decision | None = await session.scalar(
        select(Decision).where(
            Decision.tenant_id == tenant_id,
            Decision.idempotency_key == idempotency_key,
        )
    )
    return result
