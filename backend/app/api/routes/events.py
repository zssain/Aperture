"""Machine-to-machine real-time event endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_event_service
from app.core.context import RequestContext
from app.db.session import get_session
from app.schemas.event import EventCreate, EventIngestionOut
from app.services.events.service import ingest_event
from app.services.rate_limit import PostgresRateLimitExceededError, hit

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventIngestionOut, status_code=status.HTTP_202_ACCEPTED)
async def append_event(
    payload: EventCreate,
    request: Request,
    response: Response,
    context: RequestContext = Depends(require_event_service),
    session: AsyncSession = Depends(get_session),
) -> EventIngestionOut:
    try:
        authorization = request.headers.get("authorization", "service")
        await hit(session, tenant_id=context.tenant_id, bucket="events", principal=authorization)
    except PostgresRateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Event rate limit reached"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    result = await ingest_event(session, context, payload)
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return EventIngestionOut(
        event_id=result.event.id,
        job_id=result.job.id if result.job else None,
        status=result.status,
        reason=result.reason,
    )
