"""Consent-gated, idempotent event append and re-decision job coalescing."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.context import RequestContext
from app.jobs.runner import enqueue
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.enums import ApplicationStatus, EvidenceEventType, JobStatus, JobType
from app.models.job import Job
from app.models.ledger import LedgerEvent
from app.models.source import SourceConnection
from app.schemas.event import EventCreate
from app.services.classification.service import TxnEvent
from app.services.classification.vector import classify_for_ingest, normalize_narration
from app.services.ingestion.normalizer import counterparty_hash, idempotency_key
from app.services.ingestion.service import ConsentError, assert_active_consent, tenant_salt
from app.services.sources.base import NormalizedEvent
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class EventIngestionResult:
    event: LedgerEvent
    job: Job | None
    duplicate: bool
    status: str
    reason: str | None = None


async def _job_for_event(
    session: AsyncSession, tenant_id: uuid.UUID, event_id: uuid.UUID
) -> Job | None:
    job: Job | None = await session.scalar(
        select(Job)
        .where(Job.tenant_id == tenant_id, Job.payload.contains({"event_ids": [str(event_id)]}))
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return job


async def ingest_event(
    session: AsyncSession,
    context: RequestContext,
    payload: EventCreate,
) -> EventIngestionResult:
    now = datetime.now(UTC)
    if payload.occurred_at > now:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "FUTURE_EVENT", "message": "occurred_at must not be in the future"},
        )

    applicant = await session.scalar(
        select(Applicant).where(
            Applicant.tenant_id == context.tenant_id,
            Applicant.external_ref == payload.applicant_ref,
        )
    )
    if applicant is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "APPLICANT_NOT_FOUND", "message": "Applicant not found"},
        )
    connection = await session.scalar(
        select(SourceConnection)
        .where(
            SourceConnection.tenant_id == context.tenant_id,
            SourceConnection.applicant_id == applicant.id,
            SourceConnection.source_type == payload.source_type,
        )
        .order_by(SourceConnection.created_at.desc())
        .limit(1)
    )
    if connection is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "CONSENT_NOT_FOUND",
                "message": "No consented source connection exists",
            },
        )
    try:
        await assert_active_consent(session, connection, now=now)
    except ConsentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message}
        ) from exc

    normalized = NormalizedEvent(
        occurred_at=payload.occurred_at,
        direction=payload.direction,
        amount_paise=payload.amount_paise,
        description=payload.description,
        counterparty=payload.counterparty,
        balance_paise=None,
        external_id=payload.external_id,
    )
    # external_id makes the frozen key independent of an artificial snapshot id.
    key = idempotency_key(payload.source_type, normalized, uuid.UUID(int=0))
    existing = await session.scalar(
        select(LedgerEvent).where(
            LedgerEvent.tenant_id == context.tenant_id, LedgerEvent.idempotency_key == key
        )
    )
    if existing is not None:
        return EventIngestionResult(
            existing,
            await _job_for_event(session, context.tenant_id, existing.id),
            True,
            "DUPLICATE",
        )

    active_application = await session.scalar(
        select(Application)
        .where(
            Application.tenant_id == context.tenant_id,
            Application.applicant_id == applicant.id,
            Application.status.not_in(
                [ApplicationStatus.CLOSED, ApplicationStatus.AWAITING_CONSENT]
            ),
        )
        .order_by(Application.created_at.desc())
        .limit(1)
    )
    event_id = uuid.uuid4()
    event_payload = (
        {"redecision_status": "SKIPPED", "reason": "NO_ACTIVE_APPLICATION"}
        if active_application is None
        else {"redecision_status": "QUEUED"}
    )
    hashed_counterparty = counterparty_hash(
        await tenant_salt(session, context.tenant_id), payload.counterparty
    )
    event_values: dict[str, object] = {
        "id": event_id,
        "tenant_id": context.tenant_id,
        "applicant_id": applicant.id,
        "source_connection_id": connection.id,
        "source_snapshot_id": None,
        "event_type": EvidenceEventType.TRANSACTION,
        "direction": payload.direction,
        "amount_paise": payload.amount_paise,
        "balance_paise": None,
        "currency": "INR",
        "description": payload.description,
        "counterparty_hash": hashed_counterparty,
        "external_id": payload.external_id,
        "occurred_at": payload.occurred_at,
        "received_at": now,
        "idempotency_key": key,
        "payload": event_payload,
    }
    classified = await classify_for_ingest(
        session,
        [
            TxnEvent(
                event_id=event_id,
                occurred_at=payload.occurred_at,
                direction=payload.direction,
                amount_paise=payload.amount_paise,
                balance_paise=None,
                description=payload.description,
                counterparty_hash=hashed_counterparty,
                source_connection_id=connection.id,
            )
        ],
    )
    trace = classified.events[0]
    event_values.update(
        {
            "normalized_narration": trace.normalized_narration
            or (
                normalize_narration(payload.description)
                if trace.classification_method.value == "UNCLASSIFIED"
                else None
            ),
            "classification_method": trace.classification_method,
            "category": trace.category.value,
            "classifier_version": classified.classifier_version,
            "catalog_version_id": trace.catalog_version_id,
            "match_similarity": trace.match_similarity,
            "matched_entry_id": trace.matched_entry_id,
            "payload": event_payload,
        }
    )
    inserted_id = await session.scalar(
        pg_insert(LedgerEvent)
        .values(**event_values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "idempotency_key"])
        .returning(LedgerEvent.id)
    )
    if inserted_id is None:
        existing = await session.scalar(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == context.tenant_id, LedgerEvent.idempotency_key == key
            )
        )
        assert existing is not None
        return EventIngestionResult(
            existing,
            await _job_for_event(session, context.tenant_id, existing.id),
            True,
            "DUPLICATE",
        )
    event = await session.get(LedgerEvent, inserted_id)
    assert event is not None
    if active_application is None:
        await session.commit()
        return EventIngestionResult(event, None, False, "SKIPPED", "NO_ACTIVE_APPLICATION")

    # Serialize only the per-application coalescing section. The database unique
    # index remains a backstop, while this lock ensures every concurrent event is
    # preserved and merged into the single pending job.
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(str(active_application.id))))
    )
    job = await session.scalar(
        select(Job)
        .where(
            Job.tenant_id == context.tenant_id,
            Job.job_type == JobType.REDECISION,
            Job.status == JobStatus.PENDING,
            Job.payload["application_id"].as_string() == str(active_application.id),
        )
        .order_by(Job.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if job is not None:
        merged = dict(job.payload)
        merged["event_ids"] = [*list(merged.get("event_ids", [])), str(event.id)]
        merged["as_of"] = now.isoformat()
        job.payload = merged
    else:
        job = await enqueue(
            session,
            tenant_id=context.tenant_id,
            handler="redecide",
            job_type=JobType.REDECISION,
            payload={
                "application_id": str(active_application.id),
                "applicant_id": str(applicant.id),
                "event_ids": [str(event.id)],
                "as_of": now.isoformat(),
                "user_id": str(context.user_id),
            },
            run_after=now + timedelta(seconds=settings.redecision_debounce_seconds),
        )
    await session.commit()
    return EventIngestionResult(event, job, False, "QUEUED")
