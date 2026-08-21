"""Explicitly feature-gated non-production demo helpers."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_writer
from app.core.config import settings
from app.core.context import RequestContext
from app.db.session import get_session
from app.schemas.event import DemoEventResultOut, DemoIncomeConsistencyRequest
from app.services.demo.event_generator import income_consistency_sequence
from app.services.events.service import ingest_event

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post(
    "/events/income-consistency",
    response_model=DemoEventResultOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_income_consistency_demo(
    payload: DemoIncomeConsistencyRequest,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> DemoEventResultOut:
    if not settings.demo_events_enabled or settings.environment.lower() in {"production", "prod"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    event_ids = []
    job_id = None
    for event in income_consistency_sequence(
        payload.applicant_ref, source_type=payload.source_type
    ):
        result = await ingest_event(session, context, event)
        event_ids.append(result.event.id)
        if result.job is not None:
            job_id = result.job.id
    return DemoEventResultOut(
        applicant_ref=payload.applicant_ref, event_ids=event_ids, job_id=job_id
    )
