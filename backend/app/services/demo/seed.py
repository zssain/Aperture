"""Feature-flagged synthetic demo seed that exercises the production decision paths."""

import hashlib
import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings
from app.core.context import RequestContext
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.jobs.redecide import handle_redecide
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.change import DecisionChange
from app.models.consent import Consent
from app.models.decision import Decision
from app.models.enums import (
    CalibrationStatus,
    ClassificationMethod,
    ConsentStatus,
    EventDirection,
    EvidenceEventType,
    JobStatus,
    MerchantCatalogStatus,
    ModelStatus,
    PolicyStatus,
    SourceConnectionStatus,
    SourceTier,
    SourceType,
    UserRole,
)
from app.models.ledger import LedgerEvent
from app.models.merchant_catalog import MerchantCatalogVersion
from app.models.model_registry import ModelVersion
from app.models.policy import PolicyVersion
from app.models.source import SourceConnection, SourceSnapshot
from app.models.tenant import Tenant
from app.models.user import User
from app.services.catalog.builder import build_and_publish_catalog
from app.services.classification.service import TxnEvent, classify
from app.services.demo.event_generator import income_consistency_sequence
from app.services.events.service import ingest_event
from app.services.orchestrator.service import decide
from app.services.policy.defaults import seed_policy_v1
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEMO_PASSWORD = "Demo-Only-Strong-Passw0rd!"
ROOT = Path(__file__).resolve().parents[4]
PERSONAS = (
    "Asha Gig Worker",
    "Ravi Thin File",
    "Meera Manipulation Review",
    "Kabir High Risk",
    "Nila Sparse Evidence",
    "Arjun Near Boundary",
    "Fatima Salaried",
    "Dev Small Business",
    "Leela Utility History",
    "Mohan Starter Eligible",
    "Sara Mixed Income",
    "Vikram Newly Eligible",
)


class DemoEmbeddingProvider:
    """Deterministic seed-only vectors; never registered in application settings."""

    model_id = "demo-hash-embedding-v1"
    dimension = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            raw = hashlib.shake_256(text.casefold().encode()).digest(self.dimension)
            vector = [(byte - 127.5) / 127.5 for byte in raw]
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([round(value / norm, 8) for value in vector])
        return vectors


def _context(tenant: Tenant, analyst: User) -> RequestContext:
    return RequestContext(
        user_id=analyst.id,
        tenant_id=tenant.id,
        role=analyst.role.value,
        email=analyst.email,
        session_id=uuid.uuid5(uuid.NAMESPACE_URL, "aperture-demo-session"),
        approval_ceilings_paise={},
    )


def _trace(
    *,
    event_id: uuid.UUID,
    occurred_at: datetime,
    direction: EventDirection,
    amount_paise: int,
    balance_paise: int,
    description: str,
    counterparty_hash: str,
    connection_id: uuid.UUID,
) -> tuple[str, ClassificationMethod]:
    result = classify(
        [
            TxnEvent(
                event_id=event_id,
                occurred_at=occurred_at,
                direction=direction,
                amount_paise=amount_paise,
                balance_paise=balance_paise,
                description=description,
                counterparty_hash=counterparty_hash,
                source_connection_id=connection_id,
            )
        ]
    ).events[0]
    return result.category.value, result.classification_method


