from datetime import UTC, datetime

import httpx
from app.core.security import hash_token
from app.models.tenant import Tenant
from app.services.orchestrator.service import decide
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.decision_fixtures import AS_OF, build_decidable, publish_seed

pytestmark = requires_db


async def test_outcome_ingestion_is_idempotent_and_keeps_decision_cohort(
    db_session: AsyncSession, client: httpx.AsyncClient
) -> None:
    fixture = await build_decidable(db_session)
    await publish_seed(db_session, fixture)
    result = await decide(
        db_session,
        fixture.context,
        application_id=fixture.application.id,
        as_of=AS_OF,
        idempotency_key="outcome-decision",
    )
    token = "outcome-service-token"
    tenant = await db_session.get(Tenant, fixture.tenant_id)
    assert tenant is not None
    tenant.config = {
        **tenant.config,
        "event_service": {"token_hash": hash_token(token), "user_id": str(fixture.user_id)},
    }
    await db_session.commit()
    payload = {
        "decision_id": str(result.decision.id),
        "outcome_type": "PERFORMING",
        "observed_at": datetime(2026, 8, 20, tzinfo=UTC).isoformat(),
    }
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(fixture.tenant_id)}
    first = await client.post("/api/v1/outcomes", json=payload, headers=headers)
    second = await client.post("/api/v1/outcomes", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["cohort"] == {
        "exploration_cohort": result.decision.exploration_cohort,
        "performance_window_closed": True,
        "policy_version_id": str(result.decision.policy_version_id),
    }
