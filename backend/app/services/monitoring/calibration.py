"""Calibration and discrimination metrics over closed outcomes."""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sklearn.metrics import brier_score_loss, roc_auc_score, roc_curve

from app.services.monitoring.gating import MetricResult

MINIMUM_OUTCOMES = 200


def not_yet(model: str, n: int, minimum_n: int = MINIMUM_OUTCOMES) -> MetricResult:
    projected = datetime.now(UTC) + timedelta(days=max(0, minimum_n - n) * 3)
    return MetricResult(
        status="NOT_YET_MEASURABLE",
        n=n,
        minimum_n=minimum_n,
        reason=f"{model} requires {minimum_n} closed outcomes; {n} exist.",
        projected_date=projected.date().isoformat(),
    )


def calibration_metrics(rows: list[tuple[float, int]], model: str = "Model A") -> dict[str, Any]:
    n = len(rows)
    if n < MINIMUM_OUTCOMES:
        missing = not_yet(model, n)
        return {
            "brier": missing.model_dump(),
            "reliability": [],
            "data_as_of": datetime.now(UTC).isoformat(),
        }
    scores = np.asarray([row[0] for row in rows], dtype=float)
    labels = np.asarray([row[1] for row in rows], dtype=int)
    curve = []
    for lower in np.linspace(0, 0.9, 10):
        mask = (scores >= lower) & (scores < lower + 0.1)
        if mask.any():
            curve.append(
                {
                    "predicted": float(scores[mask].mean()),
                    "observed": float(labels[mask].mean()),
                    "n": int(mask.sum()),
                }
            )
    brier = float(brier_score_loss(labels, scores))
    se = math.sqrt(max(brier * (1 - brier), 0) / n)
    result = MetricResult(
        status="MEASURED",
        value=brier,
        ci_low=max(0, brier - 1.96 * se),
        ci_high=min(1, brier + 1.96 * se),
        n=n,
        minimum_n=MINIMUM_OUTCOMES,
    )
    return {
        "brier": result.model_dump(),
        "reliability": curve,
        "data_as_of": datetime.now(UTC).isoformat(),
    }


def discrimination(rows: list[tuple[float, int]]) -> dict[str, MetricResult]:
    n = len(rows)
    if n < MINIMUM_OUTCOMES or len({row[1] for row in rows}) < 2:
        missing = not_yet("Discrimination", n)
        return {"auc": missing, "ks": missing}
    scores = np.asarray([row[0] for row in rows])
    labels = np.asarray([row[1] for row in rows])
    auc = float(roc_auc_score(labels, scores))
    fpr, tpr, _ = roc_curve(labels, scores)
    ks = float(np.max(tpr - fpr))
    rng = np.random.default_rng(17)
    auc_samples: list[float] = []
    ks_samples: list[float] = []
    for _ in range(200):
        idx = rng.integers(0, n, n)
        y = labels[idx]
        s = scores[idx]
        if len(set(y.tolist())) < 2:
            continue
        auc_samples.append(float(roc_auc_score(y, s)))
        bfpr, btpr, _ = roc_curve(y, s)
        ks_samples.append(float(np.max(btpr - bfpr)))

    def measured(value: float, samples: list[float]) -> MetricResult:
        return MetricResult(
            status="MEASURED",
            value=value,
            ci_low=float(np.quantile(samples, 0.025)),
            ci_high=float(np.quantile(samples, 0.975)),
            n=n,
            minimum_n=MINIMUM_OUTCOMES,
        )

    return {"auc": measured(auc, auc_samples), "ks": measured(ks, ks_samples)}
