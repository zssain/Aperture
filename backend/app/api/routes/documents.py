"""Document upload route (CSV / PDF statements)."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.source import SourceConnection
from app.schemas.source import IngestionResultOut
from app.services.ingestion.service import ConsentError, ingest_document
from app.services.rate_limit import PostgresRateLimitExceededError, hit_many
from app.services.sources.document import (
    DocumentTooLargeError,
    RowCapExceededError,
    SchemaError,
    UnsupportedDocumentError,
)

router = APIRouter(prefix="/sources", tags=["documents"])


@router.post("/{connection_id}/documents")
async def upload_document(
    connection_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> IngestionResultOut:
    try:
        await hit_many(
            session,
            tenant_id=context.tenant_id,
            bucket="upload",
            principals=(
                f"user:{context.user_id}",
                f"ip:{request.client.host if request.client else 'unknown'}",
            ),
        )
    except PostgresRateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Upload rate limit reached"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    connection = await session.get(SourceConnection, connection_id)
    if connection is None or connection.tenant_id != context.tenant_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Source connection not found"},
        )

    data = await file.read()
    try:
        result = await ingest_document(session, connection, data, file.filename or "upload")
    except ConsentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except RowCapExceededError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "ROW_CAP_EXCEEDED", "message": str(exc), "limit": exc.limit},
        ) from exc
    except SchemaError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "SCHEMA_ERROR",
                "message": str(exc),
                "expected_columns": exc.expected_columns,
            },
        ) from exc
    except DocumentTooLargeError as exc:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "FILE_TOO_LARGE", "message": str(exc)},
        ) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "UNSUPPORTED", "message": str(exc)},
        ) from exc
    return IngestionResultOut.from_result(result)
