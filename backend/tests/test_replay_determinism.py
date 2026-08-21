"""Replay determinism - a permanent release gate.

Replaying a decision under its recorded policy must be IDENTICAL and reuse the stored risk
payload. Replaying under a different policy version returns the counterfactual outcome.
"""

import pytest
from app.models.enums import PolicyStatus
from app.models.policy import PolicyVersion
from app.services.orchestrator.replay import DIVERGED, IDENTICAL, replay
from app.services.orchestrator.service import decide
from app.services.policy.defaults import seed_policy_v1
from app.services.risk.registry import REGISTRY_PATH
from sqlalchemy.ext.asyncio import AsyncSession

from tests.decision_fixtures import AS_OF, build_decidable, publish_seed

pytestmark = pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="risk artifacts not built")


async def test_replay_is_identical_and_reuses_stored_risk(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    result = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
    )

    replayed = await replay(db_session, tenant_id=d.tenant_id, decision_id=result.decision.id)
    assert replayed.status == IDENTICAL, replayed.diff
    assert replayed.diff == {}
    assert replayed.reused_risk is True
    assert replayed.counterfactual is False


async def test_replay_is_repeatable(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    result = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
    )
    first = await replay(db_session, tenant_id=d.tenant_id, decision_id=result.decision.id)
    for _ in range(5):
        again = await replay(db_session, tenant_id=d.tenant_id, decision_id=result.decision.id)
        assert again.status == first.status == IDENTICAL
        assert again.recomputed_action == first.recomputed_action


async def test_replay_under_different_policy_returns_counterfactual(
    db_session: AsyncSession,
) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    result = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k"
    )
    assert result.decision.action.value in {"APPROVE", "APPROVE_STARTER"}

    # A stricter policy that declines essentially any risk, stored as a separate (draft) version.
    strict = seed_policy_v1().model_copy(
        update={
            "policy_version": "policy-strict",
            "pd_enhanced": 0.0001,
            "pd_standard": 0.0005,
            "pd_decline_threshold": 0.001,
            # This test isolates the threshold counterfactual. Exploration is a
            # separate deterministic policy effect and would legitimately approve
            # roughly five percent of random application UUIDs.
            "exploration_budget": 0.0,
        }
    )
    alt = PolicyVersion(
        tenant_id=d.tenant_id,
        version=99,
        status=PolicyStatus.DRAFT,
        rules=strict.model_dump(mode="json"),
    )
    db_session.add(alt)
    await db_session.flush()

    counterfactual = await replay(
        db_session,
        tenant_id=d.tenant_id,
        decision_id=result.decision.id,
        policy_version_id=alt.id,
    )
    assert counterfactual.counterfactual is True
    assert counterfactual.recomputed_outcome == "DECLINE_RISK"
    assert counterfactual.status == DIVERGED
