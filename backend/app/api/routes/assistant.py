"""Grounded AI assistants: explain-this-decision (per case) and architecture Q&A.

Both are read-only and grounded — they phrase only over facts/maps the server hands the model,
attach real citations, and degrade to deterministic output when the LLM is disabled.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_context
from app.core.context import RequestContext
from app.db.session import get_session
from app.services.assistant.architecture import ArchitectureAnswer, answer_architecture
from app.services.assistant.decision_explainer import DecisionExplanation, explain_decision
from app.services.cases.assembler import CaseNotFoundError

router = APIRouter(tags=["assistant"])


class QuestionIn(BaseModel):
    question: str = Field(default="", max_length=500)


@router.post("/cases/{application_id}/explain", response_model=DecisionExplanation)
async def explain_case_decision(
    application_id: uuid.UUID,
    payload: QuestionIn,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> DecisionExplanation:
    try:
        return await explain_decision(
            session, context.tenant_id, application_id, payload.question
        )
    except CaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CASE_NOT_FOUND", "message": "Case not found"},
        ) from exc


@router.post("/architecture/ask", response_model=ArchitectureAnswer)
async def ask_architecture(
    payload: QuestionIn,
    _: RequestContext = Depends(get_context),
) -> ArchitectureAnswer:
    return await answer_architecture(payload.question)
