"""Human override analytics independent of repayment outcomes."""

from collections import Counter
from typing import Any

from app.services.monitoring.gating import MetricResult


def override_metrics(rows: list[tuple[str | None, str | None]], decisions_n: int) -> dict[str, Any]:
    reasons = Counter(reason or "UNSPECIFIED" for reason, _ in rows)
    analysts = Counter(analyst or "UNASSIGNED" for _, analyst in rows)
    n = len(rows)
    rate = (
        MetricResult(status="MEASURED", value=n / decisions_n, n=decisions_n, minimum_n=1)
        if decisions_n
        else MetricResult(
            status="NOT_YET_MEASURABLE", n=0, minimum_n=1, reason="No decisions exist yet."
        )
    )
    return {
        "rate": rate.model_dump(),
        "by_reason": dict(reasons),
        "by_analyst": dict(analysts),
        "control_chart": [{"period": "current", "rate": rate.value, "n": decisions_n}],
        "interpretation": "A sustained spike on one reason code is a policy bug report.",
        "policy_studio_url": "/policy",
    }
