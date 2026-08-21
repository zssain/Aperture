"""Feature service tests: per-feature hand-computed fixtures, null/clamp behaviour,
point-in-time correctness (DB + Hypothesis), cross-process hash stability."""

import pathlib
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.enums import EventDirection, EvidenceEventType, UserRole
from app.models.feature import FeatureSnapshot
from app.models.ledger import LedgerEvent
from app.services.classification.service import TxnEvent, classify
from app.services.features.schema import SchemaViolationError, validate
from app.services.features.service import (
    compute_feature_values,
    compute_input_hash,
    compute_snapshot,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_user

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
AS_OF = datetime(2026, 7, 1, tzinfo=UTC)
_CONN = uuid.uuid4()


def _txn(
    days_ago: int,
    direction: EventDirection,
    amount_paise: int,
    description: str,
    counterparty: str,
    balance_paise: int | None = None,
) -> TxnEvent:
    return TxnEvent(
        event_id=uuid.uuid4(),
        occurred_at=AS_OF - timedelta(days=days_ago),
        direction=direction,
        amount_paise=amount_paise,
        balance_paise=balance_paise,
        description=description,
        counterparty_hash=counterparty,
        source_connection_id=_CONN,
    )


def _rich_events() -> list[TxnEvent]:
    events: list[TxnEvent] = []
    for m in range(6):
        amount = 5_000_000 if m < 3 else 4_000_000
        balance = 8_000_000 if m < 3 else 6_000_000
        events.append(
            _txn(15 + m * 30, EventDirection.CREDIT, amount, "Salary credit", "SAL", balance)
        )
    for m in range(3):
        events.append(_txn(5 + m * 30, EventDirection.DEBIT, 1_500_000, "Rent debit", "RENT"))
        events.append(_txn(10 + m * 30, EventDirection.DEBIT, 1_200_000, "EMI debit", "EMILOAN"))
        events.append(_txn(12 + m * 30, EventDirection.DEBIT, 200_000, "Utility bill", "UTIL"))
    for m in range(2):
        events.append(_txn(8 + m * 30, EventDirection.DEBIT, 50_000, "Mobile recharge", "TEL"))
    events.append(_txn(20, EventDirection.DEBIT, 40_000, "Groceries xyz", "GROC"))
    return events


_EXPECTED_VALUES = {
    "history_depth_days": 165,
    "median_monthly_inflow_paise": 4_500_000,
    "p25_monthly_inflow_paise": 4_000_000,
    "total_inflow_6m_paise": 27_000_000,
    "inflow_source_count": 1,
    "income_months_observed": 6,
    "salary_income_share": 1.0,
    "gig_income_share": 0.0,
    "business_income_share": 0.0,
    "monthly_emi_paise": 1_200_000,
    "essential_expense_paise": 2_950_000,
    "mean_balance_paise": 8_000_000,
    "min_balance_paise": 8_000_000,
    "balance_min_to_mean_ratio": 1.0,
    "utility_payment_ratio": 0.5,
    "utility_ontime_streak_months": 3,
    "telecom_continuity_months": 2,
    "source_diversity": 1,
}
_EXPECTED_APPROX = {
    "monthly_inflow_cv": 0.1111,
    "inflow_trend_ratio": 1.25,
    "debt_service_ratio": 1_200_000 / 4_500_000,
    "essential_expense_ratio": 2_950_000 / 4_500_000,
    "expense_cover_months": 8_000_000 / 2_950_000,
    "other_share": 1 / 18,
    "txn_density_per_month": 3.0,
}
_EXPECTED_NULL = {
    "bureau_score": "no_bureau_data",
    "bureau_active_loans": "no_bureau_data",
    "bureau_delinquencies_12m": "no_bureau_data",
}


@pytest.mark.parametrize("key", list(_EXPECTED_VALUES))
def test_feature_exact_value(key: str) -> None:
    values, _null_map, _lineage = compute_feature_values(AS_OF, classify(_rich_events()).events)
    assert values[key] == _EXPECTED_VALUES[key]


@pytest.mark.parametrize("key", list(_EXPECTED_APPROX))
def test_feature_approx_value(key: str) -> None:
    values, _null_map, _lineage = compute_feature_values(AS_OF, classify(_rich_events()).events)
    assert values[key] == pytest.approx(_EXPECTED_APPROX[key], abs=1e-3)


@pytest.mark.parametrize("key", list(_EXPECTED_NULL))
def test_feature_expected_null(key: str) -> None:
    values, null_map, _lineage = compute_feature_values(AS_OF, classify(_rich_events()).events)
    assert key not in values
    assert null_map[key] == _EXPECTED_NULL[key]


# --------------------------------------------------------------------------- #
# Null / zero / clamp behaviour
# --------------------------------------------------------------------------- #
def test_zero_events_only_history_depth_is_zero() -> None:
    values, null_map, _lineage = compute_feature_values(AS_OF, ())
    assert values == {"history_depth_days": 0}
    # No feature returns 0 for absent data — everything else is NULL with a reason.
    assert all(reason for reason in null_map.values())
    assert "median_monthly_inflow_paise" in null_map


def test_cv_returns_null_below_mean_floor() -> None:
    events = [
        _txn(15, EventDirection.CREDIT, 5_000, "Salary credit", "SAL"),
        _txn(45, EventDirection.CREDIT, 5_000, "Salary credit", "SAL"),
        _txn(75, EventDirection.CREDIT, 5_000, "Salary credit", "SAL"),
    ]
    values, null_map, _lineage = compute_feature_values(AS_OF, classify(events).events)
    assert "monthly_inflow_cv" not in values
    assert null_map["monthly_inflow_cv"] == "mean_below_floor"


def test_single_month_windowed_features_are_null() -> None:
    events = [
        _txn(3, EventDirection.CREDIT, 5_000_000, "Salary credit", "SAL"),
        _txn(6, EventDirection.CREDIT, 5_000_000, "Salary credit", "SAL"),
    ]
    values, null_map, _lineage = compute_feature_values(AS_OF, classify(events).events)
    assert "median_monthly_inflow_paise" not in values
    assert null_map["median_monthly_inflow_paise"] == "insufficient_history"


def test_ratio_is_clamped_and_recorded() -> None:
    events = [
        _txn(15, EventDirection.CREDIT, 4_500_000, "Salary credit", "SAL"),
        _txn(45, EventDirection.CREDIT, 4_500_000, "Salary credit", "SAL"),
        # EMI far exceeds income → DSR would be > 2 → clamp to 2.0.
        _txn(10, EventDirection.DEBIT, 20_000_000, "EMI debit", "EMILOAN"),
        _txn(40, EventDirection.DEBIT, 20_000_000, "EMI debit", "EMILOAN"),
    ]
    values, _null_map, lineage = compute_feature_values(AS_OF, classify(events).events)
    assert values["debt_service_ratio"] == 2.0
    assert lineage["debt_service_ratio"]["clamped"] is True


def test_schema_violation_raises_rather_than_coercing() -> None:
    with pytest.raises(SchemaViolationError):
        validate({}, {})  # every feature is absent
    with pytest.raises(SchemaViolationError):
        validate({"other_share": 2.0}, {})  # out of range [0, 1] and others missing


# --------------------------------------------------------------------------- #
# Cross-process determinism of the input hash
# --------------------------------------------------------------------------- #
def test_input_hash_is_stable_across_processes() -> None:
    local = compute_input_hash(["id-b", "id-a"], AS_OF, "features-v1")
    code = (
        "from datetime import datetime, UTC\n"
        "from app.services.features.service import compute_input_hash\n"
        "print(compute_input_hash(['id-b', 'id-a'], "
        "datetime(2026, 7, 1, tzinfo=UTC), 'features-v1'), end='')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout == local


def test_input_hash_changes_with_catalogue_or_classifier() -> None:
    baseline = compute_input_hash(["a"], AS_OF, "features-v1", "catalog-v1", "clf-v2")
    assert baseline != compute_input_hash(["a"], AS_OF, "features-v1", "catalog-v2", "clf-v2")
    assert baseline != compute_input_hash(["a"], AS_OF, "features-v1", "catalog-v1", "clf-v3")


# --------------------------------------------------------------------------- #
# Point-in-time property (Hypothesis): future events never change the features
# --------------------------------------------------------------------------- #
@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    before=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=300),
            st.sampled_from([EventDirection.CREDIT, EventDirection.DEBIT]),
            st.integers(min_value=1_000, max_value=10_000_000),
        ),
        max_size=25,
    ),
    future=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=90),
            st.sampled_from([EventDirection.CREDIT, EventDirection.DEBIT]),
            st.integers(min_value=1_000, max_value=10_000_000),
        ),
        max_size=10,
    ),
)
def test_future_events_never_change_features(
    before: list[tuple[int, EventDirection, int]],
    future: list[tuple[int, EventDirection, int]],
) -> None:
    before_events = [
        _txn(days, direction, amount, "Salary credit", "SAL")
        for (days, direction, amount) in before
    ]
    future_events = [
        TxnEvent(
            uuid.uuid4(), AS_OF + timedelta(days=days), direction, amount, None, "x", "SAL", _CONN
        )
        for (days, direction, amount) in future
    ]
    combined = before_events + future_events
    filtered = [event for event in combined if event.occurred_at <= AS_OF]

    baseline = compute_feature_values(AS_OF, classify(before_events).events)
    with_future = compute_feature_values(AS_OF, classify(filtered).events)
    assert baseline == with_future


