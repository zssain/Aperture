"""Prompt 15 event API, consent, idempotency and burst-coalescing tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from app.core.security import hash_token
from app.models.consent import Consent
from app.models.enums import ApplicationStatus, ConsentStatus, JobType, SourceType
from app.models.job import Job
from app.models.ledger import LedgerEvent
from app.models.source import SourceConnection
from app.models.tenant import Tenant
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.decision_fixtures import Decidable, build_decidable

TOKEN = "test-event-service-token"


async def _event_ready(
    session: AsyncSession, *, expired: bool = False, closed: bool = False
) -> Decidable:
    d = await build_decidable(session)
    connection = await session.scalar(
        select(SourceConnection).where(SourceConnection.applicant_id == d.applicant.id)
    )
    assert connection is not None
    consent = Consent(
        tenant_id=d.tenant_id,
        applicant_id=d.applicant.id,
        status=ConsentStatus.GRANTED,
        purpose="ongoing underwriting",
        scope={"sources": [SourceType.BANK.value]},
        granted_at=datetime.now(UTC) - timedelta(days=1),
        expires_at=datetime.now(UTC) + (-timedelta(days=1) if expired else timedelta(days=30)),
    )
    session.add(consent)
    await session.flush()
    connection.consent_id = consent.id
    if closed:
        d.application.status = ApplicationStatus.CLOSED
    tenant = await session.get(Tenant, d.tenant_id)
    assert tenant is not None
    tenant.config = {
        **tenant.config,
        "event_service": {"token_hash": hash_token(TOKEN), "user_id": str(d.user_id)},
    }
    await session.commit()
    return d


def _headers(tenant_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "X-Tenant-ID": str(tenant_id)}


def _payload(applicant_ref: str, *, external_id: str = "evt-1") -> dict[str, object]:
    return {
        "applicant_ref": applicant_ref,
        "source_type": "BANK",
        "occurred_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "amount_paise": 125_000,
        "direction": "CREDIT",
        "description": "Invoice settlement",
        "counterparty": "Private Customer Name",
        "external_id": external_id,
    }


async def test_service_token_required_and_duplicate_returns_original_200(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    d = await _event_ready(db_session)
    payload = _payload(d.applicant.external_ref)
    assert (await client.post("/api/v1/events", json=payload)).status_code == 401

    first = await client.post("/api/v1/events", json=payload, headers=_headers(d.tenant_id))
    assert first.status_code == 202
    again = await client.post("/api/v1/events", json=payload, headers=_headers(d.tenant_id))
    assert again.status_code == 200
    assert again.json()["event_id"] == first.json()["event_id"]
    assert again.json()["job_id"] == first.json()["job_id"]
    row = await db_session.get(LedgerEvent, first.json()["event_id"])
    assert row is not None
    assert row.counterparty_hash is not None
    assert "Private Customer Name" not in str(row.payload)


async def test_expired_consent_is_409(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    d = await _event_ready(db_session, expired=True)
    response = await client.post(
        "/api/v1/events",
        json=_payload(d.applicant.external_ref),
        headers=_headers(d.tenant_id),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONSENT_EXPIRED"


async def test_explicitly_expired_consent_status_is_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    d = await _event_ready(db_session)
    connection = await db_session.scalar(
        select(SourceConnection).where(SourceConnection.applicant_id == d.applicant.id)
    )
    assert connection is not None and connection.consent_id is not None
    consent = await db_session.get(Consent, connection.consent_id)
    assert consent is not None
    consent.status = ConsentStatus.EXPIRED
    await db_session.commit()
    response = await client.post(
        "/api/v1/events",
        json=_payload(d.applicant.external_ref),
        headers=_headers(d.tenant_id),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONSENT_EXPIRED"


async def test_future_and_missing_occurred_at_are_rejected(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    d = await _event_ready(db_session)
    future = _payload(d.applicant.external_ref)
    future["occurred_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert (
        await client.post("/api/v1/events", json=future, headers=_headers(d.tenant_id))
    ).status_code == 422
    missing = _payload(d.applicant.external_ref)
    del missing["occurred_at"]
    assert (
        await client.post("/api/v1/events", json=missing, headers=_headers(d.tenant_id))
    ).status_code == 422


async def test_no_active_application_appends_with_reason_and_no_job(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    d = await _event_ready(db_session, closed=True)
    response = await client.post(
        "/api/v1/events",
        json=_payload(d.applicant.external_ref),
        headers=_headers(d.tenant_id),
    )
    assert response.status_code == 202
    assert response.json()["job_id"] is None
    assert response.json()["reason"] == "NO_ACTIVE_APPLICATION"
    row = await db_session.get(LedgerEvent, response.json()["event_id"])
    assert row is not None
    assert row.payload == {
        "reason": "NO_ACTIVE_APPLICATION",
        "redecision_status": "SKIPPED",
    }


async def test_backfill_is_accepted_and_fifty_events_coalesce_to_one_job(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    d = await _event_ready(db_session)
    job_ids: set[str] = set()
    requests = []
    for index in range(50):
        payload = _payload(d.applicant.external_ref, external_id=f"burst-{index}")
        payload["occurred_at"] = (
            datetime.now(UTC) - timedelta(days=120, minutes=index)
        ).isoformat()
        requests.append(client.post("/api/v1/events", json=payload, headers=_headers(d.tenant_id)))
    responses = await asyncio.gather(*requests)
    for response in responses:
        assert response.status_code == 202
        job_ids.add(response.json()["job_id"])
    assert len(job_ids) == 1
    count = await db_session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.tenant_id == d.tenant_id, Job.job_type == JobType.REDECISION)
    )
    assert count == 1
    job = await db_session.scalar(
        select(Job).where(Job.tenant_id == d.tenant_id, Job.job_type == JobType.REDECISION)
    )
    assert job is not None
    assert len(job.payload["event_ids"]) == 50
