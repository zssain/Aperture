"""Coverage assessment tests: each component hand-verifiable, exact missing-source
deltas, diminishing diversity, freshness penalty, monotonicity, and persistence."""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest
from app.models.applicant import Applicant
from app.models.enums import AssessmentKind, SourceTier, SourceType, UserRole
from app.models.feature import FeatureSnapshot
from app.schemas.assessment import CoveragePayload
from app.services.coverage.service import (
    CoverageComponent,
    SourceEvidence,
    assess_coverage,
    persist_coverage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_user

AS_OF = datetime(2026, 7, 1, tzinfo=UTC)

_FULL_FEATURES = {
    "history_depth_days": 200,
    "median_monthly_inflow_paise": 5_000_000,
    "monthly_emi_paise": 1_200_000,
    "essential_expense_paise": 2_900_000,
    "mean_balance_paise": 8_000_000,
}


def _snapshot(
    values: Mapping[str, object] | None = None,
    null_map: Mapping[str, object] | None = None,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        values=dict(_FULL_FEATURES if values is None else values),
        null_map=dict(null_map or {}),
        as_of=AS_OF,
    )


def _source(source_type: SourceType, tier: SourceTier, days_old: int = 5) -> SourceEvidence:
    return SourceEvidence(source_type, tier, AS_OF - timedelta(days=days_old))


def _component(assessment_components: list[CoverageComponent], name: str) -> CoverageComponent:
    return next(component for component in assessment_components if component.name == name)


# --------------------------------------------------------------------------- #
# Each component, verifiable by hand
# --------------------------------------------------------------------------- #
def test_tier_component() -> None:
    aa = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED)])
    assert _component(aa.components, "tier").contribution == 20.0  # 20 * 1.0
    declared = assess_coverage(
        _snapshot(), [_source(SourceType.UTILITY, SourceTier.DECLARED_DOCUMENT)]
    )
    assert _component(declared.components, "tier").contribution == 8.0  # 20 * 0.4


def test_verification_component() -> None:
    verified = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED)])
    assert _component(verified.components, "verification").contribution == 15.0  # 15 * 1.0
    declared = assess_coverage(
        _snapshot(), [_source(SourceType.UTILITY, SourceTier.DECLARED_DOCUMENT)]
    )
    assert _component(declared.components, "verification").contribution == 7.5  # 15 * 0.5


def test_history_depth_component() -> None:
    sources = [_source(SourceType.BANK, SourceTier.AA_VERIFIED)]
    half = assess_coverage(_snapshot({**_FULL_FEATURES, "history_depth_days": 90}), sources)
    assert _component(half.components, "history_depth").contribution == 10.0  # 20 * 90/180
    full = assess_coverage(_snapshot(), sources)
    assert _component(full.components, "history_depth").contribution == 20.0


def test_freshness_component_penalises_stale_data() -> None:
    sources = [_source(SourceType.BANK, SourceTier.AA_VERIFIED, days_old=95)]
    stale = assess_coverage(_snapshot(), sources)
    fresh = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED, 5)])
    stale_c = _component(stale.components, "freshness").contribution
    fresh_c = _component(fresh.components, "freshness").contribution
    assert fresh_c == 15.0
    assert stale_c < 6.0  # 90+ days old → substantial penalty


def test_diversity_component_diminishing_returns() -> None:
    one = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED)])
    assert _component(one.components, "diversity").contribution == 7.5  # 15 * (1.0/2.0)
    four_same = assess_coverage(
        _snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED) for _ in range(4)]
    )
    # effective = 1 + .3 + .09 + .027 = 1.417 → fraction 0.7085
    assert _component(four_same.components, "diversity").fraction == pytest.approx(0.7085, abs=1e-3)


def test_completeness_component() -> None:
    sources = [_source(SourceType.BANK, SourceTier.AA_VERIFIED)]
    full = assess_coverage(_snapshot(), sources)
    assert _component(full.components, "completeness").contribution == 15.0
    missing_one = _snapshot(
        {k: v for k, v in _FULL_FEATURES.items() if k != "median_monthly_inflow_paise"},
        {"median_monthly_inflow_paise": "no_income_observed"},
    )
    partial = assess_coverage(missing_one, sources)
    assert _component(partial.components, "completeness").contribution == 12.0  # 15 * 4/5


