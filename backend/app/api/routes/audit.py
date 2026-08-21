"""Audit ledger routes.

- ``GET /audit/verify`` — verify the tenant's chain (auditor / policy owner).
- ``GET /audit/entries/{id}`` — read one entry, tenant-scoped; a cross-tenant id → 404.
- ``POST /audit/notes`` — append a manual audit note (writers only; auditor → 403),
  demonstrating an in-transaction ledger append.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context, require_role, require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.enums import UserRole
from app.services.audit.ledger import LedgerEntryRepository, append, verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    event_type: str
    subject_type: str | None
    subject_id: uuid.UUID | None
    payload_hash: str
    prev_hash: str
    created_at: datetime


class ChainVerificationOut(BaseModel):
    valid: bool
    broken_at_seq: int | None


class AuditNoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("/verify")
async def verify(
    context: RequestContext = Depends(require_role(UserRole.AUDITOR)),
    session: AsyncSession = Depends(get_session),
) -> ChainVerificationOut:
    result = await verify_chain(session, context.tenant_id)
    return ChainVerificationOut(**result)


@router.get("/entries/{entry_id}")
async def get_entry(
    entry_id: uuid.UUID,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> LedgerEntryOut:
    repo = LedgerEntryRepository(session, context.tenant_id)
    entry = await repo.get(entry_id)
    if entry is None:
        # Cross-tenant or unknown id are indistinguishable: 404, never 403.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Ledger entry not found"},
        )
    return LedgerEntryOut.model_validate(entry)


@router.post("/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: AuditNoteRequest,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> LedgerEntryOut:
    entry = await append(
        session,
        context,
        event_type="AUDIT_NOTE",
        subject_type="note",
        subject_id=None,
        payload={"text": payload.text},
    )
    await session.commit()
    return LedgerEntryOut.model_validate(entry)
