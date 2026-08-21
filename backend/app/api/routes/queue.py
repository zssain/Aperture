"""The exception-queue endpoint.

``GET /queue`` is the interface to the residue of automated decisions. Filtering, sorting and
pagination all happen server-side; the response carries counts for every view the role can see
and omits any view it cannot. A view the role may not access is a 403, not a hidden tab.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context
from app.core.context import RequestContext
from app.db.session import get_session
from app.schemas.queue import QueueResponse
from app.services.queue.service import QueueAccessError, list_queue

router = APIRouter(tags=["queue"])


@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    view: str | None = Query(default=None),
    q: str | None = Query(default=None),
    band: str | None = Query(default=None),
    coverage_min: int | None = Query(default=None),
    coverage_max: int | None = Query(default=None),
    amount_min: int | None = Query(default=None),
    amount_max: int | None = Query(default=None),
    waiting_gt: int | None = Query(default=None),
    sort: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> QueueResponse:
    try:
        return await list_queue(
            session,
            context.tenant_id,
            context.role,
            view=view,
            q=q,
            band=band,
            coverage_min=coverage_min,
            coverage_max=coverage_max,
            amount_min=amount_min,
            amount_max=amount_max,
            waiting_gt=waiting_gt,
            sort=sort,
            cursor=cursor,
            limit=limit,
        )
    except QueueAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN_VIEW", "message": "View not available for your role"},
        ) from exc
