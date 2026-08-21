"""Decision + replay routes.

- ``POST /applications/{id}/decide`` runs the orchestrator; a failed assessment returns 503
  with ``SYSTEM_UNAVAILABLE`` and no decision is persisted.
- ``POST /decisions/{id}/replay`` re-runs the decision over its stored snapshot (optionally
  under a different policy version for a counterfactual).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context, require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.decision import Decision, DecisionReason, RecourseOption
from app.schemas.decision import (
    DecideRequest,
    DecisionOut,
    ReasonOut,
    RecourseOptionOut,
    RecourseOut,
    ReplayOut,
    ReplayRequest,
)
from app.services.orchestrator.replay import replay as replay_decision
from app.services.orchestrator.service import (
    ApplicationNotFoundError,
    DecisionResult,
    SystemUnavailableError,
    _rehydrate,
    decide,
)
from app.services.rate_limit import PostgresRateLimitExceededError, hit_many

router = APIRouter(tags=["decisions"])


async def _serialize(session: AsyncSession, result: DecisionResult) -> DecisionOut:
    decision = result.decision
    reasons = list(
        await session.scalars(
            select(DecisionReason)
            .where(DecisionReason.decision_id == decision.id)
            .order_by(DecisionReason.created_at.asc())
        )
    )
    reason_out = [
        ReasonOut(
            code=r.code,
            polarity=str((r.detail or {}).get("polarity", "NEUTRAL")),
            template_params=dict((r.detail or {}).get("template_params", {})),
        )
        for r in sorted(reasons, key=lambda r: int((r.detail or {}).get("order", 0)))
    ]

    recourse_out: RecourseOut | None = None
    if result.recourse is not None:
        rows = list(
            await session.scalars(
                select(RecourseOption)
                .where(RecourseOption.decision_id == decision.id)
                .order_by(RecourseOption.rank.asc())
            )
        )
        recourse_out = RecourseOut(
            options=[
                RecourseOptionOut(
                    lever=str(row.required_change.get("lever", "")),
                    target=str(row.required_change.get("target", "")),
                    params=dict(row.required_change.get("params", {})),
                    projected_action=row.projected_action.value if row.projected_action else None,
                    projected_limit_paise=row.projected_limit_paise,
                    projected_delta=dict(row.required_change.get("projected_delta", {})),
                    expires_at=row.required_change.get("expires_at"),
                    rank=row.rank,
                )
                for row in rows
            ],
            no_viable_recourse=result.recourse.no_viable_recourse,
            timed_out=result.recourse.timed_out,
        )

    return DecisionOut(
        id=decision.id,
        application_id=decision.application_id,
        applicant_id=decision.applicant_id,
        action=decision.action.value,
        routing=decision.routing,
        outcome=result.policy_decision.outcome,
        approved_limit_paise=decision.approved_limit_paise,
        terms=dict(decision.terms or {}),
        fired_rules=list(decision.fired_rules or []),
        exploration_cohort=decision.exploration_cohort,
        is_final=decision.is_final,
        superseded_by=decision.superseded_by,
        reasons=reason_out,
        recourse=recourse_out,
        created=result.created,
    )


@router.post("/applications/{application_id}/decide", response_model=DecisionOut)
async def decide_application(
    application_id: uuid.UUID,
    payload: DecideRequest,
    request: Request,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> DecisionOut:
    try:
        await hit_many(
            session,
            tenant_id=context.tenant_id,
            bucket="decide",
            principals=(
                f"user:{context.user_id}",
                f"ip:{request.client.host if request.client else 'unknown'}",
            ),
        )
    except PostgresRateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Decision rate limit reached"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    as_of = payload.as_of or datetime.now(UTC)
    try:
        result = await decide(
            session,
            context,
            application_id=application_id,
            as_of=as_of,
            idempotency_key=payload.idempotency_key,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    except SystemUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SYSTEM_UNAVAILABLE", "which": exc.which},
        ) from exc
    return await _serialize(session, result)


@router.get("/decisions/{decision_id}", response_model=DecisionOut)
async def get_decision(
    decision_id: uuid.UUID,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> DecisionOut:
    decision = await session.get(Decision, decision_id)
    if decision is None or decision.tenant_id != context.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    return await _serialize(
        session,
        DecisionResult(
            decision=decision,
            policy_decision=_rehydrate(decision),
            created=False,
        ),
    )


@router.get("/applications/{application_id}/decisions", response_model=list[DecisionOut])
async def decision_history(
    application_id: uuid.UUID,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> list[DecisionOut]:
    rows = list(
        await session.scalars(
            select(Decision)
            .where(
                Decision.tenant_id == context.tenant_id,
                Decision.application_id == application_id,
            )
            .order_by(Decision.decided_at.desc())
        )
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    return [
        await _serialize(
            session,
            DecisionResult(
                decision=row,
                policy_decision=_rehydrate(row),
                created=False,
            ),
        )
        for row in rows
    ]


@router.post("/decisions/{decision_id}/replay", response_model=ReplayOut)
async def replay_route(
    decision_id: uuid.UUID,
    payload: ReplayRequest,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> ReplayOut:
    result = await replay_decision(
        session,
        tenant_id=context.tenant_id,
        decision_id=decision_id,
        policy_version_id=payload.policy_version_id,
    )
    return ReplayOut(
        status=result.status,
        diff=result.diff,
        recomputed_outcome=result.recomputed_outcome,
        recomputed_action=result.recomputed_action,
        stored_action=result.stored_action,
        policy_version_id=result.policy_version_id,
        counterfactual=result.counterfactual,
        reused_risk=result.reused_risk,
    )