# --------------------------------------------------------------------------- #
# Point-in-time correctness against the database (immutable snapshots)
# --------------------------------------------------------------------------- #
async def _new_application(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    applicant = Applicant(tenant_id=tenant.id, external_ref=f"app-{uuid.uuid4().hex[:8]}")
    db_session.add(applicant)
    await db_session.flush()
    application = Application(tenant_id=tenant.id, applicant_id=applicant.id)
    db_session.add(application)
    await db_session.commit()
    return tenant.id, application.id


async def _add_ledger_event(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    application_id: uuid.UUID,
    occurred_at: datetime,
    amount_paise: int,
) -> None:
    application = await db_session.get(Application, application_id)
    assert application is not None
    db_session.add(
        LedgerEvent(
            tenant_id=tenant_id,
            applicant_id=application.applicant_id,
            event_type=EvidenceEventType.TRANSACTION,
            direction=EventDirection.CREDIT,
            amount_paise=amount_paise,
            balance_paise=8_000_000,
            currency="INR",
            description="Salary credit",
            counterparty_hash="SAL",
            occurred_at=occurred_at,
            received_at=datetime.now(UTC),
            idempotency_key=uuid.uuid4().hex,
            payload={},
        )
    )
    await db_session.commit()


async def test_future_event_does_not_change_snapshot(db_session: AsyncSession) -> None:
    tenant_id, application_id = await _new_application(db_session)
    as_of = datetime(2026, 4, 1, tzinfo=UTC)
    for days in (20, 50, 80):
        await _add_ledger_event(
            db_session, tenant_id, application_id, as_of - timedelta(days=days), 5_000_000
        )

    snap1 = await compute_snapshot(
        db_session, tenant_id=tenant_id, application_id=application_id, as_of=as_of
    )
    values1, hash1, snap1_id = dict(snap1.values), snap1.input_hash, snap1.id

    # A later event must not affect a snapshot taken at the earlier as_of.
    await _add_ledger_event(
        db_session, tenant_id, application_id, as_of + timedelta(days=10), 9_999_999
    )
    snap2 = await compute_snapshot(
        db_session, tenant_id=tenant_id, application_id=application_id, as_of=as_of
    )
    assert snap2.input_hash == hash1
    assert snap2.values == values1

    db_session.expire_all()
    old = await db_session.get(FeatureSnapshot, snap1_id)
    assert old is not None and old.values == values1


async def test_backfill_creates_new_snapshot_and_leaves_old_unchanged(
    db_session: AsyncSession,
) -> None:
    tenant_id, application_id = await _new_application(db_session)
    as_of = datetime(2026, 4, 1, tzinfo=UTC)
    for days in (20, 50, 80):
        await _add_ledger_event(
            db_session, tenant_id, application_id, as_of - timedelta(days=days), 5_000_000
        )
    snap1 = await compute_snapshot(
        db_session, tenant_id=tenant_id, application_id=application_id, as_of=as_of
    )
    values1, hash1, snap1_id = dict(snap1.values), snap1.input_hash, snap1.id

    # Backfill an event with an EARLIER occurred_at (<= as_of).
    await _add_ledger_event(
        db_session, tenant_id, application_id, as_of - timedelta(days=110), 4_000_000
    )
    snap2 = await compute_snapshot(
        db_session, tenant_id=tenant_id, application_id=application_id, as_of=as_of
    )
    assert snap2.input_hash != hash1  # a new snapshot that includes the backfill

    db_session.expire_all()
    old = await db_session.get(FeatureSnapshot, snap1_id)
    assert old is not None and old.values == values1  # the old snapshot is untouched


async def test_zero_events_still_produces_a_snapshot(db_session: AsyncSession) -> None:
    tenant_id, application_id = await _new_application(db_session)
    as_of = datetime(2026, 4, 1, tzinfo=UTC)
    snapshot = await compute_snapshot(
        db_session, tenant_id=tenant_id, application_id=application_id, as_of=as_of
    )
    assert snapshot.values == {"history_depth_days": 0}
    assert "median_monthly_inflow_paise" in snapshot.null_map

    events = list(
        await db_session.scalars(select(LedgerEvent).where(LedgerEvent.tenant_id == tenant_id))
    )
    assert events == []
