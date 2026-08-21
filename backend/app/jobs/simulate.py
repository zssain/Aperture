"""Asynchronous full-book policy simulation handler."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import RequestContext
from app.jobs.handlers import _uuid
from app.models.job import Job
from app.services.policy.simulation import simulate_policy


async def handle_simulate(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    report = await simulate_policy(
        session, tenant_id=context.tenant_id, policy_id=_uuid(job.payload["policy_version_id"])
    )
    minimum = settings.policy_simulation_minimum_snapshots
    if int(report["n_snapshots"]) < minimum:
        raise ValueError(
            f"Simulation requires {minimum} complete stored assessment sets; "
            f"{report['n_snapshots']} exist."
        )
    return report