# --------------------------------------------------------------------------- #
# Score assembly, band gating, missing sources
# --------------------------------------------------------------------------- #
def test_score_always_has_component_breakdown() -> None:
    cov = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED)])
    assert {c.name for c in cov.components} == {
        "tier",
        "verification",
        "history_depth",
        "freshness",
        "diversity",
        "completeness",
    }
    assert cov.score == sum(round(c.contribution) for c in cov.components) or cov.score == round(
        sum(c.contribution for c in cov.components)
    )


def test_single_source_is_capped_below_high() -> None:
    cov = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED)])
    assert cov.score >= 75  # high raw score
    assert cov.band != "HIGH"  # but diversity caps the band


def test_four_same_type_scores_lower_than_two_different() -> None:
    four_same = assess_coverage(
        _snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED) for _ in range(4)]
    )
    two_diff = assess_coverage(
        _snapshot(),
        [
            _source(SourceType.BANK, SourceTier.AA_VERIFIED),
            _source(SourceType.UTILITY, SourceTier.DECLARED_DOCUMENT),
        ],
    )
    assert four_same.score < two_diff.score


def test_removing_a_source_lowers_score_by_the_reported_delta() -> None:
    base = [_source(SourceType.BANK, SourceTier.AA_VERIFIED)]
    base_cov = assess_coverage(_snapshot(), base)
    telecom_delta = next(
        m.coverage_delta for m in base_cov.missing_sources if m.source_type == "TELECOM"
    )
    with_telecom = [*base, _source(SourceType.TELECOM, SourceTier.DECLARED_DOCUMENT)]
    with_cov = assess_coverage(_snapshot(), with_telecom)
    assert with_cov.score - base_cov.score == telecom_delta


def test_missing_sources_name_type_reason_and_delta() -> None:
    cov = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED)])
    types = {m.source_type for m in cov.missing_sources}
    assert {"BUREAU", "UTILITY", "TELECOM"} <= types
    assert all(m.why for m in cov.missing_sources)


# --------------------------------------------------------------------------- #
# Properties: monotonic in source count and freshness
# --------------------------------------------------------------------------- #
def test_score_monotonic_non_decreasing_in_freshness() -> None:
    scores = [
        assess_coverage(
            _snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED, days_old=d)]
        ).score
        for d in (5, 30, 60, 90, 120)
    ]
    assert scores == sorted(scores, reverse=True)  # fresher (smaller d) ≥ staler


def test_adding_a_distinct_source_does_not_lower_score() -> None:
    one = assess_coverage(_snapshot(), [_source(SourceType.BANK, SourceTier.AA_VERIFIED)]).score
    two = assess_coverage(
        _snapshot(),
        [
            _source(SourceType.BANK, SourceTier.AA_VERIFIED),
            _source(SourceType.UTILITY, SourceTier.DECLARED_DOCUMENT),
        ],
    ).score
    assert two >= one


def test_assess_coverage_is_pure() -> None:
    snapshot = _snapshot()
    sources = [_source(SourceType.BANK, SourceTier.AA_VERIFIED)]
    first = assess_coverage(snapshot, sources)
    second = assess_coverage(snapshot, sources)
    assert first == second


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
async def test_coverage_persists_as_assessment_row(db_session: AsyncSession) -> None:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    applicant = Applicant(tenant_id=tenant.id, external_ref=f"a-{uuid.uuid4().hex[:8]}")
    db_session.add(applicant)
    await db_session.flush()
    snapshot = FeatureSnapshot(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        as_of=AS_OF,
        schema_version="features-v1",
        values=dict(_FULL_FEATURES),
        null_map={},
        input_hash="hash",
    )
    db_session.add(snapshot)
    await db_session.commit()

    assessment = assess_coverage(snapshot, [_source(SourceType.BANK, SourceTier.AA_VERIFIED)])
    row = await persist_coverage(
        db_session, tenant_id=tenant.id, feature_snapshot=snapshot, assessment=assessment
    )
    assert row.kind is AssessmentKind.COVERAGE
    assert row.engine_version == assessment.engine_version
    # Payload round-trips through the typed schema.
    parsed = CoveragePayload(**row.payload)
    assert parsed.score == assessment.score
    assert len(parsed.components) == 6
