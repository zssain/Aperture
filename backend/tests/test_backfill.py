"""Unit tests for the model-health historical backfill (pure, no database).

These pin the honesty properties of the synthetic cohort: specs are balance-coherent
across the whole capacity gradient, the ground-truth hazard is independent of any model
and monotone in latent capacity, and outcome labels are deterministic and produce both
classes with a realistic bad rate. The end-to-end flip (endpoint reports MEASURED) is
covered by the database-gated integration test at the bottom.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from app.models.enums import OutcomeLabel
from app.services.demo.backfill import (
    _draw_outcome,
    _ground_truth_hazard,
    _historical_spec,
)
from app.services.demo.personas import build_corpus
from sqlalchemy.ext.asyncio import AsyncSession

_ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)
_ADVERSE = {OutcomeLabel.DELINQUENT, OutcomeLabel.DEFAULTED, OutcomeLabel.WRITTEN_OFF}


def test_historical_specs_are_balance_coherent_across_the_gradient() -> None:
    # build_corpus raises ValueError if any running balance goes negative; a clean pass over
    # the whole cohort proves every generated applicant is a coherent, fundable book.
    for index in range(300):
        spec, capacity = _historical_spec(index)
        assert 0.0 <= capacity < 1.0
        corpus = build_corpus(spec, _ANCHOR)
        assert corpus.events


def test_historical_specs_spread_income_and_statement_length() -> None:
    specs = [_historical_spec(index)[0] for index in range(60)]
    assert len({spec.months for spec in specs}) >= 3
    incomes = {spec.income_base_paise for spec in specs}
    assert max(incomes) - min(incomes) > 4_000_000


def test_ground_truth_hazard_is_monotone_and_bounded() -> None:
    assert _ground_truth_hazard(0.0) > _ground_truth_hazard(1.0)
    for capacity in (0.0, 0.25, 0.5, 0.75, 0.999):
        hazard = _ground_truth_hazard(capacity)
        assert 0.0 < hazard < 1.0
    assert _ground_truth_hazard(1.0) < 0.06  # strong applicants rarely default
    assert _ground_truth_hazard(0.0) > 0.40  # weak applicants carry real risk


def test_draw_outcome_is_deterministic() -> None:
    assert _draw_outcome(7, 0.3) == _draw_outcome(7, 0.3)
    assert _draw_outcome(0, 0.99) in _ADVERSE
    assert _draw_outcome(0, 0.0) not in _ADVERSE


def test_cohort_outcomes_have_both_classes_and_a_realistic_bad_rate() -> None:
    labels = [
        _draw_outcome(index, _ground_truth_hazard(_historical_spec(index)[1]))
        for index in range(240)
    ]
    adverse = sum(1 for label in labels if label in _ADVERSE)
    assert 0 < adverse < len(labels)  # both a good and a bad class are present
    assert 0.08 < adverse / len(labels) < 0.45  # independent hazard → minority-bad, realistic


# --------------------------------------------------------------------------- #
# Database-gated end-to-end flip: seeding the cohort makes the health endpoint measure.
# --------------------------------------------------------------------------- #
try:
    from tests.conftest import requires_db
except ImportError:  # pragma: no cover - conftest always importable under pytest
    requires_db = pytest.mark.skip(reason="conftest unavailable")


@requires_db
@pytest.mark.asyncio
async def test_backfill_makes_calibration_drift_and_overrides_measurable(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routes.health_metrics import _metrics
    from app.core.config import settings
    from app.models.tenant import Tenant
    from app.services.demo.backfill import seed_health_backfill
    from app.services.demo.seed import seed_demo
    from sqlalchemy import select

    # Lower only the *calibration* minimum so the test proves the flip without seeding 200
    # rows; drift's 100-decision floor is met by the cohort itself.
    monkeypatch.setattr(settings, "demo_seed_enabled", True)
    monkeypatch.setattr(settings, "demo_backfill_size", 120)
    monkeypatch.setattr("app.services.monitoring.calibration.MINIMUM_OUTCOMES", 100)

    await seed_demo()
    created = await seed_health_backfill()
    assert created == 120

    tenant = await db_session.scalar(select(Tenant).where(Tenant.slug == "aperture-demo"))
    assert tenant is not None
    metrics: Any = await _metrics(db_session, tenant.id)

    assert metrics["calibration"]["model_a"]["brier"]["status"] == "MEASURED"
    assert metrics["discrimination"]["auc"]["status"] == "MEASURED"
    assert metrics["drift"]["overall"]["status"] == "MEASURED"
    assert metrics["overrides"]["rate"]["status"] == "MEASURED"
    assert metrics["outcome_data_quality"]["n"] >= 120
