"""Feature-flagged synthetic demo seed that exercises the production decision paths.

The persona corpus lives in :mod:`app.services.demo.personas`; this module persists it
and runs every applicant through the REAL pipeline — classification, snapshot, four
assessments, policy engine, recourse — so nothing the demo shows is stubbed.
"""

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
from app.services.demo.personas import PERSONAS, TRANSITION_REF, PersonaSpec, build_corpus
from app.services.events.service import ingest_event
from app.services.orchestrator.service import decide
from app.services.policy.defaults import seed_policy_v1
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEMO_PASSWORD = "123456"  # sandbox-only demo credential
# Explicit per-role sign-in emails (sandbox only). Not derived from the role name so
# they can read however the demo wants.
DEMO_EMAILS: dict[UserRole, str] = {
    UserRole.CREDIT_ANALYST: "creditanalyst@aperture.com",
    UserRole.CREDIT_POLICY_OWNER: "policyowner@aperture.com",
    UserRole.FRAUD_REVIEWER: "fraudreviewer@aperture.com",
    UserRole.AUDITOR: "auditor@aperture.com",
}
ROOT = Path(__file__).resolve().parents[4]


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
    balance_paise: int | None,
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
    spec: PersonaSpec,
    anchor: datetime,
) -> Application:
    corpus = build_corpus(spec, anchor)
    applicant = Applicant(tenant_id=tenant.id, external_ref=spec.ref, display_name=spec.name)
    session.add(applicant)
    await session.flush()
    application = Application(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        occupation=spec.occupation,
        requested_amount_paise=spec.requested_amount_paise,
        requested_tenor_months=spec.requested_tenor_months,
    )
    session.add(application)
    consent = Consent(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        status=ConsentStatus.GRANTED,
        purpose="Credit underwriting (sandbox demonstration)",
        scope={"sources": [SourceType.BANK.value], "demo": True},
        granted_at=anchor - timedelta(days=30 * spec.months + 10),
        expires_at=anchor + timedelta(days=365),
        artefact_hash=hashlib.sha256(f"demo-consent:{spec.ref}".encode()).hexdigest(),
    )
    session.add(consent)
    await session.flush()
    connection = SourceConnection(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        consent_id=consent.id,
        source_type=SourceType.BANK,
        tier=spec.tier,
        provider="DEMO_SYNTHETIC",
        status=SourceConnectionStatus.CONNECTED,
    )
    session.add(connection)
    await session.flush()
    snapshot = SourceSnapshot(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        applicant_id=applicant.id,
        tier=spec.tier,
        fetched_at=anchor,
        period_start=corpus.period_start,
        period_end=corpus.period_end,
        content_hash=hashlib.sha256(f"demo-corpus:{spec.ref}".encode()).hexdigest(),
        record_count=len(corpus.events),
        ingested_count=len(corpus.events),
        payload={"synthetic_demo": True},
    )
    session.add(snapshot)
    await session.flush()

    for index, event in enumerate(corpus.events):
        event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"aperture:{spec.ref}:{index}")
        category, method = _trace(
            event_id=event_id,
            occurred_at=event.occurred_at,
            direction=event.direction,
            amount_paise=event.amount_paise,
            balance_paise=event.balance_paise,
            description=event.description,
            counterparty_hash=event.counterparty_hash,
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
                direction=event.direction,
                amount_paise=event.amount_paise,
                balance_paise=event.balance_paise,
                description=event.description,
                category=category,
                classification_method=method,
                classifier_version="clf-v2",
                counterparty_hash=event.counterparty_hash,
                occurred_at=event.occurred_at,
                received_at=anchor,
                idempotency_key=f"demo:{spec.ref}:{index}",
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
        if catalog is None:
            # Only publish the hash-embedding catalogue on a virgin database. If any
            # LIVE catalogue exists (for example one built with a real embedding
            # provider) it is left untouched so runtime queries stay consistent.
            await build_and_publish_catalog(
                session, DemoEmbeddingProvider(), version="demo-catalog-v2"
            )

        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "aperture-demo"))
        if tenant is None:
            tenant = Tenant(
                name="Aperture Demo",
                slug="aperture-demo",
                config={
                    "demo": True,
                    # Per-role approval authority. Without this, ceiling_for_role() is
                    # None and every human approval is rejected as INSUFFICIENT_AUTHORITY,
                    # which would block the entire review/override journey. Analyst can
                    # confirm starter/standard cases but not high-value ones (Fatima at
                    # ₹2.5L stays above the analyst ceiling — demonstrating enforcement).
                    "approval_ceilings_paise": {
                        "CREDIT_ANALYST": 15_000_000,
                        "FRAUD_REVIEWER": 15_000_000,
                        "CREDIT_POLICY_OWNER": 100_000_000,
                    },
                },
            )
            session.add(tenant)
            await session.flush()
        users: dict[UserRole, User] = {}
        for role in UserRole:
            email = DEMO_EMAILS[role]
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
        for spec in PERSONAS:
            applicant = await session.scalar(
                select(Applicant).where(
                    Applicant.tenant_id == tenant.id, Applicant.external_ref == spec.ref
                )
            )
            if applicant is None:
                application = await _create_persona(
                    session, tenant=tenant, spec=spec, anchor=started
                )
            else:
                found_application = await session.scalar(
                    select(Application).where(
                        Application.tenant_id == tenant.id,
                        Application.applicant_id == applicant.id,
                    )
                )
                if found_application is None:
                    raise RuntimeError(f"incomplete existing demo persona: {spec.ref}")
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

        transition_index = next(
            index for index, spec in enumerate(PERSONAS) if spec.ref == TRANSITION_REF
        )
        transition_application = applications[transition_index]
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
        if decision_count < 13 or action_count < 4:
            raise RuntimeError(
                "demo book is incomplete or lacks a realistic mix: "
                f"{decision_count} decisions, {action_count} distinct actions"
            )
        elapsed = (datetime.now(UTC) - started).total_seconds()
        if elapsed >= 120:
            raise RuntimeError(f"demo seed exceeded two-minute budget: {elapsed:.1f}s")
    print(
        "Demo seeded: live catalogue, 1 tenant, 4 users, "
        f"{len(PERSONAS)} full event-corpus applicants, "
        f"{decision_count} decisions, and an improved eligibility change ({elapsed:.1f}s)."
    )
    print(f"Demo password: {DEMO_PASSWORD}")
