"""Case-file endpoints: the assembled case, paginated evidence, and feature lineage.

The lineage endpoint is deliberately first-class: every number the analyst sees can be traced
to the exact events it was computed from, and the endpoint recomputes to prove it.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context
from app.core.context import RequestContext
from app.db.session import get_session
from app.schemas.case import CaseOut, EvidencePage, LineageOut
from app.services.cases.assembler import (
    CaseNotFoundError,
    assemble_case,
    get_lineage,
    list_evidence,
)

router = APIRouter(tags=["cases"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "CASE_NOT_FOUND", "message": "Case not found"},
    )


@router.get("/cases/{application_id}", response_model=CaseOut)
async def get_case(
    application_id: uuid.UUID,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> CaseOut:
    try:
        return await assemble_case(session, context.tenant_id, application_id)
    except CaseNotFoundError as exc:
        raise _not_found() from exc


@router.get("/cases/{application_id}/evidence", response_model=EvidencePage)
async def get_evidence(
    application_id: uuid.UUID,
    category: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> EvidencePage:
    try:
        return await list_evidence(
            session,
            context.tenant_id,
            application_id,
            category=category,
            from_ts=from_ts,
            to_ts=to_ts,
            cursor=cursor,
            limit=limit,
        )
    except CaseNotFoundError as exc:
        raise _not_found() from exc


@router.get("/features/{snapshot_id}/{feature_key}/lineage", response_model=LineageOut)
async def get_feature_lineage(
    snapshot_id: uuid.UUID,
    feature_key: str,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> LineageOut:
    try:
        return await get_lineage(session, context.tenant_id, snapshot_id, feature_key)
    except CaseNotFoundError as exc:
        raise _not_found() from exc
