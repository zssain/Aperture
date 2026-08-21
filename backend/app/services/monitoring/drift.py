"""Population stability index against registered reference distributions."""

import math

from app.services.monitoring.gating import MetricResult


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
