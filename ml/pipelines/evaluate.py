"""Evaluation metrics with bootstrap confidence intervals.

Measured numbers only. Nothing here targets or asserts a threshold — the point is an
honest report of how the benchmark performs on ITS population, not the product's.
"""

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)


def ks_statistic(y_true: NDArray[np.int_], y_score: NDArray[np.float64]) -> float:
    """Kolmogorov-Smirnov separation between positive and negative score distributions."""
    from scipy.stats import ks_2samp

    positives = y_score[y_true == 1]
    negatives = y_score[y_true == 0]
    if len(positives) == 0 or len(negatives) == 0:
        return 0.0
    return float(ks_2samp(positives, negatives).statistic)


_METRICS: dict[str, Callable[[NDArray[np.int_], NDArray[np.float64]], float]] = {
    "roc_auc": lambda y, s: float(roc_auc_score(y, s)),
    "pr_auc": lambda y, s: float(average_precision_score(y, s)),
    "brier": lambda y, s: float(brier_score_loss(y, s)),
    "ks": ks_statistic,
}


def _bootstrap_ci(
    y_true: NDArray[np.int_],
    y_score: NDArray[np.float64],
    metric: Callable[[NDArray[np.int_], NDArray[np.float64]], float],
    *,
    n_boot: int = 400,
    seed: int = 42,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(y_true)
    samples: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        y_b, s_b = y_true[idx], y_score[idx]
        if len(np.unique(y_b)) < 2:
            continue
        samples.append(metric(y_b, s_b))
    if not samples:
        return (float("nan"), float("nan"))
    lo, hi = np.percentile(samples, [2.5, 97.5])
    return (float(lo), float(hi))


def evaluate_scores(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, metric in _METRICS.items():
        point = metric(y_true, y_score)
        ci_low, ci_high = _bootstrap_ci(y_true, y_score, metric)
        result[name] = {"value": point, "ci95": [ci_low, ci_high]}

    prob_true, prob_pred = calibration_curve(
        y_true, y_score, n_bins=10, strategy="quantile"
    )
    result["reliability_curve"] = {
        "prob_true": [float(x) for x in prob_true],
        "prob_pred": [float(x) for x in prob_pred],
    }
    return result
