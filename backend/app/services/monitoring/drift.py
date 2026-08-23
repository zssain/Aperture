"""Population stability index against registered reference distributions."""

import math

from app.services.monitoring.gating import MetricResult


def score_bins(scores: list[float], bins: int = 10) -> list[float]:
    """Bin scores in [0, 1] into equal-width deciles and return the proportion per bin.

    Turns a real distribution of model pd scores into the ``actual``/``expected`` vectors
    :func:`population_stability_index` compares, so the drift metric measures a genuine
    population shift between two windows rather than a placeholder.
    """
    counts = [0] * bins
    for score in scores:
        index = min(int(max(0.0, min(score, 1.0)) * bins), bins - 1)
        counts[index] += 1
    total = len(scores)
    if total == 0:
        return [0.0] * bins
    return [count / total for count in counts]


def population_stability_index(actual: list[float], expected: list[float]) -> float:
    if len(actual) != len(expected):
        raise ValueError("actual and expected distributions must have equal bins")
    epsilon = 1e-6
    return sum(
        (a - e) * math.log((a + epsilon) / (e + epsilon))
        for a, e in zip(actual, expected, strict=True)
    )


def drift_metric(actual: list[float], expected: list[float], n: int) -> MetricResult:
    if n == 0:
        return MetricResult(
            status="NOT_YET_MEASURABLE",
            n=0,
            minimum_n=100,
            reason="No decided applications exist for drift measurement.",
        )
    if n < 100:
        return MetricResult(
            status="INSUFFICIENT_SAMPLE",
            n=n,
            minimum_n=100,
            reason=f"Insufficient sample (n={n}, minimum 100).",
        )
    return MetricResult(
        status="MEASURED", value=population_stability_index(actual, expected), n=n, minimum_n=100
    )
