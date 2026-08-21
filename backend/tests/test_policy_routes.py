import uuid

import httpx
import pytest
from app.models.enums import PolicyStatus, UserRole
from app.models.policy import PolicyVersion
from app.services.policy.defaults import seed_policy_v1
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.factories import DEFAULT_PASSWORD, create_user

pytestmark = requires_db


async def _login(client: httpx.AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200, response.text


async def test_draft_lifecycle_validation_live_immutability_and_publish_gate(
    db_session: AsyncSession, client: httpx.AsyncClient
) -> None:
    owner, tenant = await create_user(db_session, role=UserRole.CREDIT_POLICY_OWNER)
    live = PolicyVersion(
        tenant_id=tenant.id,
        version=1,
        status=PolicyStatus.LIVE,
        rules=seed_policy_v1().model_dump(mode="json"),
        created_by=owner.id,
    )
    db_session.add(live)
    await db_session.commit()
    await _login(client, owner.email)

    listed = await client.get("/api/v1/policies")
    assert listed.status_code == 200
    assert listed.json()[0]["author"] == owner.full_name

    immutable = await client.patch(f"/api/v1/policies/{live.id}", json={"rules": live.rules})
    assert immutable.status_code == 409
    assert immutable.json()["detail"]["code"] == "LIVE_POLICY_IMMUTABLE"

    created = await client.post("/api/v1/policies")
    assert created.status_code == 201
    draft = created.json()
    invalid_rules = {**draft["rules"], "exploration_budget": 0.5}
    patched = await client.patch(f"/api/v1/policies/{draft['id']}", json={"rules": invalid_rules})
    assert patched.status_code == 200
    assert patched.json()["validation"]["ok"] is False
    assert "exploration_budget" in " ".join(patched.json()["validation"]["errors"])

    insufficient = await client.post(f"/api/v1/policies/{draft['id']}/simulate")
    assert insufficient.status_code == 422  # invalid drafts are rejected before cohort work
    publish = await client.post(
        f"/api/v1/policies/{draft['id']}/publish",
        json={
            "simulation_job_id": str(uuid.uuid4()),
            "change_note": "A sufficiently detailed policy change note.",
            "bulk_redecide": False,
        },
    )
    assert publish.status_code == 409
    assert publish.json()["detail"]["code"] == "SIMULATION_REQUIRED"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/policies", None),
        ("POST", "/api/v1/policies", None),
        ("PATCH", "/api/v1/policies/00000000-0000-0000-0000-000000000016", {"rules": {}}),
        ("POST", "/api/v1/policies/00000000-0000-0000-0000-000000000016/simulate", None),
        (
            "GET",
            "/api/v1/policies/00000000-0000-0000-0000-000000000016/simulation/00000000-0000-0000-0000-000000000160",
            None,
        ),
        (
            "POST",
            "/api/v1/policies/00000000-0000-0000-0000-000000000016/publish",
            {
                "simulation_job_id": "00000000-0000-0000-0000-000000000160",
                "change_note": "A sufficiently detailed policy change note.",
            },
        ),
    ],
)
async def test_every_policy_endpoint_rejects_non_owner(
    db_session: AsyncSession,
    client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    analyst, _tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    await _login(client, analyst.email)
    response = await client.request(method, path, json=body)
    assert response.status_code == 403
