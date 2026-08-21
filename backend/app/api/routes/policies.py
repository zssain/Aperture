"""Policy Studio API: draft, validate, simulate, and safely publish."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import settings
from app.core.context import RequestContext
from app.db.session import get_session
from app.jobs.runner import enqueue
from app.models.enums import JobStatus, JobType, PolicyStatus, UserRole
from app.models.job import Job
from app.models.policy import PolicyVersion
from app.models.user import User
from app.services.audit.ledger import append
from app.services.policy.schema import PolicyRules
from app.services.policy.simulation import policy_hash
from app.services.policy.validator import validate
from app.services.rate_limit import PostgresRateLimitExceededError, hit_many

router = APIRouter(prefix="/policies", tags=["policies"])
owner = require_role(UserRole.CREDIT_POLICY_OWNER)


class PolicyPatch(BaseModel):
    rules: dict[str, Any]


class PublishRequest(BaseModel):
    simulation_job_id: uuid.UUID
    change_note: str = Field(min_length=20, max_length=2000)
    bulk_redecide: bool = False


def _validation(rules: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = PolicyRules(**rules)
    except Exception as exc:
        return {"ok": False, "errors": [str(exc)]}
    result = validate(parsed)
    return {"ok": result.ok, "errors": list(result.errors)}


def _serialize(row: PolicyVersion, author: User | None = None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "version": row.version,
        "status": row.status.value,
        "rules": row.rules,
        "author": author.full_name if author else None,
        "change_note": row.notes,
        "published_at": row.published_at,
        "created_at": row.created_at,
        "draft_hash": policy_hash(row.rules),
        "validation": _validation(row.rules),
    }


async def _policy(
    session: AsyncSession, context: RequestContext, policy_id: uuid.UUID
) -> PolicyVersion:
    row = await session.get(PolicyVersion, policy_id)
    if row is None or row.tenant_id != context.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    return row


@router.get("")
async def list_policies(
    context: RequestContext = Depends(owner),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(PolicyVersion)
            .where(PolicyVersion.tenant_id == context.tenant_id)
            .order_by(PolicyVersion.version.desc())
        )
    )
    authors = {
        user.id: user
        for user in await session.scalars(
            select(User).where(User.id.in_([row.created_by for row in rows if row.created_by]))
        )
    }
    return [
        _serialize(row, authors.get(row.created_by) if row.created_by else None) for row in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_draft(
    context: RequestContext = Depends(owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    live = await session.scalar(
        select(PolicyVersion).where(
            PolicyVersion.tenant_id == context.tenant_id,
            PolicyVersion.status == PolicyStatus.LIVE,
        )
    )
    if live is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No live policy to copy")
    existing = await session.scalar(
        select(PolicyVersion).where(
            PolicyVersion.tenant_id == context.tenant_id,
            PolicyVersion.status == PolicyStatus.DRAFT,
        )
    )
    if existing:
        return _serialize(existing, await session.get(User, existing.created_by))
    next_version = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(PolicyVersion.version), 0)).where(
                    PolicyVersion.tenant_id == context.tenant_id
                )
            )
            or 0
        )
        + 1
    )
    rules = dict(live.rules)
    rules["policy_version"] = f"policy-v{next_version}"
    draft = PolicyVersion(
        tenant_id=context.tenant_id,
        version=next_version,
        status=PolicyStatus.DRAFT,
        rules=rules,
        created_by=context.user_id,
    )
    session.add(draft)
    await session.commit()
    return _serialize(draft, await session.get(User, context.user_id))


@router.patch("/{policy_id}")
async def update_draft(
    policy_id: uuid.UUID,
    payload: PolicyPatch,
    context: RequestContext = Depends(owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await _policy(session, context, policy_id)
    if row.status != PolicyStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "LIVE_POLICY_IMMUTABLE", "message": "A live policy cannot be edited."},
        )
    validation = _validation(payload.rules)
    row.rules = payload.rules
    await session.commit()
    result = _serialize(row, await session.get(User, row.created_by))
    result["validation"] = validation
    return result


@router.post("/{policy_id}/simulate", status_code=status.HTTP_202_ACCEPTED)
async def start_simulation(
    policy_id: uuid.UUID,
    request: Request,
    context: RequestContext = Depends(owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        await hit_many(
            session,
            tenant_id=context.tenant_id,
            bucket="policy_simulate",
            principals=(
                f"user:{context.user_id}",
                f"ip:{request.client.host if request.client else 'unknown'}",
            ),
        )
    except PostgresRateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Policy simulation rate limit reached"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    row = await _policy(session, context, policy_id)
    if row.status != PolicyStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Only drafts can be simulated")
    validation = _validation(row.rules)
    if not validation["ok"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=validation)
    from app.models.feature import FeatureSnapshot

    count = int(
        await session.scalar(
            select(func.count())
            .select_from(FeatureSnapshot)
            .where(FeatureSnapshot.tenant_id == context.tenant_id)
        )
        or 0
    )
    minimum = settings.policy_simulation_minimum_snapshots
    if count < minimum:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "INSUFFICIENT_SIMULATION_COHORT",
                "message": (
                    f"Simulation requires at least {minimum} stored snapshots; {count} exist."
                ),
                "minimum_n": minimum,
                "n": count,
            },
        )
    job = await enqueue(
        session,
        tenant_id=context.tenant_id,
        handler="simulate_policy_book",
        job_type=JobType.DECISION,
        payload={"policy_version_id": str(row.id), "draft_hash": policy_hash(row.rules)},
    )
    await session.commit()
    return {"job_id": str(job.id), "status": job.status.value, "draft_hash": policy_hash(row.rules)}


@router.get("/{policy_id}/simulation/{job_id}")
async def get_simulation(
    policy_id: uuid.UUID,
    job_id: uuid.UUID,
    context: RequestContext = Depends(owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _policy(session, context, policy_id)
    job = await session.get(Job, job_id)
    if (
        job is None
        or job.tenant_id != context.tenant_id
        or job.payload.get("policy_version_id") != str(policy_id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "error": job.error,
        **(job.result or {}),
    }


@router.post("/{policy_id}/publish")
async def publish(
    policy_id: uuid.UUID,
    payload: PublishRequest,
    context: RequestContext = Depends(owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    draft = await _policy(session, context, policy_id)
    await session.refresh(draft, with_for_update=True)
    if draft.status != PolicyStatus.DRAFT:
        winner = await session.scalar(
            select(PolicyVersion).where(
                PolicyVersion.tenant_id == context.tenant_id,
                PolicyVersion.status == PolicyStatus.LIVE,
            )
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Policy v{winner.version if winner else 'unknown'} already won publication.",
        )
    job = await session.get(Job, payload.simulation_job_id)
    if (
        job is None
        or job.tenant_id != context.tenant_id
        or job.status != JobStatus.SUCCEEDED
        or job.payload.get("policy_version_id") != str(draft.id)
        or (job.result or {}).get("draft_hash") != policy_hash(draft.rules)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "SIMULATION_REQUIRED",
                "message": "Run a completed simulation for the current draft before publishing.",
            },
        )
    validation = _validation(draft.rules)
    if not validation["ok"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=validation)
    try:
        current = await session.scalar(
            select(PolicyVersion)
            .where(
                PolicyVersion.tenant_id == context.tenant_id,
                PolicyVersion.status == PolicyStatus.LIVE,
            )
            .with_for_update()
        )
        if current:
            current.status = PolicyStatus.ARCHIVED
        draft.status = PolicyStatus.LIVE
        draft.notes = payload.change_note
        draft.published_at = datetime.now(UTC)
        await append(
            session,
            context,
            "POLICY_PUBLISHED",
            "policy_version",
            draft.id,
            {
                "version": draft.version,
                "change_note": payload.change_note,
                "simulation_job_id": str(job.id),
            },
        )
        bulk_job = None
        if payload.bulk_redecide:
            bulk_job = await enqueue(
                session,
                tenant_id=context.tenant_id,
                handler="bulk_redecide_chunked",
                job_type=JobType.REDECISION,
                payload={"policy_id": str(draft.id), "user_id": str(context.user_id), "offset": 0},
            )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        winner = await session.scalar(
            select(PolicyVersion).where(
                PolicyVersion.tenant_id == context.tenant_id,
                PolicyVersion.status == PolicyStatus.LIVE,
            )
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Policy v{winner.version if winner else 'unknown'} already won publication.",
        ) from exc
    return {
        "policy": _serialize(draft, await session.get(User, draft.created_by)),
        "bulk_job_id": str(bulk_job.id) if bulk_job else None,
    }
