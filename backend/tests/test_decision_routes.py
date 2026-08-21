"""HTTP-layer smoke tests for the decision + job routes (auth, serialization, 503 mapping)."""

import httpx
import pytest
from app.services.risk.registry import REGISTRY_PATH
from sqlalchemy.ext.asyncio import AsyncSession

from tests.decision_fixtures import AS_OF, build_decidable, publish_seed
from tests.factories import DEFAULT_PASSWORD

pytestmark = pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="risk artifacts not built")


async def _login(client: httpx.AsyncClient, email: str) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    assert resp.status_code == 200


async def test_decide_route_returns_full_decision(
    db_session: AsyncSession, client: httpx.AsyncClient
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    await _login(client, d.context.email)

    resp = await client.post(
        f"/api/v1/applications/{d.application.id}/decide",
        json={"as_of": AS_OF.isoformat(), "idempotency_key": "route-k"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"].startswith("APPROVE")
    assert body["reasons"][0]["code"].startswith("GATE_")
    assert body["terms"]

    # GET the job route for a non-existent id is a 404 (tenant-scoped, invariant 9).
    missing = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


async def test_decide_route_503_on_assessment_failure(
    db_session: AsyncSession, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    await _login(client, d.context.email)

    def _boom(_snapshot: object) -> object:
        raise RuntimeError("risk down")

    monkeypatch.setattr("app.services.orchestrator.assessments.assess_risk", _boom)

    resp = await client.post(
        f"/api/v1/applications/{d.application.id}/decide",
        json={"as_of": AS_OF.isoformat(), "idempotency_key": "route-fail"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "SYSTEM_UNAVAILABLE"
