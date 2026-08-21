"""Recourse: preview the applicant notice, and send an evidence request.

The notice is template-rendered from the decision's reasons and recourse options. It states the
action, that it does not ensure approval, and the expiry - and never a threshold.
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context, require_writer
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.decision import Decision, DecisionReason, RecourseOption
from app.models.enums import NoticeStatus, NoticeType
from app.models.notice import Notice
from app.services.audit import ledger
from app.services.notices.llm_renderer import render_notice
from app.services.notices.renderer import render_recourse_notice
from app.services.rate_limit import PostgresRateLimitExceededError, hit_many

router = APIRouter(tags=["recourse"])


class NoticeOut(BaseModel):
    subject: str
    body: str
    language: str


class SendRequest(BaseModel):
    language: str = "en"


async def _load_decision(
    session: AsyncSession, tenant_id: uuid.UUID, decision_id: uuid.UUID
) -> Decision:
    decision = await session.get(Decision, decision_id)
    if decision is None or decision.tenant_id != tenant_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "Decision not found"}
        )
    return decision


async def _reasons(
    session: AsyncSession, tenant_id: uuid.UUID, decision_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(DecisionReason).where(
                DecisionReason.tenant_id == tenant_id,
                DecisionReason.decision_id == decision_id,
            )
        )
    )
    rows.sort(key=lambda r: int((r.detail or {}).get("order", 0)))
    return [{"code": r.code} for r in rows]


async def _recourse_options(
    session: AsyncSession, tenant_id: uuid.UUID, decision_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(RecourseOption)
            .where(
                RecourseOption.tenant_id == tenant_id,
                RecourseOption.decision_id == decision_id,
            )
            .order_by(RecourseOption.rank.asc())
        )
    )
    return [{"required_change": dict(r.required_change or {})} for r in rows]


@router.get("/decisions/{decision_id}/notice/preview", response_model=NoticeOut)
async def preview_notice(
    decision_id: uuid.UUID,
    kind: Literal["decision", "recourse"] = Query(default="decision"),
    language: str = Query(default="en"),
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> NoticeOut:
    decision = await _load_decision(session, context.tenant_id, decision_id)
    if kind == "recourse":
        options = await _recourse_options(session, context.tenant_id, decision_id)
        rendered = render_recourse_notice(options=options, language=language)
    else:
        reasons = await _reasons(session, context.tenant_id, decision_id)
        try:
            await hit_many(
                session,
                tenant_id=context.tenant_id,
                bucket="notice_render",
                principals=(f"tenant:{context.tenant_id}",),
            )
        except PostgresRateLimitExceededError as exc:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "RATE_LIMITED", "message": "Notice-render rate limit reached"},
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        rendered = await render_notice(
            outcome=_outcome(decision),
            terms=dict(decision.terms or {}),
            reasons=reasons,
            language=language,
        )
    return NoticeOut(subject=rendered.subject, body=rendered.body, language=rendered.language)


@router.post("/decisions/{decision_id}/recourse/send", response_model=NoticeOut)
async def send_recourse(
    decision_id: uuid.UUID,
    payload: SendRequest,
    request: Request,
    context: RequestContext = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> NoticeOut:
    try:
        await hit_many(
            session,
            tenant_id=context.tenant_id,
            bucket="recourse",
            principals=(
                f"user:{context.user_id}",
                f"ip:{request.client.host if request.client else 'unknown'}",
            ),
        )
    except PostgresRateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Recourse-send rate limit reached"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    decision = await _load_decision(session, context.tenant_id, decision_id)
    options = await _recourse_options(session, context.tenant_id, decision_id)
    rendered = render_recourse_notice(options=options, language=payload.language)

    session.add(
        Notice(
            tenant_id=context.tenant_id,
            application_id=decision.application_id,
            decision_id=decision.id,
            applicant_id=decision.applicant_id,
            notice_type=NoticeType.RECOURSE_REQUEST,
            language=rendered.language,
            subject=rendered.subject,
            body=rendered.body,
            status=NoticeStatus.SENT,
        )
    )
    await ledger.append(
        session,
        context,
        event_type="RECOURSE_SENT",
        subject_type="decision",
        subject_id=decision.id,
        payload={"language": rendered.language, "options": len(options)},
    )
    await session.commit()
    return NoticeOut(subject=rendered.subject, body=rendered.body, language=rendered.language)


def _outcome(decision: Decision) -> str:
    for rule in reversed(decision.fired_rules or []):
        if isinstance(rule, dict) and rule.get("outcome"):
            return str(rule["outcome"])
    return decision.action.value
