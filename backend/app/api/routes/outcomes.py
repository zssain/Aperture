"""Idempotent outcome ingestion authenticated by the event service token."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_event_service
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.decision import Decision
from app.models.enums import OutcomeLabel
from app.models.outcome import Outcome

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


class OutcomeIn(BaseModel):
    decision_id: uuid.UUID
    outcome_type: OutcomeLabel
    observed_at: datetime
    amount_recovered_paise: int | None = Field(default=None, ge=0)


@router.post("", status_code=status.HTTP_201_CREATED)
async def ingest_outcome(
    payload: OutcomeIn,
    context: RequestContext = Depends(require_event_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    decision = await session.get(Decision, payload.decision_id)
    if decision is None or decision.tenant_id != context.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    existing = await session.scalar(
        select(Outcome).where(
            Outcome.tenant_id == context.tenant_id,
            Outcome.decision_id == decision.id,
            Outcome.label == payload.outcome_type,
            Outcome.observed_at == payload.observed_at,
        )
    )
    if existing:
        return {"id": str(existing.id), "created": False, "cohort": existing.detail or {}}
    row = Outcome(
        tenant_id=context.tenant_id,
        application_id=decision.application_id,
        decision_id=decision.id,
        applicant_id=decision.applicant_id,
        label=payload.outcome_type,
        observed_at=payload.observed_at,
        principal_paise=payload.amount_recovered_paise,
        detail={
            "exploration_cohort": decision.exploration_cohort,
            "performance_window_closed": True,
            "policy_version_id": str(decision.policy_version_id),
        },
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        winner = await session.scalar(
            select(Outcome).where(
                Outcome.tenant_id == context.tenant_id,
                Outcome.decision_id == decision.id,
                Outcome.label == payload.outcome_type,
                Outcome.observed_at == payload.observed_at,
            )
        )
        if winner is None:
            raise
        return {"id": str(winner.id), "created": False, "cohort": winner.detail or {}}
    return {"id": str(row.id), "created": True, "cohort": row.detail or {}}