async def _create_persona(
    session: AsyncSession,
    *,
    tenant: Tenant,
    index: int,
    name: str,
    anchor: datetime,
) -> Application:
    ref = f"demo-persona-{index + 1:02d}"
    applicant = Applicant(tenant_id=tenant.id, external_ref=ref, display_name=name)
    session.add(applicant)
    await session.flush()
    requested = 20_000_000 if index in {3, 11} else 5_000_000 + index * 250_000
    application = Application(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        occupation="self-employed" if index in {0, 7, 10, 11} else "salaried",
        requested_amount_paise=requested,
        requested_tenor_months=12,
    )
    session.add(application)
    consent = Consent(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        status=ConsentStatus.GRANTED,
        purpose="synthetic demonstration of ongoing underwriting",
        scope={"sources": [SourceType.BANK.value], "demo": True},
        granted_at=anchor - timedelta(days=220),
        expires_at=anchor + timedelta(days=365),
        artefact_hash=hashlib.sha256(f"demo-consent:{ref}".encode()).hexdigest(),
    )
    session.add(consent)
    await session.flush()
    connection = SourceConnection(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        consent_id=consent.id,
        source_type=SourceType.BANK,
        tier=SourceTier.AA_VERIFIED,
        provider="DEMO_SYNTHETIC",
        status=SourceConnectionStatus.CONNECTED,
    )
    session.add(connection)
    await session.flush()
    months = 2 if index == 4 else 7
    snapshot = SourceSnapshot(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        applicant_id=applicant.id,
        tier=SourceTier.AA_VERIFIED,
        fetched_at=anchor,
        period_start=anchor - timedelta(days=months * 30 + 5),
        period_end=anchor - timedelta(days=2),
        content_hash=hashlib.sha256(f"demo-corpus:{ref}".encode()).hexdigest(),
        record_count=months * 3,
        ingested_count=months * 3,
        payload={"synthetic_demo": True},
    )
    session.add(snapshot)
    await session.flush()

    balance = 2_000_000
    for month in reversed(range(months)):
        when = anchor - timedelta(days=30 * month + 16)
        base_income = 3_000_000 if index == 11 else 4_500_000 + index * 125_000
        income = base_income
        if index in {3, 5, 10}:
            income += ((month % 3) - 1) * 2_000_000
        income_text = (
            "gig partner payout"
            if index in {0, 9}
            else "invoice business settlement"
            if index in {7, 10, 11}
            else "monthly salary payroll credit"
        )
        rows = (
            (when, EventDirection.CREDIT, max(500_000, income), income_text, "income"),
            (when + timedelta(days=2), EventDirection.DEBIT, 1_200_000, "monthly rent", "rent"),
            (when + timedelta(days=4), EventDirection.DEBIT, 350_000, "utility bill", "utility"),
        )
        for position, (occurred, direction, amount, description, counterparty) in enumerate(rows):
            balance += amount if direction is EventDirection.CREDIT else -amount
            event_id = uuid.uuid5(
                uuid.NAMESPACE_URL, f"aperture:{ref}:{month}:{position}:{description}"
            )
            category, method = _trace(
                event_id=event_id,
                occurred_at=occurred,
                direction=direction,
                amount_paise=amount,
                balance_paise=balance,
                description=description,
                counterparty_hash=f"demo-{ref}-{counterparty}",
                connection_id=connection.id,
            )
            session.add(
                LedgerEvent(
                    id=event_id,
                    tenant_id=tenant.id,
                    applicant_id=applicant.id,
                    source_connection_id=connection.id,
                    source_snapshot_id=snapshot.id,
                    event_type=EvidenceEventType.TRANSACTION,
                    direction=direction,
                    amount_paise=amount,
                    balance_paise=balance,
                    description=description,
                    category=category,
                    classification_method=method,
                    classifier_version="clf-v2",
                    counterparty_hash=f"demo-{ref}-{counterparty}",
                    occurred_at=occurred,
                    received_at=anchor,
                    idempotency_key=f"demo:{ref}:{month}:{position}",
                    payload={"synthetic_demo": True},
                )
            )
    return application


