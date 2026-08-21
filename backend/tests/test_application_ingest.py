"""Prompt 14 case-intake integration tests for both evidence paths and edge cases."""

import pathlib
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from app.jobs.handlers import HANDLERS, system_context
from app.jobs.runner import run_next
from app.models.application import Application
from app.models.enums import JobStatus, UserRole
from app.models.job import Job
from app.services.policy.defaults import seed_policy_v1
from app.services.policy.store import publish_policy
from app.services.risk.registry import REGISTRY_PATH
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.factories import DEFAULT_PASSWORD, create_user

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "statements"

pytestmark = pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="risk artifacts not built")


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _authenticated(
    session: AsyncSession, client: httpx.AsyncClient
) -> tuple[uuid.UUID, uuid.UUID]:
    user, tenant = await create_user(session, role=UserRole.CREDIT_ANALYST)
    await publish_policy(
        session,
        tenant_id=tenant.id,
        version=1,
        rules=seed_policy_v1(),
        created_by=user.id,
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200
    return user.id, tenant.id


def _fields(ref: str) -> dict[str, object]:
    return {
        "display_name": "Mira Shah",
        "external_ref": ref,
        "declared_income_paise": 5_000_000,
        "occupation": "GIG",
        "requested_amount_paise": 2_000_000,
        "requested_tenor_months": 12,
        "product": "PERSONAL_LOAN",
    }


async def _run_pipeline(engine: AsyncEngine) -> None:
    outcome = await run_next(
        _factory(engine),
        handlers=HANDLERS,
        worker_id=f"test-{uuid.uuid4()}",
        context_factory=system_context,
    )
    assert outcome.status == JobStatus.SUCCEEDED.value


async def test_connect_path_runs_to_a_decided_case_without_browser_polling(
    db_session: AsyncSession, db_engine: AsyncEngine, client: httpx.AsyncClient
) -> None:
    await _authenticated(db_session, client)
    response = await client.post(
        "/api/v1/applications",
        json={
            **_fields(f"connect-{uuid.uuid4().hex}"),
            "consent_granted": True,
            "purpose": "Credit underwriting",
            "scope": ["BANK"],
            "expires_at": "2026-12-31T23:59:59Z",
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "QUEUED"

    # Simulates closing the tab: no GET /jobs poll is needed for the server worker to finish.
    await _run_pipeline(db_engine)
    job = await client.get(f"/api/v1/jobs/{created['job_id']}")
    assert job.status_code == 200
    progress = job.json()["result"]
    assert progress["decision_id"]
    assert [stage["status"] for stage in progress["stages"]] == [
        "complete",
        "complete",
        "complete",
        "complete",
        "complete",
        "complete",
    ]
    case = await client.get(f"/api/v1/cases/{created['application_id']}")
    assert case.status_code == 200
    assert case.json()["decision"] is not None
    queue = await client.get("/api/v1/queue?view=all-decisions")
    assert any(row["application_id"] == created["application_id"] for row in queue.json()["rows"])


async def test_document_path_reports_rows_and_duplicate_links_existing_case(
    db_session: AsyncSession, db_engine: AsyncEngine, client: httpx.AsyncClient
) -> None:
    await _authenticated(db_session, client)
    data = {key: str(value) for key, value in _fields(f"upload-{uuid.uuid4().hex}").items()}
    file_bytes = (FIXTURES / "clean_gig.csv").read_bytes()
    response = await client.post(
        "/api/v1/applications/documents",
        data=data,
        files={"file": ("clean_gig.csv", file_bytes, "text/csv")},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["ingestion"]["ingested"] == 7
    assert created["ingestion"]["rejected"] == 0
    await _run_pipeline(db_engine)
    completed = await client.get(f"/api/v1/jobs/{created['job_id']}")
    assert completed.json()["result"]["decision_id"]
    case = await client.get(f"/api/v1/cases/{created['application_id']}")
    assert case.json()["decision"] is not None

    duplicate_data = {
        key: str(value) for key, value in _fields(f"duplicate-{uuid.uuid4().hex}").items()
    }
    duplicate = await client.post(
        "/api/v1/applications/documents",
        data=duplicate_data,
        files={"file": ("clean_gig.csv", file_bytes, "text/csv")},
    )
    assert duplicate.status_code == 201
    body = duplicate.json()
    assert body["status"] == "ALREADY_INGESTED"
    assert body["existing_case_url"] == f"/cases/{created['application_id']}"


async def test_malformed_upload_names_expected_format_and_creates_no_application(
    db_session: AsyncSession, client: httpx.AsyncClient
) -> None:
    _user_id, tenant_id = await _authenticated(db_session, client)
    before = int(
        await db_session.scalar(
            select(func.count()).select_from(Application).where(Application.tenant_id == tenant_id)
        )
        or 0
    )
    response = await client.post(
        "/api/v1/applications/documents",
        data={key: str(value) for key, value in _fields(f"bad-{uuid.uuid4().hex}").items()},
        files={
            "file": (
                "malformed_columns.csv",
                (FIXTURES / "malformed_columns.csv").read_bytes(),
                "text/csv",
            )
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "SCHEMA_ERROR"
    assert detail["expected_columns"] == ["Date", "Description", "Amount"]
    after = int(
        await db_session.scalar(
            select(func.count()).select_from(Application).where(Application.tenant_id == tenant_id)
        )
        or 0
    )
    assert after == before


async def test_zero_usable_rows_creates_case_but_no_decision(
    db_session: AsyncSession, db_engine: AsyncEngine, client: httpx.AsyncClient
) -> None:
    await _authenticated(db_session, client)
    unusable = (
        b"Date,Description,Amount\nnot-a-date,Bad date,100.00\n2026-01-01,Bad amount,not-money\n"
    )
    response = await client.post(
        "/api/v1/applications/documents",
        data={key: str(value) for key, value in _fields(f"empty-{uuid.uuid4().hex}").items()},
        files={"file": ("unusable.csv", unusable, "text/csv")},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["ingestion"]["ingested"] == 0
    assert created["ingestion"]["rejected"] == 2
    assert len(created["ingestion"]["rejected_reasons"]) == 2

    await _run_pipeline(db_engine)
    job = await client.get(f"/api/v1/jobs/{created['job_id']}")
    assert job.json()["result"]["outcome"] == "ZERO_USABLE_EVIDENCE"
    case = await client.get(f"/api/v1/cases/{created['application_id']}")
    assert case.status_code == 200
    assert case.json()["decision"] is None


async def test_declined_consent_is_undecided_and_in_evidence_needed(
    db_session: AsyncSession, client: httpx.AsyncClient
) -> None:
    await _authenticated(db_session, client)
    response = await client.post(
        "/api/v1/applications",
        json={
            **_fields(f"declined-{uuid.uuid4().hex}"),
            "consent_granted": False,
            "scope": [],
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["application_status"] == "AWAITING_CONSENT"
    assert created["job_id"] is None

    queue = await client.get("/api/v1/queue?view=evidence-needed")
    assert queue.status_code == 200
    row = next(
        item for item in queue.json()["rows"] if item["application_id"] == created["application_id"]
    )
    assert row["routed_because"]["text"] == "Consent required"
    assert row["pd"] == {"value": None, "status": "unavailable"}


async def test_provider_failure_is_stage_scoped_and_other_source_completes(
    db_session: AsyncSession, db_engine: AsyncEngine, client: httpx.AsyncClient
) -> None:
    await _authenticated(db_session, client)
    response = await client.post(
        "/api/v1/applications",
        json={
            **_fields(f"partial-{uuid.uuid4().hex}"),
            "consent_granted": True,
            "scope": ["BANK", "UPI"],
            "failure_modes": {"BANK": "timeout"},
            "expires_at": datetime(2026, 12, 31, tzinfo=UTC).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    await _run_pipeline(db_engine)
    job = await client.get(f"/api/v1/jobs/{response.json()['job_id']}")
    result = job.json()["result"]
    fetching = next(stage for stage in result["stages"] if stage["key"] == "fetching")
    assert fetching["status"] == "failed"
    assert result["retryable_stage"] == "fetching"
    assert {source["status"] for source in result["sources"]} == {"UNAVAILABLE", "OK"}
    assert result["decision_id"]

    case = await client.get(f"/api/v1/cases/{response.json()['application_id']}")
    assert case.status_code == 200
    case_body = case.json()
    assert {(source["source_type"], source["status"]) for source in case_body["sources"]} == {
        ("BANK", "UNAVAILABLE"),
        ("UPI", "CONNECTED"),
    }
    missing_sources = case_body["assessments"]["COVERAGE"]["payload"]["missing_sources"]
    assert any(source["source_type"] == "BANK" for source in missing_sources)

    retried = await client.post(
        f"/api/v1/jobs/{job.json()['id']}/retry", json={"stage": "fetching"}
    )
    assert retried.status_code == 201
    retry_job = await db_session.get(Job, uuid.UUID(retried.json()["id"]))
    assert retry_job is not None
    assert len(retry_job.payload["connection_ids"]) == 1
