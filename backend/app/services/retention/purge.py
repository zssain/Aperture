"""Audited, class-specific purge; decision records are never deleted."""

import os
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.models.security import RetentionItem
from app.services.audit.ledger import append
from app.services.retention.policy import RetentionClass


async def purge_expired(
    session: AsyncSession,
    context: RequestContext,
    retention_class: RetentionClass,
    *,
    now: datetime | None = None,
) -> int:
    if retention_class == RetentionClass.DECISION_RECORD:
        return 0
    now = now or datetime.now(UTC)
    items = list(
        await session.scalars(
            select(RetentionItem).where(
                RetentionItem.tenant_id == context.tenant_id,
                RetentionItem.retention_class == retention_class.value,
                RetentionItem.expires_at <= now,
                RetentionItem.purged_at.is_(None),
                RetentionItem.legal_hold.is_(False),
            )
        )
    )
    count = 0
    for item in items:
        if item.storage_path:
            with suppress(FileNotFoundError):
                os.unlink(item.storage_path)
        item.purged_at = now
        count += 1
        await append(
            session,
            context,
            "RETENTION_PURGED",
            item.subject_type,
            item.subject_id,
            {"retention_class": retention_class.value, "retention_item_id": str(item.id)},
        )
    await session.commit()
    return count


async def schedule_raw_purge(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    applicant_id: uuid.UUID,
    storage_path: str | None,
    subject_id: uuid.UUID | None,
    expires_at: datetime,
) -> RetentionItem:
    item = RetentionItem(
        tenant_id=tenant_id,
        retention_class=RetentionClass.RAW_EVIDENCE.value,
        applicant_id=applicant_id,
        subject_type="source_snapshot",
        subject_id=subject_id,
        storage_path=storage_path,
        expires_at=expires_at,
    )
    session.add(item)
    await session.flush()
    return item
