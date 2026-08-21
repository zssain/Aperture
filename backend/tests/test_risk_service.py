"""Risk inference tests: routing, no-fallback failure modes, schema mismatch, PD
bounds, calibration disjointness, latency, and registry hash enforcement.

Artifact-dependent tests skip when the benchmark has not been built (run
`python -m ml.pipelines.train_benchmark`); the scorecard path always runs.
"""

import json
import pathlib
import time
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from app.models.feature import FeatureSnapshot
from app.services.risk.registry import (
    REGISTRY_PATH,
    RegistryError,
    get_registry,
    load_registry,
    reset_cache,
)
from app.services.risk.service import (
    InsufficientFeaturesError,
    InvalidProbabilityError,
    SchemaMismatchError,
    _check_probability,
    assert_model_features_allowed,
    assess_risk,
)

pytestmark = pytest.mark.skipif(
    not REGISTRY_PATH.exists(),
    reason="risk artifacts not built (run python -m ml.pipelines.train_benchmark)",
)

_SCORECARD_FEATURES = {
    "median_monthly_inflow_paise": 5_000_000,
    "monthly_inflow_cv": 0.5,
    "inflow_trend_ratio": 1.0,
    "debt_service_ratio": 0.4,
    "essential_expense_ratio": 0.6,
    "balance_min_to_mean_ratio": 0.8,
    "mean_balance_paise": 3_000_000,
    "utility_ontime_streak_months": 6,
    "telecom_continuity_months": 6,
    "other_share": 0.05,
    "history_depth_days": 300,
}


def _snapshot(values: Mapping[str, object], schema: str = "features-v1") -> FeatureSnapshot:
    return FeatureSnapshot(
        schema_version=schema, values=dict(values), null_map={}, as_of=datetime.now(UTC)
    )


# --------------------------------------------------------------------------- #
# Model B (scorecard) inference
# --------------------------------------------------------------------------- #
def test_scorecard_inference_is_uncalibrated_with_reasons() -> None:
    result = assess_risk(_snapshot(_SCORECARD_FEATURES))
    assert 0.0 <= result.pd <= 1.0
    assert result.calibration_status == "UNCALIBRATED"
    assert result.model_version == "cashflow-scorecard-v1"
    assert result.reason_codes  # at least one
    assert result.feature_schema_version == "features-v1"
    assert any(c["present"] for c in result.contributions)


def test_model_b_output_always_uncalibrated() -> None:
    result = assess_risk(_snapshot({"median_monthly_inflow_paise": 4_000_000}))
    assert result.calibration_status == "UNCALIBRATED"


# --------------------------------------------------------------------------- #
# No-fallback failure modes
# --------------------------------------------------------------------------- #
def test_all_null_snapshot_raises_insufficient_features() -> None:
    with pytest.raises(InsufficientFeaturesError):
        assess_risk(_snapshot({}))


def test_no_observable_scorecard_features_raises() -> None:
    # Non-scorecard keys only → the scorecard uses zero features.
    with pytest.raises(InsufficientFeaturesError):
        assess_risk(_snapshot({"bureau_score": 700}))


def test_schema_mismatch_raises_and_does_not_coerce() -> None:
    with pytest.raises(SchemaMismatchError):
        assess_risk(_snapshot(_SCORECARD_FEATURES, schema="features-v99"))


def test_probability_outside_unit_interval_raises() -> None:
    with pytest.raises(InvalidProbabilityError):
        _check_probability(1.5)
    assert _check_probability(0.5) == 0.5


# --------------------------------------------------------------------------- #
# Model A (benchmark) inference
# --------------------------------------------------------------------------- #
def test_benchmark_inference_is_calibrated() -> None:
    registry = get_registry()
    if registry.benchmark is None:
        pytest.skip("benchmark not registered")
    values = dict.fromkeys(registry.benchmark.feature_columns, 0.0)
    result = assess_risk(_snapshot(values, schema="uci-default-v1"))
    assert 0.0 <= result.pd <= 1.0
    assert result.calibration_status == "CALIBRATED"
    assert result.model_version == "benchmark-v1"
    assert result.contributions  # TreeSHAP contributions present


def test_calibrator_fitted_disjoint_from_training() -> None:
    metrics_path = REGISTRY_PATH.parent / "benchmark_v1.metrics.json"
    if not metrics_path.exists():
        pytest.skip("metrics not present")
    metrics = json.loads(metrics_path.read_text())
    calibration = metrics["calibration"]
    assert calibration["fitted_on"] == "validation"
    assert calibration["disjoint_from_training"] is True
    # The split partitions the dataset, so train/val/holdout are disjoint by construction.
    manifest = json.loads((REGISTRY_PATH.parent.parent / "data" / "manifest.json").read_text())
    assert metrics["n_train"] + metrics["n_validation"] + metrics["n_holdout"] == manifest["n_rows"]
    assert metrics["n_validation"] > 0
    # The LR baseline is trained and reported alongside XGBoost.
    assert metrics["logistic_regression_baseline"]["roc_auc"]["value"] > 0.5
    assert metrics["xgboost_calibrated"]["roc_auc"]["value"] > 0.5


# --------------------------------------------------------------------------- #
# Registry hash enforcement (a swapped model is fatal)
# --------------------------------------------------------------------------- #
def test_hash_mismatch_raises(tmp_path: pathlib.Path) -> None:
    manifest = json.loads(REGISTRY_PATH.read_text())
    for entry in manifest["models"].values():
        entry["artifact_sha256"] = "0" * 64  # tamper every recorded hash
    tampered = tmp_path / "registry.json"
    tampered.write_text(json.dumps(manifest))
    with pytest.raises(RegistryError):
        load_registry(tampered)


def test_missing_artifact_raises_and_returns_no_score(tmp_path: pathlib.Path) -> None:
    manifest = json.loads(REGISTRY_PATH.read_text())
    for entry in manifest["models"].values():
        if entry.get("kind") == "benchmark":
            entry["artifact_path"] = "ml/artifacts/does_not_exist.joblib"
    broken = tmp_path / "registry.json"
    broken.write_text(json.dumps(manifest))
    # The load itself raises — no PD is produced and no default value is returned.
    with pytest.raises(RegistryError):
        load_registry(broken)


def test_feature_allow_list_enforced() -> None:
    reset_cache()
    assert_model_features_allowed()  # passes for the real scorecard


# --------------------------------------------------------------------------- #
# Latency
# --------------------------------------------------------------------------- #
def test_scorecard_inference_p95_latency_under_200ms() -> None:
    snapshot = _snapshot(_SCORECARD_FEATURES)
    assess_risk(snapshot)  # warm the cached registry
    timings: list[float] = []
    for _ in range(200):
        start = time.perf_counter()
        assess_risk(snapshot)
        timings.append((time.perf_counter() - start) * 1000)
    timings.sort()
    p95 = timings[int(0.95 * len(timings))]
    assert p95 < 200.0
