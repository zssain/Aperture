"""Coverage distribution metrics independent of repayment outcomes."""

from collections import Counter
from typing import Any

from app.services.monitoring.gating import MetricResult


def coverage_distribution(scores: list[int], evidence_reviews: int) -> dict[str, Any]:
    n = len(scores)
    bins = Counter(min(9, max(0, score // 10)) for score in scores)
    share = (
        MetricResult(status="MEASURED", value=evidence_reviews / n, n=n, minimum_n=1)
        if n
        else MetricResult(
            status="NOT_YET_MEASURABLE", n=0, minimum_n=1, reason="No decisions exist yet."
        )
    )
    return {
        "histogram": [{"range": f"{i * 10}-{i * 10 + 9}", "n": bins[i]} for i in range(10)],
        "review_evidence_share": share.model_dump(),
    }
