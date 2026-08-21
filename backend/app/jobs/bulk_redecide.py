"""Chunked bulk re-decision handler with persisted progress."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import RequestContext
from app.jobs.runner import enqueue
from app.models.application import Application
from app.models.enums import ApplicationStatus, JobType
from app.models.job import Job


async def handle_bulk_redecide_chunked(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    ids = list(
        await session.scalars(
            select(Application.id)
            .where(
                Application.tenant_id == context.tenant_id,
                Application.status.in_([ApplicationStatus.DECIDED, ApplicationStatus.REFERRED]),
            )
            .order_by(Application.id)
        )
    )
    start = int(job.payload.get("offset", 0))
    chunk = ids[start : start + settings.policy_bulk_redecision_chunk_size]
    as_of = datetime.now(UTC).isoformat()
    for application_id in chunk:
        await enqueue(
            session,
            tenant_id=context.tenant_id,
            handler="decide",
            job_type=JobType.DECISION,
            payload={
                "application_id": str(application_id),
                "as_of": as_of,
                "idempotency_key": f"policy-publish:{job.payload['policy_id']}:{application_id}",
                "user_id": str(context.user_id),
            },
        )
    processed = start + len(chunk)
    root_job_id = _job_id(job.payload.get("root_job_id")) or job.id
    progress = {"processed": processed, "total": len(ids), "complete": processed >= len(ids)}
    if root_job_id != job.id:
        root = await session.get(Job, root_job_id)
        if root is not None and root.tenant_id == context.tenant_id:
            root.result = progress
    if processed < len(ids):
        await enqueue(
            session,
            tenant_id=context.tenant_id,
            handler="bulk_redecide_chunked",
            job_type=JobType.REDECISION,
            payload={**job.payload, "offset": processed, "root_job_id": str(root_job_id)},
        )
    await session.commit()
    return progress


def _job_id(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None