async def seed_demo() -> None:
    if not settings.demo_seed_enabled:
        raise RuntimeError("demo seed refused: set DEMO_SEED_ENABLED=true explicitly")
    started = datetime.now(UTC)
    async with SessionLocal() as session:
        catalog = await session.scalar(
            select(MerchantCatalogVersion).where(
                MerchantCatalogVersion.status == MerchantCatalogStatus.LIVE
            )
        )
        if catalog is None or catalog.version != "demo-catalog-v2":
            await build_and_publish_catalog(
                session, DemoEmbeddingProvider(), version="demo-catalog-v2"
            )

        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "aperture-demo"))
        if tenant is None:
            tenant = Tenant(name="Aperture Demo", slug="aperture-demo", config={"demo": True})
            session.add(tenant)
            await session.flush()
        users: dict[UserRole, User] = {}
        for role in UserRole:
            email = f"{role.value.casefold().replace('_', '-')}@demo.aperture.test"
            user = await session.scalar(
                select(User).where(User.tenant_id == tenant.id, User.email == email)
            )
            if user is None:
                user = User(
                    tenant_id=tenant.id,
                    email=email,
                    full_name=f"Demo {role.value.replace('_', ' ').title()}",
                    role=role,
                    is_active=True,
                    hashed_password=hash_password(DEMO_PASSWORD),
                )
                session.add(user)
                await session.flush()
            users[role] = user
        owner = users[UserRole.CREDIT_POLICY_OWNER]
        analyst = users[UserRole.CREDIT_ANALYST]
        benchmark = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.tenant_id == tenant.id,
                ModelVersion.name == "benchmark",
                ModelVersion.version == "benchmark-v1",
            )
        )
        if benchmark is None:
            manifest = json.loads((ROOT / "ml/artifacts/registry.json").read_text())
            entry = manifest["models"]["benchmark-v1"]
            session.add(
                ModelVersion(
                    tenant_id=tenant.id,
                    name="benchmark",
                    version="benchmark-v1",
                    kind="benchmark",
                    status=ModelStatus.ACTIVE,
                    calibration_status=CalibrationStatus.CALIBRATED,
                    artifact_uri=str(entry["artifact_path"]),
                    artifact_hash=str(entry["artifact_sha256"]),
                    metrics={"source": "ml/artifacts/benchmark_v1.metrics.json"},
                )
            )
        rules = seed_policy_v1().model_dump(mode="json")
        live = await session.scalar(
            select(PolicyVersion).where(
                PolicyVersion.tenant_id == tenant.id, PolicyVersion.status == PolicyStatus.LIVE
            )
        )
        if live is None:
            session.add(
                PolicyVersion(
                    tenant_id=tenant.id,
                    version=1,
                    status=PolicyStatus.LIVE,
                    rules=rules,
                    published_at=started,
                    created_by=owner.id,
                )
            )
        draft = await session.scalar(
            select(PolicyVersion).where(
                PolicyVersion.tenant_id == tenant.id, PolicyVersion.version == 2
            )
        )
        if draft is None:
            session.add(
                PolicyVersion(
                    tenant_id=tenant.id,
                    version=2,
                    status=PolicyStatus.DRAFT,
                    rules=rules,
                    created_by=owner.id,
                )
            )
        await session.commit()

        applications: list[Application] = []
        for index, name in enumerate(PERSONAS):
            ref = f"demo-persona-{index + 1:02d}"
            applicant = await session.scalar(
                select(Applicant).where(
                    Applicant.tenant_id == tenant.id, Applicant.external_ref == ref
                )
            )
            if applicant is None:
                application = await _create_persona(
                    session, tenant=tenant, index=index, name=name, anchor=started
                )
            else:
                found_application = await session.scalar(
                    select(Application).where(
                        Application.tenant_id == tenant.id,
                        Application.applicant_id == applicant.id,
                    )
                )
                if found_application is None:
                    raise RuntimeError(f"incomplete existing demo persona: {ref}")
                application = found_application
            applications.append(application)
        await session.commit()

        context = _context(tenant, analyst)
        for index, application in enumerate(applications):
            existing = await session.scalar(
                select(Decision).where(
                    Decision.tenant_id == tenant.id,
                    Decision.application_id == application.id,
                )
            )
            if existing is None:
                await decide(
                    session,
                    context,
                    application_id=application.id,
                    as_of=started,
                    idempotency_key=f"demo-initial-{index + 1:02d}",
                    generate_recourse=True,
                )

        transition_application = applications[11]
        transition_change = await session.scalar(
            select(DecisionChange).where(
                DecisionChange.tenant_id == tenant.id,
                DecisionChange.application_id == transition_application.id,
            )
        )
        if transition_change is None:
            applicant = await session.get(Applicant, transition_application.applicant_id)
            if applicant is None:
                raise RuntimeError("demo transition applicant disappeared")
            ingested = [
                await ingest_event(session, context, event)
                for event in income_consistency_sequence(applicant.external_ref, now=started)
            ]
            jobs = {result.job.id: result.job for result in ingested if result.job is not None}
            if len(jobs) != 1:
                raise RuntimeError("demo transition events did not coalesce into one job")
            job = next(iter(jobs.values()))
            job.status = JobStatus.RUNNING
            await session.commit()
            result = await handle_redecide(session, job, context)
            if result.get("status") != "CHANGED" or result.get("direction") != "IMPROVED":
                raise RuntimeError(f"demo transition did not improve: {result}")
            transition_change = await session.get(
                DecisionChange, uuid.UUID(str(result["change_id"]))
            )
        if transition_change is None or not transition_change.feature_changes:
            raise RuntimeError("demo transition lacks a named driving feature")

        decision_count = int(
            await session.scalar(
                select(func.count()).select_from(Decision).where(Decision.tenant_id == tenant.id)
            )
            or 0
        )
        action_count = int(
            await session.scalar(
                select(func.count(func.distinct(Decision.action))).where(
                    Decision.tenant_id == tenant.id
                )
            )
            or 0
        )
        if decision_count < 13 or action_count < 2:
            raise RuntimeError(
                "demo book is incomplete or lacks a realistic mix: "
                f"{decision_count}, {action_count}"
            )
        elapsed = (datetime.now(UTC) - started).total_seconds()
        if elapsed >= 120:
            raise RuntimeError(f"demo seed exceeded two-minute budget: {elapsed:.1f}s")
    print(
        "Demo seeded: live catalogue, 1 tenant, 4 users, 12 full event-corpus applicants, "
        f"{decision_count} decisions, and an improved eligibility change ({elapsed:.1f}s)."
    )
    print(f"Demo password: {DEMO_PASSWORD}")
