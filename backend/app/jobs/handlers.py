"""Registered job handlers. Each is idempotent, so an at-least-once redelivery is safe.

Registered: sync_source, decide, bulk_redecide, simulate_policy, verify_chain.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.jobs.redecide import handle_redecide
from app.jobs.runner import Handler, enqueue
from app.models.application import Application
from app.models.enums import ApplicationStatus, JobType
from app.models.job import Job
from app.models.ledger import LedgerEvent
from app.models.source import SourceConnection
from app.services.audit.ledger import verify_chain
from app.services.orchestrator.replay import replay
from app.services.orchestrator.service import SystemUnavailableError, decide
from app.services.sources.base import FetchPeriod
from app.services.sources.mock_aa import MockAccountAggregatorAdapter


def _uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def system_context(job: Job) -> RequestContext:
    """A minimal tenant-scoped context for background work; the acting user is carried on the
    payload when a decision needs an attributable actor."""
    payload = job.payload
    user_raw = payload.get("user_id")
    return RequestContext(
        user_id=_uuid(user_raw) if user_raw else uuid.UUID(int=0),
        tenant_id=job.tenant_id,
        role="CREDIT_ANALYST",
        email="system@aperture",
        session_id=uuid.uuid4(),
        approval_ceilings_paise={},
    )


async def handle_decide(session: AsyncSession, job: Job, context: RequestContext) -> dict[str, Any]:
    payload = job.payload
    result = await decide(
        session,
        context,
        application_id=_uuid(payload["application_id"]),
        as_of=datetime.fromisoformat(str(payload["as_of"])),
        idempotency_key=str(payload["idempotency_key"]),
    )
    return {"decision_id": str(result.decision.id), "created": result.created}


async def handle_bulk_redecide(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    payload = job.payload
    as_of = str(payload["as_of"])
    application_ids = list(payload["application_ids"])
    enqueued = 0
    for application_id in application_ids:
        await enqueue(
            session,
            tenant_id=context.tenant_id,
            handler="decide",
            job_type=JobType.DECISION,
            payload={
                "application_id": str(application_id),
                "as_of": as_of,
                # Deterministic key so re-running bulk_redecide creates no duplicate decisions.
                "idempotency_key": f"redecide:{application_id}:{as_of}",
                "user_id": str(context.user_id),
            },
        )
        enqueued += 1
    await session.commit()
    return {"enqueued": enqueued}


async def handle_simulate_policy(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    payload = job.payload
    result = await replay(
        session,
        tenant_id=context.tenant_id,
        decision_id=_uuid(payload["decision_id"]),
        policy_version_id=_uuid(payload["policy_version_id"])
        if payload.get("policy_version_id")
        else None,
    )
    return {
        "status": result.status,
        "recomputed_outcome": result.recomputed_outcome,
        "counterfactual": result.counterfactual,
    }


async def handle_verify_chain(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    verification = await verify_chain(session, context.tenant_id)
    return dict(verification)


async def handle_sync_source(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    payload = job.payload
    connection = await session.get(SourceConnection, _uuid(payload["connection_id"]))
    if connection is None or connection.tenant_id != context.tenant_id:
        return {"status": "NOT_FOUND"}
    from app.services.ingestion.service import ConsentError, ingest_source

    period = FetchPeriod(
        start=datetime.fromisoformat(str(payload["period_start"])),
        end=datetime.fromisoformat(str(payload["period_end"])),
    )
    try:
        result = await ingest_source(session, connection, MockAccountAggregatorAdapter(), period)
    except ConsentError:
        return {"status": "CONSENT_ERROR"}
    return {"status": result.status, "already_ingested": result.already_ingested}


def _progress(job: Job) -> dict[str, Any]:
    progress = dict(job.result or {})
    progress.setdefault("started_at", datetime.now(UTC).isoformat())
    progress.setdefault("stages", [])
    progress.setdefault("sources", [])
    return progress


async def _set_stage(
    session: AsyncSession,
    job: Job,
    key: str,
    stage_status: str,
    *,
    count: int | None = None,
    message: str | None = None,
) -> None:
    progress = _progress(job)
    stages: list[dict[str, Any]] = []
    for raw in list(progress["stages"]):
        stage = dict(raw)
        if stage.get("key") == key:
            stage["status"] = stage_status
            if count is not None:
                stage["count"] = count
            if message is not None:
                stage["message"] = message
            if stage_status == "running":
                stage.setdefault("started_at", datetime.now(UTC).isoformat())
            if stage_status in {"complete", "failed"}:
                stage["finished_at"] = datetime.now(UTC).isoformat()
        stages.append(stage)
    progress["stages"] = stages
    job.result = progress
    await session.commit()


async def _event_count(session: AsyncSession, job: Job, applicant_id: uuid.UUID) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(LedgerEvent)
        .where(
            LedgerEvent.tenant_id == job.tenant_id,
            LedgerEvent.applicant_id == applicant_id,
        )
    )
    return int(value or 0)


async def handle_ingest_pipeline(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    """Fetch all selected sources, preserve partial failures, then invoke ``decide``.

    Progress is committed between stages so polling clients can see useful state while
    the worker continues independently of any browser tab.
    """
    payload = job.payload
    application_id = _uuid(payload["application_id"])
    applicant_id = _uuid(payload["applicant_id"])
    failure_modes = dict(payload.get("failure_modes", {}))
    connection_ids = [_uuid(value) for value in list(payload.get("connection_ids", []))]
    as_of = datetime.fromisoformat(str(payload["as_of"]))

    sources: list[dict[str, Any]] = []
    total_ingested = 0
    total_deduplicated = 0
    unavailable = 0

    if connection_ids:
        await _set_stage(session, job, "fetching", "running")
        period = FetchPeriod(start=as_of - timedelta(days=210), end=as_of)
        for connection_id in connection_ids:
            connection = await session.get(SourceConnection, connection_id)
            if connection is None or connection.tenant_id != context.tenant_id:
                sources.append(
                    {
                        "connection_id": str(connection_id),
                        "status": "FAILED",
                        "message": "Source connection not found.",
                    }
                )
                unavailable += 1
                continue
            mode_raw = failure_modes.get(connection.source_type.value)
            failure_mode = str(mode_raw) if mode_raw is not None else None
            from app.services.ingestion.service import ConsentError, ingest_source

            try:
                ingestion_result = await ingest_source(
                    session,
                    connection,
                    MockAccountAggregatorAdapter(failure_mode=failure_mode),
                    period,
                )
            except ConsentError as exc:
                sources.append(
                    {
                        "connection_id": str(connection.id),
                        "source_type": connection.source_type.value,
                        "status": "FAILED",
                        "message": exc.message,
                    }
                )
                unavailable += 1
                continue
            total_ingested += ingestion_result.ingested
            total_deduplicated += ingestion_result.deduplicated
            if ingestion_result.status in {"UNAVAILABLE", "FAILED"}:
                unavailable += 1
            sources.append(
                {
                    "connection_id": str(connection.id),
                    "source_type": connection.source_type.value,
                    "status": ingestion_result.status,
                    "ingested": ingestion_result.ingested,
                    "deduplicated": ingestion_result.deduplicated,
                    "message": (
                        "Provider unavailable - retry this source."
                        if ingestion_result.status == "UNAVAILABLE"
                        else "Provider failed - retry this source."
                        if ingestion_result.status == "FAILED"
                        else None
                    ),
                }
            )
            progress = _progress(job)
            progress["sources"] = sources
            job.result = progress
            await session.commit()

        if unavailable:
            await _set_stage(
                session,
                job,
                "fetching",
                "failed",
                count=len(connection_ids) - unavailable,
                message=(
                    f"{unavailable} source unavailable; completed sources will still be assessed."
                ),
            )
        else:
            await _set_stage(session, job, "fetching", "complete", count=len(connection_ids))
        await _set_stage(session, job, "normalising", "running")
        await _set_stage(
            session,
            job,
            "normalising",
            "complete",
            count=total_ingested,
            message=f"{total_deduplicated} duplicate rows skipped.",
        )

    evidence_count = await _event_count(session, job, applicant_id)
    if evidence_count == 0:
        application = await session.get(Application, application_id)
        if application is not None and application.tenant_id == context.tenant_id:
            application.status = ApplicationStatus.OPEN
        await _set_stage(
            session,
            job,
            "normalising",
            "failed",
            count=0,
            message="No usable evidence was found. The case was created but not decided.",
        )
        progress = _progress(job)
        progress.update(
            {
                "application_id": str(application_id),
                "outcome": "ZERO_USABLE_EVIDENCE",
                "retryable_stage": "fetching" if connection_ids else None,
            }
        )
        job.result = progress
        await session.commit()
        return progress

    await _set_stage(session, job, "features", "running")
    await _set_stage(session, job, "assessing", "running")
    try:
        decision_result = await decide(
            session,
            context,
            application_id=application_id,
            as_of=as_of,
            idempotency_key=str(payload["idempotency_key"]),
        )
    except SystemUnavailableError as exc:
        application = await session.get(Application, application_id)
        if application is not None and application.tenant_id == context.tenant_id:
            application.status = ApplicationStatus.REFERRED
        await _set_stage(session, job, "features", "complete", count=evidence_count)
        await _set_stage(
            session,
            job,
            "assessing",
            "failed",
            message=f"{exc.which} assessment is unavailable. Retry this stage.",
        )
        progress = _progress(job)
        progress.update(
            {
                "application_id": str(application_id),
                "outcome": "SYSTEM_UNAVAILABLE",
                "retryable_stage": "assessing",
            }
        )
        job.result = progress
        await session.commit()
        return progress
    except Exception:
        await _set_stage(
            session,
            job,
            "assessing",
            "failed",
            message="The assessment pipeline failed unexpectedly. Retry this stage.",
        )
        progress = _progress(job)
        progress["retryable_stage"] = "assessing"
        job.result = progress
        await session.commit()
        raise

    await _set_stage(session, job, "features", "complete", count=evidence_count)
    await _set_stage(session, job, "assessing", "complete", count=4)
    await _set_stage(session, job, "decided", "complete", count=1)
    application = await session.get(Application, application_id)
    if application is not None and application.tenant_id == context.tenant_id:
        application.status = (
            ApplicationStatus.REFERRED
            if decision_result.decision.routing == "HUMAN"
            else ApplicationStatus.DECIDED
        )
    progress = _progress(job)
    progress.update(
        {
            "application_id": str(application_id),
            "decision_id": str(decision_result.decision.id),
            "outcome": decision_result.policy_decision.outcome,
            "retryable_stage": "fetching" if unavailable else None,
        }
    )
    job.result = progress
    await session.commit()
    return progress


HANDLERS: dict[str, Handler] = {
    "decide": handle_decide,
    "bulk_redecide": handle_bulk_redecide,
    "simulate_policy": handle_simulate_policy,
    "verify_chain": handle_verify_chain,
    "sync_source": handle_sync_source,
    "ingest_pipeline": handle_ingest_pipeline,
    "redecide": handle_redecide,
}

# Imports are deliberately late: these handlers reuse the runner types and small helpers
# defined in this module without creating an import cycle during module initialisation.
from app.jobs.bulk_redecide import handle_bulk_redecide_chunked  # noqa: E402
from app.jobs.retention import handle_retention_purge  # noqa: E402
from app.jobs.simulate import handle_simulate  # noqa: E402

HANDLERS.update(
    {
        "simulate_policy_book": handle_simulate,
        "bulk_redecide_chunked": handle_bulk_redecide_chunked,
        "purge_retention": handle_retention_purge,
    }
)
