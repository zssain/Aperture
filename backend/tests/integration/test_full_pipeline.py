"""Decision pipeline integration over verified-account and document evidence tiers."""

import pytest
from app.models.assessment import Assessment
from app.models.enums import SourceTier
from app.models.source import SourceConnection, SourceSnapshot
from app.services.orchestrator.replay import IDENTICAL, replay
from app.services.orchestrator.service import decide
from app.services.risk.registry import REGISTRY_PATH
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.decision_fixtures import AS_OF, build_decidable, publish_seed

pytestmark = pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="risk artifacts not built")


@pytest.mark.parametrize("tier", [SourceTier.AA_VERIFIED, SourceTier.DECLARED_DOCUMENT])
async def test_both_evidence_paths_reach_a_complete_replayable_decision(
    db_session: AsyncSession, tier: SourceTier
) -> None:
    fixture = await build_decidable(db_session)
    connection = await db_session.scalar(
        select(SourceConnection).where(SourceConnection.applicant_id == fixture.applicant.id)
    )
    snapshot = await db_session.scalar(
        select(SourceSnapshot).where(SourceSnapshot.applicant_id == fixture.applicant.id)
    )
    assert connection is not None and snapshot is not None
    connection.tier = tier
    snapshot.tier = tier
    await db_session.commit()
    await publish_seed(db_session, fixture)
    result = await decide(
        db_session,
        fixture.context,
        application_id=fixture.application.id,
        as_of=AS_OF,
        idempotency_key=f"integration-{tier.value}",
        generate_recourse=False,
    )
    assessment_count = await db_session.scalar(
        select(func.count())
        .select_from(Assessment)
        .where(Assessment.feature_snapshot_id == result.decision.feature_snapshot_id)
    )
    assert assessment_count == 4
    replayed = await replay(
        db_session, tenant_id=fixture.tenant_id, decision_id=result.decision.id
    )
    assert replayed.status == IDENTICAL
