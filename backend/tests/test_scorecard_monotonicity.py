"""Cash-flow scorecard: full monotonicity suite, published rationale, UNCALIBRATED,
and credit_features containment. (Pure — no trained artifact needed.)"""

import pytest
from app.registries.credit_features import CREDIT_FEATURES
from app.registries.fairness_attributes import FAIRNESS_ATTRIBUTES
from ml.scorecard.cashflow_scorecard_v1 import (
    FEATURE_ORDER,
    FEATURES,
    INTERCEPT,
    predict,
)
from ml.scorecard.monotonicity_test import run_monotonicity_check


@pytest.mark.parametrize("feature", [f.key for f in FEATURES])
def test_each_feature_is_monotonic_in_its_declared_direction(feature: str) -> None:
    results = run_monotonicity_check()
    assert results[feature] is True


def test_every_weight_has_a_rationale() -> None:
    for feature in FEATURES:
        assert feature.rationale.strip(), f"{feature.key} has no rationale"
        assert feature.direction in {"PD_UP", "PD_DOWN"}


def test_scorecard_output_is_always_uncalibrated() -> None:
    output = predict({f.key: (f.low + f.high) / 2 for f in FEATURES})
    assert output.calibration_status == "UNCALIBRATED"
    assert 0.0 <= output.pd <= 1.0


def test_scorecard_uses_only_credit_features_and_no_fairness_attributes() -> None:
    keys = set(FEATURE_ORDER)
    assert keys <= CREDIT_FEATURES
    assert not (keys & FAIRNESS_ATTRIBUTES)
    # A deliberate violation would be caught by the containment check.
    assert (keys | {"age"}) & FAIRNESS_ATTRIBUTES


def test_contributions_are_exact_and_sum_into_log_odds() -> None:
    features = {f.key: (f.low + f.high) / 2 for f in FEATURES}
    output = predict(features)
    total = sum(c.contribution for c in output.contributions)
    assert output.log_odds == pytest.approx(INTERCEPT + total, abs=1e-9)
