"""Risk inference: validate schema, route, predict, calibrate, attribute, reason.

NO FALLBACK SCORE UNDER ANY CONDITION. A missing artifact, a hash mismatch, a schema
mismatch, an impossible probability, or an all-null snapshot each RAISES — inventing a
PD from nothing is exactly what this product exists to stop.
"""

from dataclasses import dataclass
from typing import Any

from app.models.feature import FeatureSnapshot
from app.registries.credit_features import CREDIT_FEATURES
from app.registries.fairness_attributes import FAIRNESS_ATTRIBUTES
from app.services.risk.attribution import (
    additive_contributions,
    treeshap_contributions,
)
from app.services.risk.reasons import reason_codes
from app.services.risk.registry import (
    BenchmarkModel,
    LoadedRegistry,
    ScorecardModel,
    get_registry,
)


class RiskError(Exception):
    """Base risk error — always fatal, never a fallback."""


class InsufficientFeaturesError(RiskError):
    """The snapshot has too little signal to produce any PD."""


class SchemaMismatchError(RiskError):
    """The snapshot's feature schema does not match the routed model. Never coerce."""


class InvalidProbabilityError(RiskError):
    """A model produced a PD outside [0, 1]; it is broken, not to be papered over."""


class RiskModelUnavailableError(RiskError):
    """The routed model is not registered/available."""


@dataclass(frozen=True)
class RiskAssessment:
    pd: float
    calibration_status: str
    model_version: str
    feature_schema_version: str
    contributions: list[dict[str, Any]]
    reason_codes: list[str]


def assert_model_features_allowed() -> None:
    """No feature outside ``credit_features`` may reach a product model; no fairness
    attribute may reach any model. (The benchmark uses its own UCI feature space.)"""
    scorecard_features = set(get_registry().scorecard.feature_order)
    outside = scorecard_features - CREDIT_FEATURES
    if outside:
        raise RiskError(f"scorecard uses non-credit features: {sorted(outside)}")
    leaked = scorecard_features & FAIRNESS_ATTRIBUTES
    if leaked:
        raise RiskError(f"scorecard uses fairness attributes: {sorted(leaked)}")


def _check_probability(pd_value: float) -> float:
    if not (0.0 <= pd_value <= 1.0):
        raise InvalidProbabilityError(f"model produced PD={pd_value!r} outside [0, 1]")
    return pd_value


def _assess_with_scorecard(snapshot: FeatureSnapshot, model: ScorecardModel) -> RiskAssessment:
    values = snapshot.values
    feature_input = {key: values.get(key) for key in model.feature_order}
    output = model.module.predict(feature_input)
    if output.features_used == 0:
        raise InsufficientFeaturesError("no scorecard features are observable")

    pd_value = _check_probability(float(output.pd))
    pairs = additive_contributions(output)
    contributions = [
        {
            "feature": c.feature,
            "value": c.value,
            "contribution": float(c.contribution),
            "direction": c.direction,
            "present": c.present,
        }
        for c in output.contributions
    ]
    return RiskAssessment(
        pd=pd_value,
        calibration_status=model.calibration_status,  # UNCALIBRATED
        model_version=model.model_version,
        feature_schema_version=model.feature_schema_version,
        contributions=contributions,
        reason_codes=reason_codes(pairs),
    )


def _assess_with_benchmark(snapshot: FeatureSnapshot, model: BenchmarkModel) -> RiskAssessment:
    import numpy as np

    values = snapshot.values
    missing = [c for c in model.feature_columns if values.get(c) is None]
    if missing:
        raise InsufficientFeaturesError(f"benchmark requires all features; missing: {missing[:5]}")
    row = np.array([float(values[c]) for c in model.feature_columns], dtype=np.float32)
    raw = float(model.booster.predict_proba(row.reshape(1, -1))[0, 1])
    calibrated = float(model.calibrator.transform([raw])[0])
    pd_value = _check_probability(calibrated)

    pairs = treeshap_contributions(model.booster, row, model.feature_columns)
    ranked = sorted(pairs, key=lambda item: -abs(item[1]))
    contributions = [
        {"feature": feature, "contribution": contribution} for feature, contribution in ranked
    ]
    return RiskAssessment(
        pd=pd_value,
        calibration_status=model.calibration_status,  # CALIBRATED
        model_version=model.model_version,
        feature_schema_version=model.feature_schema_version,
        contributions=contributions,
        reason_codes=reason_codes(pairs),
    )


def assess_risk(
    feature_snapshot: FeatureSnapshot, registry: LoadedRegistry | None = None
) -> RiskAssessment:
    registry = registry or get_registry()
    values = feature_snapshot.values
    if not values:
        raise InsufficientFeaturesError("snapshot has no observable features")

    schema = feature_snapshot.schema_version
    # Route by feature schema. (When a bureau→benchmark adapter exists, bureau-rich
    # snapshots will be mapped into the benchmark schema; until then, product snapshots
    # in features-v1 are scored by the cash-flow scorecard.)
    if schema == registry.scorecard.feature_schema_version:
        return _assess_with_scorecard(feature_snapshot, registry.scorecard)
    if registry.benchmark is not None and schema == registry.benchmark.feature_schema_version:
        return _assess_with_benchmark(feature_snapshot, registry.benchmark)
    raise SchemaMismatchError(
        f"snapshot schema {schema!r} matches no registered model (never coerced)"
    )
