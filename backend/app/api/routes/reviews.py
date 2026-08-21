"""Human-review endpoint + the decision's audit timeline.

The reason contract is enforced at the schema boundary: an override without a reason code, or with
free text under 20 characters, is a 422 the client cannot bypass.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context, require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.audit import LedgerEntry
from app.models.enums import ReviewOutcome
from app.models.user import User
from app.services.reviews.service import (
    AlreadyFinalError,
    DecisionNotFoundError,
    InsufficientAuthorityError,
    RoleNotPermittedError,
    submit_review,
)

router = APIRouter(tags=["reviews"])

_MIN_REASON_LEN = 20
_VALID_OVERRIDE_OUTCOMES = {o.value for o in ReviewOutcome}


class ReviewRequest(BaseModel):
    action: Literal["confirm", "override", "request_evidence"]
    reason_code: str | None = None
    reason_text: str | None = None
    override_outcome: str | None = None
    language: str = "en"

    @model_validator(mode="after")
    def _enforce_reason_on_divergence(self) -> "ReviewRequest":
        # An override diverges from the recommendation, so it must be explained (invariant 10).
        if self.action == "override":
            if not self.reason_code:
                raise ValueError("reason_code is required for an override")
            if not self.reason_text or len(self.reason_text.strip()) < _MIN_REASON_LEN:
                raise ValueError(
                    f"reason_text must be at least {_MIN_REASON_LEN} characters for an override"
                )
            if self.override_outcome not in _VALID_OVERRIDE_OUTCOMES:
                raise ValueError("override_outcome must be a valid review outcome")
        return self


class NoticeOut(BaseModel):
    subject: str
    body: str
    language: str


class ReviewResponse(BaseModel):
    review_id: uuid.UUID
    status: str
    resulting_outcome: str
    recommendation_outcome: str
    diverged: bool
    notice: NoticeOut


class LedgerItemOut(BaseModel):
    seq: int
    event_type: str
    actor_id: uuid.UUID | None
    actor_email: str | None
    payload: dict[str, Any]
    payload_hash: str
    prev_hash: str
    created_at: datetime


@router.post("/decisions/{decision_id}/review", response_model=ReviewResponse)
async def review_decision(
    decision_id: uuid.UUID,
    payload: ReviewRequest,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> ReviewResponse:
    try:
        result = await submit_review(
            session,
            context,
            decision_id=decision_id,
            action=payload.action,
            reason_code=payload.reason_code,
            reason_text=payload.reason_text,
            override_outcome=payload.override_outcome,
            language=payload.language,
        )
    except DecisionNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "Decision not found"}
        ) from exc
    except RoleNotPermittedError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN_ROLE", "message": f"Requires {exc.required_role}"},
        ) from exc
    except InsufficientAuthorityError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "INSUFFICIENT_AUTHORITY", "message": "Amount exceeds your authority"},
        ) from exc
    except AlreadyFinalError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_FINAL",
                "message": "This decision was already finalised",
                "winning_outcome": exc.winning_outcome,
            },
        ) from exc

    return ReviewResponse(
        review_id=result.review.id,
        status="final",
        resulting_outcome=result.resulting_outcome,
        recommendation_outcome=result.recommendation_outcome,
        diverged=result.diverged,
        notice=NoticeOut(
            subject=result.notice.subject, body=result.notice.body, language=result.notice.language
        ),
    )


@router.get("/decisions/{decision_id}/ledger", response_model=list[LedgerItemOut])
async def decision_ledger(
    decision_id: uuid.UUID,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> list[LedgerItemOut]:
    stmt = (
        select(LedgerEntry, User.email)
        .outerjoin(User, User.id == LedgerEntry.actor_id)
        .where(
            LedgerEntry.tenant_id == context.tenant_id,
            LedgerEntry.subject_id == decision_id,
        )
        .order_by(LedgerEntry.seq.asc())
    )
    rows = await session.execute(stmt)
    return [
        LedgerItemOut(
            seq=entry.seq,
            event_type=entry.event_type,
            actor_id=entry.actor_id,
            actor_email=email,
            payload=dict(entry.payload or {}),
            payload_hash=entry.payload_hash,
            prev_hash=entry.prev_hash,
            created_at=entry.created_at,
        )
        for entry, email in rows
    ]
