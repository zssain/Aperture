"""Affordability tests: worked EMI fixtures (to the rupee), null→INDETERMINATE,
irregular-income p25, max-principal consistency, monotonicity, purity, persistence."""

import itertools
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from app.models.applicant import Applicant
from app.models.enums import AssessmentKind, UserRole
from app.models.feature import FeatureSnapshot
from app.schemas.assessment import AffordabilityPayload
from app.services.affordability.service import (
    RequestedTerms,
    assess_affordability,
    compute_emi_paise,
    persist_affordability,
    principal_from_emi_paise,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_user

AS_OF = datetime(2026, 7, 1, tzinfo=UTC)


def _snapshot(values: Mapping[str, object]) -> FeatureSnapshot:
    return FeatureSnapshot(values=dict(values), null_map={}, as_of=AS_OF)


_REGULAR_INCOME = {
    "median_monthly_inflow_paise": 5_000_000,
    "p25_monthly_inflow_paise": 4_000_000,
    "monthly_inflow_cv": 0.11,
    "monthly_emi_paise": 1_200_000,
    "essential_expense_paise": 2_900_000,
}


# --------------------------------------------------------------------------- #
# EMI to the rupee (hand-computed spreadsheet fixtures)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("principal_paise", "tenor", "rate_bps", "expected_paise"),
    [
        (10_000_000, 12, 1200, 888_488),  # ₹1,00,000 @ 12% / 12m → ₹8,884.88
        (5_000_000, 24, 1800, 249_620),  # ₹50,000  @ 18% / 24m → ₹2,496.20
        (20_000_000, 36, 0, 555_556),  # ₹2,00,000 @ 0%  / 36m → ₹5,555.56
    ],
)
def test_emi_matches_hand_computation_to_the_rupee(
    principal_paise: int, tenor: int, rate_bps: int, expected_paise: int
) -> None:
    emi = compute_emi_paise(principal_paise, tenor, rate_bps)
    assert abs(emi - expected_paise) <= 100  # within ₹1


def test_worked_affordability_example() -> None:
    result = assess_affordability(_snapshot(_REGULAR_INCOME), RequestedTerms(10_000_000, 12, 1200))
    assert result.status == "PASS"
    assert result.income_basis == "median"
    assert result.net_monthly_income_paise == 5_000_000
    assert abs((result.new_emi_paise or 0) - 888_488) <= 100
    assert result.disposable_income_paise == 5_000_000 - 1_200_000 - 2_900_000
    assert result.dsr == pytest.approx((1_200_000 + 888_488) / 5_000_000, abs=1e-4)
    assert result.max_supportable_emi_paise == 1_300_000  # 0.5*5,000,000 - 1,200,000


# --------------------------------------------------------------------------- #
# Null income → INDETERMINATE (never FAIL)
# --------------------------------------------------------------------------- #
def test_null_income_is_indeterminate_not_fail() -> None:
    snapshot = FeatureSnapshot(
        values={"monthly_emi_paise": 1_200_000},
        null_map={"median_monthly_inflow_paise": "no_income_observed"},
        as_of=AS_OF,
    )
    result = assess_affordability(snapshot, RequestedTerms(10_000_000, 12, 1200))
    assert result.status == "INDETERMINATE"
    assert result.status != "FAIL"
    assert result.reason == "income_not_observable"
    assert result.net_monthly_income_paise is None


# --------------------------------------------------------------------------- #
# Irregular income → 25th percentile, recorded
# --------------------------------------------------------------------------- #
def test_irregular_income_uses_p25_and_records_it() -> None:
    irregular = {**_REGULAR_INCOME, "monthly_inflow_cv": 0.30}  # above 0.25 threshold
    result = assess_affordability(_snapshot(irregular), RequestedTerms(10_000_000, 12, 1200))
    assert result.income_basis == "p25"
    assert result.irregular_income is True
    assert result.net_monthly_income_paise == 4_000_000


# --------------------------------------------------------------------------- #
# Terms cap consistency + principal-exceeds → FAIL
# --------------------------------------------------------------------------- #
def test_max_principal_consistent_with_max_emi() -> None:
    result = assess_affordability(_snapshot(_REGULAR_INCOME), RequestedTerms(10_000_000, 12, 1200))
    assert result.max_supportable_emi_paise is not None
    assert result.max_supportable_principal_paise is not None
    reconstructed = compute_emi_paise(result.max_supportable_principal_paise, 12, 1200)
    assert abs(reconstructed - result.max_supportable_emi_paise) <= 100  # within ₹1


def test_request_above_max_principal_fails_with_maximum_stated() -> None:
    result = assess_affordability(_snapshot(_REGULAR_INCOME), RequestedTerms(100_000_000, 12, 1200))
    assert result.status == "FAIL"
    assert result.reason == "principal_exceeds_max"
    assert result.max_supportable_principal_paise is not None
    assert result.requested_amount_paise > result.max_supportable_principal_paise


def test_zero_obligations_uses_only_new_emi() -> None:
    values = {
        "median_monthly_inflow_paise": 5_000_000,
        "monthly_inflow_cv": 0.10,
    }  # no monthly_emi_paise
    result = assess_affordability(_snapshot(values), RequestedTerms(5_000_000, 24, 1200))
    assert result.existing_emi_paise == 0
    assert result.dsr == pytest.approx((result.new_emi_paise or 0) / 5_000_000, abs=1e-6)


# --------------------------------------------------------------------------- #
# Properties + purity
# --------------------------------------------------------------------------- #
def test_dsr_monotonic_increasing_in_requested_amount() -> None:
    snapshot = _snapshot(_REGULAR_INCOME)
    dsrs = [
        assess_affordability(snapshot, RequestedTerms(amount, 12, 1200)).dsr
        for amount in (2_000_000, 5_000_000, 10_000_000, 15_000_000)
    ]
    assert all(a is not None and b is not None and a < b for a, b in itertools.pairwise(dsrs))


def test_assess_affordability_is_pure() -> None:
    snapshot = _snapshot(_REGULAR_INCOME)
    terms = RequestedTerms(10_000_000, 12, 1200)
    assert assess_affordability(snapshot, terms) == assess_affordability(snapshot, terms)


def test_stress_test_is_reported() -> None:
    result = assess_affordability(_snapshot(_REGULAR_INCOME), RequestedTerms(5_000_000, 24, 1200))
    assert result.stressed_dsr is not None
    assert result.stress_pass is not None


def test_principal_from_emi_zero_rate() -> None:
    assert principal_from_emi_paise(555_556, 36, 0) == 555_556 * 36


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
async def test_affordability_persists_as_assessment_row(db_session: AsyncSession) -> None:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    applicant = Applicant(tenant_id=tenant.id, external_ref=f"a-{uuid.uuid4().hex[:8]}")
    db_session.add(applicant)
    await db_session.flush()
    snapshot = FeatureSnapshot(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        as_of=AS_OF,
        schema_version="features-v1",
        values=dict(_REGULAR_INCOME),
        null_map={},
        input_hash="hash",
    )
    db_session.add(snapshot)
    await db_session.commit()

    assessment = assess_affordability(snapshot, RequestedTerms(10_000_000, 12, 1200))
    row = await persist_affordability(
        db_session, tenant_id=tenant.id, feature_snapshot=snapshot, assessment=assessment
    )
    assert row.kind is AssessmentKind.AFFORDABILITY
    assert row.engine_version == assessment.engine_version
    parsed = AffordabilityPayload(**row.payload)
    assert parsed.status == "PASS"
    assert parsed.new_emi_paise == assessment.new_emi_paise
