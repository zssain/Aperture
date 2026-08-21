"""Recording a human decision - where invariant 10 (no silent overrides) becomes real.

A confirm accepts the recommendation; an override or an evidence request diverges from it and so
requires a reason (enforced at the schema boundary). The original recommendation is never
rewritten - the decision row is immutable - so it survives verbatim on the decision and again in
the ledger entry this writes. Finality is a single ``RESOLVED`` review row; the partial unique
index makes concurrent submissions resolve to one winner.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.models.application import Application
from app.models.decision import Decision, DecisionReason, HumanReview, RecourseOption
from app.models.enums import (
    DecisionAction,
    NoticeType,
    ReviewOutcome,
    ReviewStatus,
    UserRole,
)
from app.models.notice import Notice
from app.services.audit import ledger
from app.services.notices.renderer import (
    RenderedNotice,
    render_decision_notice,
    render_recourse_notice,
)

_FRAUD_OUTCOMES = frozenset({"FRAUD_REVIEW", "REVIEW_FRAUD"})

CONFIRM = "confirm"
OVERRIDE = "override"
REQUEST_EVIDENCE = "request_evidence"

_ACTION_TO_OUTCOME: dict[DecisionAction, ReviewOutcome] = {
    DecisionAction.APPROVE: ReviewOutcome.APPROVED,
    DecisionAction.APPROVE_STARTER: ReviewOutcome.APPROVED,
    DecisionAction.DECLINE: ReviewOutcome.DECLINED,
    DecisionAction.REFER: ReviewOutcome.ESCALATED,
}

_REVIEW_OUTCOME_TO_TEMPLATE = {
    ReviewOutcome.APPROVED: "APPROVE",
    ReviewOutcome.DECLINED: "DECLINE",
    ReviewOutcome.ESCALATED: "REVIEW",
}


class ReviewError(Exception):
    pass


class DecisionNotFoundError(ReviewError):
    pass


class RoleNotPermittedError(ReviewError):
    def __init__(self, required_role: str) -> None:
        super().__init__(f"requires role {required_role}")
        self.required_role = required_role


class InsufficientAuthorityError(ReviewError):
    pass


class AlreadyFinalError(ReviewError):
    """A resolved review already exists; the caller loses cleanly and sees the winner."""

    def __init__(self, winning_outcome: str) -> None:
        super().__init__("decision already finalised")
        self.winning_outcome = winning_outcome


@dataclass(frozen=True)
class ReviewResult:
    review: HumanReview
    resulting_outcome: str
    recommendation_outcome: str
    diverged: bool
    notice: RenderedNotice


def _first_gate_outcome(decision: Decision) -> str:
    for rule in decision.fired_rules or []:
        if isinstance(rule, dict) and 1 <= int(rule.get("number", 0)) <= 9:
            return str(rule.get("outcome", ""))
    return ""


def _recommendation_outcome(decision: Decision) -> str:
    for rule in reversed(decision.fired_rules or []):
        if isinstance(rule, dict) and rule.get("outcome"):
            return str(rule["outcome"])
    return decision.action.value


def is_fraud_routed(decision: Decision) -> bool:
    return _first_gate_outcome(decision) in _FRAUD_OUTCOMES


async def _resolved_review(
    session: AsyncSession, tenant_id: uuid.UUID, decision_id: uuid.UUID
) -> HumanReview | None:
    review: HumanReview | None = await session.scalar(
        select(HumanReview).where(
            HumanReview.tenant_id == tenant_id,
            HumanReview.decision_id == decision_id,
            HumanReview.status == ReviewStatus.RESOLVED,
        )
    )
    return review


def _resulting_outcome(
    action: str, decision: Decision, override_outcome: str | None
) -> ReviewOutcome:
    if action == CONFIRM:
        return _ACTION_TO_OUTCOME[decision.action]
    if action == OVERRIDE:
        assert override_outcome is not None  # enforced by the request schema
        return ReviewOutcome(override_outcome)
    return ReviewOutcome.ESCALATED  # request_evidence


async def _reasons_for(
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
    return [
        {"code": r.code, "template_params": dict((r.detail or {}).get("template_params", {}))}
        for r in rows
    ]


async def _recourse_for(
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


async def _render_notice(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    decision: Decision,
    resulting: ReviewOutcome,
    action: str,
    language: str,
) -> tuple[RenderedNotice, NoticeType]:
    if action == REQUEST_EVIDENCE:
        options = await _recourse_for(session, tenant_id, decision.id)
        rendered = render_recourse_notice(options=options, language=language)
        return rendered, NoticeType.RECOURSE_REQUEST
    reasons = await _reasons_for(session, tenant_id, decision.id)
    outcome = _REVIEW_OUTCOME_TO_TEMPLATE[resulting]
    return (
        render_decision_notice(
            outcome=outcome, terms=dict(decision.terms or {}), reasons=reasons, language=language
        ),
        NoticeType.DECISION,
    )


async def submit_review(
    session: AsyncSession,
    context: RequestContext,
    *,
    decision_id: uuid.UUID,
    action: str,
    reason_code: str | None,
    reason_text: str | None,
    override_outcome: str | None,
    language: str = "en",
) -> ReviewResult:
    decision = await session.get(Decision, decision_id)
    if decision is None or decision.tenant_id != context.tenant_id:
        raise DecisionNotFoundError(str(decision_id))

    # Role: a manipulation-routed case is a fraud reviewer's to resolve; an analyst is 403.
    if is_fraud_routed(decision) and context.role != UserRole.FRAUD_REVIEWER.value:
        raise RoleNotPermittedError(UserRole.FRAUD_REVIEWER.value)

    existing = await _resolved_review(session, context.tenant_id, decision_id)
    if existing is not None:
        raise AlreadyFinalError(existing.outcome.value if existing.outcome else "RESOLVED")

    resulting = _resulting_outcome(action, decision, override_outcome)

    # Authority: an approval must be within the role's ceiling.
    if resulting == ReviewOutcome.APPROVED:
        application = await session.get(Application, decision.application_id)
        amount = decision.approved_limit_paise or (
            application.requested_amount_paise if application else None
        )
        ceiling = context.ceiling_for_role()
        if ceiling is None or amount is None or amount > ceiling:
            raise InsufficientAuthorityError("amount exceeds approval authority")

    recommendation = _recommendation_outcome(decision)
    diverged = action != CONFIRM

    notice, notice_type = await _render_notice(
        session, context.tenant_id, decision, resulting, action, language
    )

    review = HumanReview(
        tenant_id=context.tenant_id,
        application_id=decision.application_id,
        decision_id=decision.id,
        reviewer_id=context.user_id,
        queue="fraud-review" if is_fraud_routed(decision) else "my-exceptions",
        status=ReviewStatus.RESOLVED,
        outcome=resulting,
        reason_code=reason_code,
        reason_text=reason_text,
        assigned_at=datetime.now(UTC),
        resolved_at=datetime.now(UTC),
    )

    # The ledger entry records the recommendation VERBATIM alongside what the human chose, so an
    # override is never silent (invariant 10). The append locks the tenant row, serialising
    # concurrent submitters so the loser's insert conflicts rather than deadlocks.
    await ledger.append(
        session,
        context,
        event_type="DECISION_REVIEWED",
        subject_type="decision",
        subject_id=decision.id,
        payload={
            "recommendation": {
                "action": decision.action.value,
                "outcome": recommendation,
                "fired_rules": [dict(r) for r in (decision.fired_rules or [])],
            },
            "review_action": action,
            "resulting_outcome": resulting.value,
            "diverged": diverged,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "reviewer_id": str(context.user_id),
        },
    )

    session.add(review)
    session.add(
        Notice(
            tenant_id=context.tenant_id,
            application_id=decision.application_id,
            decision_id=decision.id,
            applicant_id=decision.applicant_id,
            notice_type=notice_type,
            language=notice.language,
            subject=notice.subject,
            body=notice.body,
        )
    )

    try:
        await session.commit()
    except IntegrityError as exc:
        # Lost the race on the one-resolved-review index: return the winner cleanly (409).
        await session.rollback()
        winner = await _resolved_review(session, context.tenant_id, decision_id)
        winning = winner.outcome.value if winner and winner.outcome else "RESOLVED"
        raise AlreadyFinalError(winning) from exc

    return ReviewResult(
        review=review,
        resulting_outcome=resulting.value,
        recommendation_outcome=recommendation,
        diverged=diverged,
        notice=notice,
    )
