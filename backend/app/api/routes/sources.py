"""Source ingestion route (pull adapters, e.g. the mock Account Aggregator)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.source import SourceConnection
from app.schemas.source import FetchRequest, IngestionResultOut
from app.services.ingestion.service import ConsentError, ingest_source
from app.services.sources.base import FetchPeriod
from app.services.sources.mock_aa import MockAccountAggregatorAdapter

router = APIRouter(prefix="/sources", tags=["sources"])


async def _load_connection(
    session: AsyncSession, context: RequestContext, connection_id: uuid.UUID
) -> SourceConnection:
    connection = await session.get(SourceConnection, connection_id)
    if connection is None or connection.tenant_id != context.tenant_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Source connection not found"},
        )
    return connection


@router.post("/{connection_id}/ingest")
async def ingest(
    connection_id: uuid.UUID,
    payload: FetchRequest,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> IngestionResultOut:
    connection = await _load_connection(session, context, connection_id)
    adapter = MockAccountAggregatorAdapter(failure_mode=payload.failure_mode)
    period = FetchPeriod(start=payload.period_start, end=payload.period_end)
    try:
        result = await ingest_source(session, connection, adapter, period)
    except ConsentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return IngestionResultOut.from_result(result)
