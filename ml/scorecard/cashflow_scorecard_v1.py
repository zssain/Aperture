"""Cash-flow scorecard v1 — a transparent additive points model over the product's
observed cash-flow features. PUBLISHED IN FULL: every weight has a written rationale.

This model is ALWAYS ``UNCALIBRATED`` — there is no outcome data linking these features
to defaults yet (see the stage README). It exists to score the feature space the product
actually observes, honestly labelled as uncalibrated, until real calibration is earned.

Design: each feature is transformed to a centred, monotonic value in [-0.5, +0.5]
(clamped), multiplied by a signed weight (the sign is the declared monotonic direction),
and summed through a logistic link. Contributions are therefore EXACT and closed-form —
no SHAP approximation is needed or permitted here.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

SCORECARD_VERSION = "cashflow-scorecard-v1"
FEATURE_SCHEMA_VERSION = "features-v1"
CALIBRATION_STATUS = "UNCALIBRATED"

# Base log-odds for a fully-neutral applicant (every transform at 0). logit(0.15).
INTERCEPT = -1.7346


@dataclass(frozen=True)
class ScorecardFeature:
    key: str
    weight: float
    low: float  # transform lower bound (value <= low -> t = -0.5)
    high: float  # transform upper bound (value >= high -> t = +0.5)
    direction: str  # "PD_UP" | "PD_DOWN": which way PD moves as the feature increases
    rationale: str


# All keys are members of the credit_features allow-list (enforced by a test).
FEATURES: tuple[ScorecardFeature, ...] = (
    ScorecardFeature(
        "median_monthly_inflow_paise", -1.4, 0.0, 10_000_000.0, "PD_DOWN",
        "Higher, larger income raises capacity to repay, so PD falls as inflow rises.",
    ),
    ScorecardFeature(
        "monthly_inflow_cv", 1.5, 0.0, 1.0, "PD_UP",
        "Volatile income (high coefficient of variation) is harder to service debt from; PD rises.",
    ),
    ScorecardFeature(
        "inflow_trend_ratio", -0.8, 0.5, 1.5, "PD_DOWN",
        "Rising recent income vs prior period signals improving capacity; PD falls.",
    ),
    ScorecardFeature(
        "debt_service_ratio", 1.6, 0.0, 1.0, "PD_UP",
        "A larger share of income already committed to EMIs leaves less headroom; PD rises with DSR.",
    ),
    ScorecardFeature(
        "essential_expense_ratio", 1.0, 0.0, 1.5, "PD_UP",
        "High essential outgo relative to income squeezes disposable income; PD rises.",
    ),
    ScorecardFeature(
        "balance_min_to_mean_ratio", -1.0, 0.0, 1.0, "PD_DOWN",
        "A minimum balance close to the mean indicates a stable buffer, not living to zero; PD falls.",
    ),
    ScorecardFeature(
        "mean_balance_paise", -1.0, 0.0, 5_000_000.0, "PD_DOWN",
        "A thicker average balance buffer absorbs shocks; PD falls as the buffer grows.",
    ),
    ScorecardFeature(
        "utility_ontime_streak_months", -1.1, 0.0, 12.0, "PD_DOWN",
        "A long unbroken run of on-time utility payments is durable repayment discipline; PD falls.",
    ),
    ScorecardFeature(
        "telecom_continuity_months", -0.6, 0.0, 12.0, "PD_DOWN",
        "Telecom continuity is a thin-file stability signal; PD falls modestly with continuity.",
    ),
    ScorecardFeature(
        "other_share", 1.2, 0.0, 0.5, "PD_UP",
        "A large share of unclassifiable transactions is unexplained behaviour; ignorance raises PD.",
    ),
    ScorecardFeature(
        "history_depth_days", -0.9, 0.0, 365.0, "PD_DOWN",
        "A longer observed history is more evidence to stand on; PD falls as depth grows.",
    ),
)

FEATURE_ORDER: tuple[str, ...] = tuple(f.key for f in FEATURES)


@dataclass(frozen=True)
class Contribution:
    feature: str
    value: float | None
    transformed: float
    contribution: float  # exact log-odds contribution (weight * transform)
    direction: str
    present: bool


@dataclass(frozen=True)
class ScorecardOutput:
    pd: float
    log_odds: float
    contributions: list[Contribution]
    features_used: int
    calibration_status: str
    scorecard_version: str
    feature_schema_version: str


def _centred_transform(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    scaled = (value - low) / (high - low)
    clamped = min(1.0, max(0.0, scaled))
    return clamped - 0.5  # [-0.5, +0.5]


def predict(features: dict[str, Any]) -> ScorecardOutput:
    """Score a feature dict. Missing features contribute nothing (no imputation of a
    value — a neutral 0, distinct from a computed extreme)."""
    log_odds = INTERCEPT
    contributions: list[Contribution] = []
    used = 0
    for feature in FEATURES:
        raw = features.get(feature.key)
        if raw is None:
            contributions.append(
                Contribution(feature.key, None, 0.0, 0.0, feature.direction, present=False)
            )
            continue
        used += 1
        transformed = _centred_transform(float(raw), feature.low, feature.high)
        contribution = feature.weight * transformed
        log_odds += contribution
        contributions.append(
            Contribution(
                feature.key,
                float(raw),
                transformed,
                contribution,
                feature.direction,
                present=True,
            )
        )
    pd = 1.0 / (1.0 + math.exp(-log_odds))
    return ScorecardOutput(
        pd=pd,
        log_odds=log_odds,
        contributions=contributions,
        features_used=used,
        calibration_status=CALIBRATION_STATUS,
        scorecard_version=SCORECARD_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
    )


def weights_document() -> dict[str, Any]:
    """The full published weights (the registry hashes this)."""
    return {
        "scorecard_version": SCORECARD_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "calibration_status": CALIBRATION_STATUS,
        "intercept": INTERCEPT,
        "features": [
            {
                "key": f.key,
                "weight": f.weight,
                "low": f.low,
                "high": f.high,
                "direction": f.direction,
                "rationale": f.rationale,
            }
            for f in FEATURES
        ],
    }


def scorecard_fingerprint() -> str:
    """Stable SHA-256 over the published weights document (registry verification)."""
    canonical = json.dumps(weights_document(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
