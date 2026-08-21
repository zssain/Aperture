"""Human-review tests: reason enforcement, the authority + role matrix, atomic finality under
concurrency, and notice content (correct numbers, no thresholds, no guarantees), en + hi.

Decisions are seeded directly so every routing/authority combination is cheap to construct.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from app.core.context import RequestContext
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.decision import Decision, DecisionReason, HumanReview
from app.models.enums import (
    DecisionAction,
    PolicyStatus,
    ReviewOutcome,
    ReviewStatus,
    UserRole,
)
from app.models.feature import FeatureSnapshot
from app.models.policy import PolicyVersion
from app.services.notices.renderer import render_decision_notice, render_recourse_notice
from app.services.policy.defaults import seed_policy_v1
from app.services.reviews.service import (
    AlreadyFinalError,
    InsufficientAuthorityError,
    RoleNotPermittedError,
    submit_review,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.conftest import requires_db
from tests.factories import DEFAULT_PASSWORD, create_user

pytestmark = requires_db

_RULES = seed_policy_v1().model_dump(mode="json")

_APPROVE_RULES = [{"number": 8, "name": "approve_standard", "outcome": "APPROVE_STANDARD"}]
_FRAUD_RULES = [{"number": 5, "name": "manipulation_elevated", "outcome": "REVIEW_FRAUD"}]


@dataclass
class Seeded:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    decision: Decision


async def _seed(
    session: AsyncSession,
    *,
    role: UserRole = UserRole.CREDIT_ANALYST,
    fired_rules: list[dict[str, object]] | None = None,
    action: DecisionAction = DecisionAction.APPROVE,
    approved_limit_paise: int | None = 1_000_000,
) -> Seeded:
    user, tenant = await create_user(session, role=role)
    applicant = Applicant(tenant_id=tenant.id, external_ref=f"ext-{uuid.uuid4().hex[:8]}")
    session.add(applicant)
    await session.flush()
    application = Application(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        requested_amount_paise=1_000_000,
        requested_tenor_months=12,
    )
    session.add(application)
    await session.flush()
    policy = PolicyVersion(tenant_id=tenant.id, version=1, status=PolicyStatus.LIVE, rules=_RULES)
    snapshot = FeatureSnapshot(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        application_id=application.id,
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
        schema_version="features-v1",
        values={},
        null_map={},
        input_hash=uuid.uuid4().hex,
    )
    session.add_all([policy, snapshot])
    await session.flush()
    decision = Decision(
        tenant_id=tenant.id,
        application_id=application.id,
        applicant_id=applicant.id,
        feature_snapshot_id=snapshot.id,
        policy_version_id=policy.id,
        action=action,
        routing="HUMAN",
        fired_rules=fired_rules or _APPROVE_RULES,
        is_final=False,
        terms={
            "approved_principal_paise": approved_limit_paise or 0,
            "approved_tenor_months": 12,
            "annual_rate_bps": 1800,
            "band": "B",
        },
        approved_limit_paise=approved_limit_paise,
    )
    session.add(decision)
    await session.flush()
    session.add(
        DecisionReason(
            tenant_id=tenant.id,
            decision_id=decision.id,
            code="GATE_APPROVE_STANDARD",
            message="GATE_APPROVE_STANDARD",
            detail={"polarity": "POSITIVE", "template_params": {}, "order": 0},
        )
    )
    await session.commit()
    return Seeded(tenant.id, user.id, user.email, decision)


def _context(seed: Seeded, role: str, *, ceiling: int | None = None) -> RequestContext:
    return RequestContext(
        user_id=seed.user_id,
        tenant_id=seed.tenant_id,
        role=role,
        email=seed.email,
        session_id=uuid.uuid4(),
        approval_ceilings_paise={role: ceiling} if ceiling is not None else {},
    )


# --------------------------------------------------------------------------- #
# Confirm → review recorded, decision final, ledger entry appended.
# --------------------------------------------------------------------------- #
async def test_confirm_records_review_final_and_ledger(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)
    ctx = _context(seed, "CREDIT_ANALYST", ceiling=5_000_000)

    result = await submit_review(
        db_session,
        ctx,
        decision_id=seed.decision.id,
        action="confirm",
        reason_code=None,
        reason_text=None,
        override_outcome=None,
    )

    assert result.resulting_outcome == "APPROVED"
    assert result.diverged is False
    review = await db_session.scalar(
        select(HumanReview).where(HumanReview.decision_id == seed.decision.id)
    )
    assert review is not None and review.status == ReviewStatus.RESOLVED
    # A DECISION_REVIEWED ledger entry exists for this decision.
    from app.models.audit import LedgerEntry

    entry = await db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.subject_id == seed.decision.id,
            LedgerEntry.event_type == "DECISION_REVIEWED",
        )
    )
    assert entry is not None


# --------------------------------------------------------------------------- #
# Override preserves the original recommendation verbatim in the ledger.
# --------------------------------------------------------------------------- #
async def test_override_preserves_recommendation(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)
    ctx = _context(seed, "CREDIT_ANALYST", ceiling=5_000_000)

    result = await submit_review(
        db_session,
        ctx,
        decision_id=seed.decision.id,
        action="override",
        reason_code="MANUAL_DECLINE",
        reason_text="Declining after manual review of documents.",
        override_outcome="DECLINED",
    )
    assert result.resulting_outcome == "DECLINED"
    assert result.diverged is True
    assert result.recommendation_outcome == "APPROVE_STANDARD"

    from app.models.audit import LedgerEntry

    entry = await db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.subject_id == seed.decision.id,
            LedgerEntry.event_type == "DECISION_REVIEWED",
        )
    )
    assert entry is not None
    assert entry.payload["recommendation"]["outcome"] == "APPROVE_STANDARD"
    assert entry.payload["resulting_outcome"] == "DECLINED"


# --------------------------------------------------------------------------- #
# Role matrix: analyst 403 on a fraud case; fraud reviewer succeeds.
# --------------------------------------------------------------------------- #
async def test_analyst_forbidden_on_fraud_case(db_session: AsyncSession) -> None:
    seed = await _seed(
        db_session, fired_rules=_FRAUD_RULES, action=DecisionAction.REFER, approved_limit_paise=None
    )
    analyst = _context(seed, "CREDIT_ANALYST")
    with pytest.raises(RoleNotPermittedError):
        await submit_review(
            db_session,
            analyst,
            decision_id=seed.decision.id,
            action="confirm",
            reason_code=None,
            reason_text=None,
            override_outcome=None,
        )


async def test_fraud_reviewer_resolves_fraud_case(db_session: AsyncSession) -> None:
    seed = await _seed(
        db_session,
        role=UserRole.FRAUD_REVIEWER,
        fired_rules=_FRAUD_RULES,
        action=DecisionAction.REFER,
        approved_limit_paise=None,
    )
    reviewer = _context(seed, "FRAUD_REVIEWER")
    result = await submit_review(
        db_session,
        reviewer,
        decision_id=seed.decision.id,
        action="confirm",
        reason_code=None,
        reason_text=None,
        override_outcome=None,
    )
    assert result.resulting_outcome == "ESCALATED"


# --------------------------------------------------------------------------- #
# Authority: an approval must be within the role's ceiling.
# --------------------------------------------------------------------------- #
async def test_authority_blocks_approval_above_ceiling(db_session: AsyncSession) -> None:
    seed = await _seed(db_session, approved_limit_paise=9_000_000)
    ctx = _context(seed, "CREDIT_ANALYST", ceiling=1_000_000)  # below the approved amount
    with pytest.raises(InsufficientAuthorityError):
        await submit_review(
            db_session,
            ctx,
            decision_id=seed.decision.id,
            action="confirm",
            reason_code=None,
            reason_text=None,
            override_outcome=None,
        )


# --------------------------------------------------------------------------- #
# Finality: a second submit loses cleanly with the winning outcome; the DB enforces one winner.
# --------------------------------------------------------------------------- #
async def test_second_submit_gets_winner(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)
    ctx = _context(seed, "CREDIT_ANALYST", ceiling=5_000_000)
    await submit_review(
        db_session,
        ctx,
        decision_id=seed.decision.id,
        action="confirm",
        reason_code=None,
        reason_text=None,
        override_outcome=None,
    )
    with pytest.raises(AlreadyFinalError) as excinfo:
        await submit_review(
            db_session,
            ctx,
            decision_id=seed.decision.id,
            action="override",
            reason_code="MANUAL_DECLINE",
            reason_text="Trying to override after the fact here.",
            override_outcome="DECLINED",
        )
    assert excinfo.value.winning_outcome == "APPROVED"


async def test_concurrent_resolution_has_one_winner(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    seed = await _seed(db_session)

    def _resolved() -> HumanReview:
        return HumanReview(
            tenant_id=seed.tenant_id,
            application_id=seed.decision.application_id,
            decision_id=seed.decision.id,
            status=ReviewStatus.RESOLVED,
            outcome=ReviewOutcome.APPROVED,
            queue="my-exceptions",
        )

    async with AsyncSession(db_engine) as sa, AsyncSession(db_engine) as sb:
        sa.add(_resolved())
        await sa.commit()  # A wins and commits its resolved review
        sb.add(_resolved())
        with pytest.raises(IntegrityError):
            await sb.flush()  # B loses on the one-resolved-per-decision index


# --------------------------------------------------------------------------- #
# Reason enforcement at the schema boundary (422), via HTTP.
# --------------------------------------------------------------------------- #
async def _login(client: httpx.AsyncClient, email: str) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    assert resp.status_code == 200


async def test_override_without_reason_is_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(db_session)
    await _login(client, seed.email)
    path = f"/api/v1/decisions/{seed.decision.id}/review"

    missing = await client.post(path, json={"action": "override", "override_outcome": "DECLINED"})
    assert missing.status_code == 422

    short = await client.post(
        path,
        json={
            "action": "override",
            "override_outcome": "DECLINED",
            "reason_code": "X",
            "reason_text": "too short",
        },
    )
    assert short.status_code == 422


# --------------------------------------------------------------------------- #
# Notices: correct numbers, no thresholds, no guarantees, en + hi.
# --------------------------------------------------------------------------- #
def test_decision_notice_states_terms_without_thresholds() -> None:
    reasons = [{"code": "GATE_APPROVE_STANDARD"}, {"code": "COVERAGE_GAP"}]
    terms = {
        "approved_principal_paise": 1_800_000,
        "approved_tenor_months": 9,
        "annual_rate_bps": 2200,
    }

    en = render_decision_notice(
        outcome="APPROVE_STANDARD", terms=terms, reasons=reasons, language="en"
    )
    assert "18,000" in en.body  # correct approved amount (paise → rupees)
    assert "22% per year" in en.body  # correct rate
    for forbidden in ("min_coverage", "threshold", "PD", "pd_", "0.1", "coverage 41"):
        assert forbidden not in en.body
    assert "guarantee" not in en.body.lower()

    hi = render_decision_notice(
        outcome="APPROVE_STANDARD", terms=terms, reasons=reasons, language="hi"
    )
    assert hi.language == "hi"
    assert "स्वीकृत" in hi.body  # rendered in Hindi from the same params
    assert "18,000" in hi.body


def test_recourse_notice_is_non_promissory_with_expiry() -> None:
    options = [
        {
            "required_change": {"lever": "ADD_SOURCE", "expires_at": "2026-09-15T00:00:00+00:00"},
        }
    ]
    for lang in ("en", "hi"):
        notice = render_recourse_notice(options=options, language=lang)
        assert "2026-09-15" in notice.body  # expiry present
        assert "guaranteed" not in notice.body.lower()
        assert "will be approved" not in notice.body.lower()
    en = render_recourse_notice(options=options, language="en")
    assert "does not ensure approval" in en.body
