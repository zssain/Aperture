"""Monotonicity check for the cash-flow scorecard.

For each feature, perturb it up from a neutral mid-range baseline and assert the PD
moves in the feature's DECLARED direction. Importable so both the ml build and the
backend test suite run the same check.
"""

from typing import Any

from ml.scorecard.cashflow_scorecard_v1 import FEATURES, predict


def _baseline() -> dict[str, Any]:
    # Mid-range value for every feature (transform ~ 0, none saturated).
    return {f.key: (f.low + f.high) / 2 for f in FEATURES}


def run_monotonicity_check() -> dict[str, bool]:
    """Return {feature_key: passed} for every feature."""
    results: dict[str, bool] = {}
    for feature in FEATURES:
        base = _baseline()
        span = feature.high - feature.low
        lower = dict(base)
        higher = dict(base)
        lower[feature.key] = feature.low + span * 0.25
        higher[feature.key] = feature.low + span * 0.75

        pd_lower = predict(lower).pd
        pd_higher = predict(higher).pd
        if feature.direction == "PD_UP":
            results[feature.key] = pd_higher > pd_lower
        else:  # PD_DOWN
            results[feature.key] = pd_higher < pd_lower
    return results


if __name__ == "__main__":  # pragma: no cover
    outcome = run_monotonicity_check()
    for key, passed in outcome.items():
        print(f"{'OK ' if passed else 'FAIL'} {key}")
    if not all(outcome.values()):
        raise SystemExit(1)
