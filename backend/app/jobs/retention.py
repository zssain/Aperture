"""Retention purge job handler."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.models.job import Job
from app.services.retention.policy import RetentionClass
from app.services.retention.purge import purge_expired


async def handle_retention_purge(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    retention_class = RetentionClass(str(job.payload["retention_class"]))
    purged = await purge_expired(session, context, retention_class)
    return {"retention_class": retention_class.value, "purged": purged}
