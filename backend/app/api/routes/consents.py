"""Consent routes: grant (with connection registration) and revoke."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.schemas.consent import (
    ConsentCreatedResponse,
    ConsentCreateRequest,
    ConsentOut,
    SourceConnectionOut,
)
from app.services.consent.service import (
    ConsentNotFoundError,
    create_consent,
    revoke_consent,
)

router = APIRouter(tags=["consents"])


@router.post("/applicants/{applicant_id}/consents", status_code=status.HTTP_201_CREATED)
async def grant_consent(
    applicant_id: uuid.UUID,
    payload: ConsentCreateRequest,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> ConsentCreatedResponse:
    try:
        consent, connections = await create_consent(
            session,
            context,
            applicant_id=applicant_id,
            purpose=payload.purpose,
            scope=payload.scope,
            expires_at=payload.expires_at,
        )
    except ConsentNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Applicant not found"},
        ) from exc
    return ConsentCreatedResponse(
        consent=ConsentOut.model_validate(consent),
        connections=[SourceConnectionOut.model_validate(c) for c in connections],
    )


@router.post("/consents/{consent_id}/revoke")
async def revoke(
    consent_id: uuid.UUID,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> ConsentOut:
    try:
        consent = await revoke_consent(session, context, consent_id=consent_id)
    except ConsentNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Consent not found"},
        ) from exc
    return ConsentOut.model_validate(consent)
