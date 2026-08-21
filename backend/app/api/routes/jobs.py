"""Job status route: ``GET /jobs/{id}`` (tenant-scoped)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context, require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.jobs.runner import enqueue
from app.models.enums import JobType
from app.models.job import Job
from app.schemas.decision import JobOut, RetryJobRequest

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _serialize(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        result=job.result,
        error=job.error,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> JobOut:
    job = await session.get(Job, job_id)
    # Cross-tenant reads are a 404, never a 403 (invariant 9).
    if job is None or job.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return _serialize(job)


def _retry_progress(job: Job) -> dict[str, Any]:
    prior = dict(job.result or {})
    stages: list[dict[str, Any]] = []
    for raw in list(prior.get("stages", [])):
        stage = dict(raw)
        if stage.get("key") != "consent":
            stage = {"key": stage.get("key"), "label": stage.get("label"), "status": "pending"}
        stages.append(stage)
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "stages": stages,
        "sources": [],
        "retry_of": str(job.id),
    }


@router.post("/{job_id}/retry", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def retry_job(
    job_id: uuid.UUID,
    payload: RetryJobRequest,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> JobOut:
    job = await session.get(Job, job_id)
    if job is None or job.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if job.job_type is not JobType.INGEST or payload.stage not in {"fetching", "assessing"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "STAGE_NOT_RETRYABLE", "message": "This stage cannot be retried."},
        )

    next_payload = dict(job.payload)
    next_payload["as_of"] = datetime.now(UTC).isoformat()
    original_key = job.payload.get("idempotency_key", "intake")
    next_payload["idempotency_key"] = f"{original_key}:retry:{uuid.uuid4()}"
    next_payload["user_id"] = str(context.user_id)
    if payload.stage == "fetching":
        failed_ids = {
            str(source.get("connection_id"))
            for source in list((job.result or {}).get("sources", []))
            if source.get("status") in {"UNAVAILABLE", "FAILED"}
        }
        next_payload["connection_ids"] = [
            value
            for value in list(job.payload.get("connection_ids", []))
            if str(value) in failed_ids
        ]
        next_payload["failure_modes"] = {}
    else:
        next_payload["connection_ids"] = []
        next_payload["failure_modes"] = {}

    retried = await enqueue(
        session,
        tenant_id=context.tenant_id,
        handler="ingest_pipeline",
        job_type=JobType.INGEST,
        payload=next_payload,
    )
    retried.result = _retry_progress(job)
    await session.commit()
    return _serialize(retried)
