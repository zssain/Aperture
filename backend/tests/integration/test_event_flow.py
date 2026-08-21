"""The release event journey must create an explainable eligibility change."""

from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_change_detection import (
    test_demo_generator_uses_real_event_and_feature_engines as _event_scenario,
)


async def test_decline_to_newly_eligible_names_the_driving_feature(
    db_session: AsyncSession,
) -> None:
    await _event_scenario(db_session)
