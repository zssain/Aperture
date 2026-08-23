"""Orchestrator integration tests: end-to-end, idempotency, every failure path, the
single-transaction rollback guarantee, concurrency recovery, supersession, and latency.

Artifact-dependent (the risk scorecard must be registered); skipped if not built.
"""

import time
import uuid

import pytest
from app.models.audit import LedgerEntry
from app.models.decision import Decision
from app.services.orchestrator.idempotency import find_existing_decision
from app.services.orchestrator.service import SystemUnavailableError, decide
from app.services.risk.registry import REGISTRY_PATH
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.decision_fixtures import AS_OF, build_decidable, publish_seed

pytestmark = pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="risk artifacts not built")


async def _decision_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(Decision).where(Decision.tenant_id == tenant_id)
        )
        or 0
    )


async def _ledger_decision_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(
                LedgerEntry.event_type == "DECISION_MADE",
                LedgerEntry.tenant_id == tenant_id,
            )
        )
        or 0
    )


async def test_end_to_end_produces_full_decision_with_ledger(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)

    result = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k1"
    )

    assert result.created is True
    assert result.decision.action.value in {"APPROVE", "APPROVE_STARTER"}
    assert result.decision.terms  # terms present for an approval
    assert result.policy_decision.reasons[0].code.startswith("GATE_")
    assert await _ledger_decision_count(db_session, d.tenant_id) == 1
    # The stored snapshot exists (replay depends on it).
    assert result.decision.feature_snapshot_id is not None


async def test_same_idempotency_key_returns_identical_decision_no_new_ledger(
    db_session: AsyncSession,
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)

    first = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
    )
    ledger_after_first = await _ledger_decision_count(db_session, d.tenant_id)

    second = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
    )

    assert second.decision.id == first.decision.id
    assert second.created is False
    # No second ledger entry for the repeated key.
    assert await _ledger_decision_count(db_session, d.tenant_id) == ledger_after_first


async def test_assessment_failure_persists_no_decision_and_raises(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)

    def _boom(_snapshot: object) -> object:
        raise RuntimeError("risk model down")

    monkeypatch.setattr("app.services.orchestrator.assessments.assess_risk", _boom)

    with pytest.raises(SystemUnavailableError):
        await decide(
            db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
        )
    await db_session.rollback()
    assert await _decision_count(db_session, d.tenant_id) == 0


async def test_null_requested_amount_fails_rather_than_assessing_zero_loan(
    db_session: AsyncSession,
) -> None:
    """A missing requested amount is unknowable input, not a ₹0 loan: the decision must
    fail as SYSTEM_UNAVAILABLE (invariant 2), never fabricate a zero and assess it."""
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    d.application.requested_amount_paise = None
    await db_session.flush()

    with pytest.raises(SystemUnavailableError):
        await decide(
            db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
        )
    await db_session.rollback()
    assert await _decision_count(db_session, d.tenant_id) == 0


async def test_ledger_append_failure_rolls_back_decision(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)

    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("ledger append failed")

    monkeypatch.setattr("app.services.orchestrator.service.ledger.append", _boom)

    with pytest.raises(RuntimeError):
        await decide(
            db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
        )
    await db_session.rollback()
    # No orphan decision — the decision and its ledger entry are one transaction.
    assert await _decision_count(db_session, d.tenant_id) == 0


async def test_concurrent_decide_one_wins_on_unique_constraint(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)

    winner = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="race"
    )

    # Simulate the concurrent path: the pre-insert idempotency check misses the winner (as it
    # would under a true race), so the commit hits the unique index and recovery returns the winner.
    calls = {"n": 0}

    async def _find_missing_first(
        session: AsyncSession, *, tenant_id: uuid.UUID, idempotency_key: str
    ) -> Decision | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return await find_existing_decision(
            session, tenant_id=tenant_id, idempotency_key=idempotency_key
        )

    monkeypatch.setattr(
        "app.services.orchestrator.service.find_existing_decision", _find_missing_first
    )

    loser = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="race"
    )
    assert loser.decision.id == winner.decision.id
    assert loser.created is False
    assert await _decision_count(db_session, d.tenant_id) == 1


async def test_supersede_once_trigger_links_predecessor_but_freezes_the_rest(
    db_session: AsyncSession,
) -> None:
    d1 = await build_decidable(db_session)
    await publish_seed(db_session, d1)
    a = await decide(
        db_session, d1.context, application_id=d1.application.id, as_of=AS_OF, idempotency_key="a"
    )
    d2 = await build_decidable(db_session)
    await publish_seed(db_session, d2)
    b = await decide(
        db_session, d2.context, application_id=d2.application.id, as_of=AS_OF, idempotency_key="b"
    )

    # A one-time superseded_by set is permitted.
    await db_session.execute(
        text("UPDATE decisions SET superseded_by = :b WHERE id = :a"),
        {"b": b.decision.id, "a": a.decision.id},
    )
    await db_session.commit()

    # Any other mutation of a decided outcome is refused by the trigger.
    with pytest.raises(Exception):  # noqa: B017 - restrict_violation surfaces as a DB error
        await db_session.execute(
            text("UPDATE decisions SET action = 'DECLINE' WHERE id = :a"),
            {"a": a.decision.id},
        )
        await db_session.commit()
    await db_session.rollback()


async def test_p95_end_to_end_latency_under_2_5s(db_session: AsyncSession) -> None:
    timings: list[float] = []
    for i in range(5):
        d = await build_decidable(db_session)
        await publish_seed(db_session, d)
        start = time.perf_counter()
        await decide(
            db_session,
            d.context,
            application_id=d.application.id,
            as_of=AS_OF,
            idempotency_key=f"lat-{i}",
        )
        timings.append(time.perf_counter() - start)
    timings.sort()
    p95 = timings[int(0.95 * (len(timings) - 1))]
    assert p95 < 2.5, timings
