"""Gated subgroup outcome rates."""

import math
from collections import defaultdict

from app.services.monitoring.gating import MetricResult

MINIMUM_SUBGROUP_N = 200


def disparity_metrics(
    rows: list[tuple[str, str, int]], minimum_n: int = MINIMUM_SUBGROUP_N
) -> dict[str, dict[str, MetricResult]]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for attribute, subgroup, adverse in rows:
        groups[(attribute, subgroup)].append(adverse)
    result: dict[str, dict[str, MetricResult]] = defaultdict(dict)
    for (attribute, subgroup), labels in groups.items():
        n = len(labels)
        if n < minimum_n:
            metric = MetricResult(
                status="INSUFFICIENT_SAMPLE",
                n=n,
                minimum_n=minimum_n,
                reason=f"Insufficient sample (n={n}, minimum {minimum_n}).",
            )
        else:
            value = sum(labels) / n
            se = math.sqrt(value * (1 - value) / n)
            metric = MetricResult(
                status="MEASURED",
                value=value,
                ci_low=max(0, value - 1.96 * se),
                ci_high=min(1, value + 1.96 * se),
                n=n,
                minimum_n=minimum_n,
            )
        result[attribute][subgroup] = metric
    return dict(result)
