"""Policy draft, simulation and publication gates composed through the public API."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_policy_routes import (
    test_draft_lifecycle_validation_live_immutability_and_publish_gate as _policy_gate_scenario,
)


async def test_draft_simulate_publish_gates(
    db_session: AsyncSession, client: httpx.AsyncClient
) -> None:
    await _policy_gate_scenario(db_session, client)
