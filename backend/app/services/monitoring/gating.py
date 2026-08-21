"""The sole numeric result contract used by monitoring."""

from typing import Literal, Self

from pydantic import BaseModel, model_validator


class MetricResult(BaseModel):
    status: Literal["MEASURED", "INSUFFICIENT_SAMPLE", "NOT_YET_MEASURABLE"]
    value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n: int
    minimum_n: int
    reason: str | None = None
    projected_date: str | None = None

    @model_validator(mode="after")
    def validate_gating(self) -> Self:
        if self.status != "MEASURED" and any(
            value is not None for value in (self.value, self.ci_low, self.ci_high)
        ):
            raise ValueError("unmeasured metrics cannot carry a value or confidence interval")
        if self.status == "MEASURED" and self.value is None:
            raise ValueError("measured metrics require a value")
        if self.status != "MEASURED" and not self.reason:
            raise ValueError("unmeasured metrics require a reason")
        return self


def gated(value: float | None, *, n: int, minimum_n: int, reason: str) -> MetricResult:
    if value is None:
        return MetricResult(status="NOT_YET_MEASURABLE", n=n, minimum_n=minimum_n, reason=reason)
    if n < minimum_n:
        return MetricResult(
            status="INSUFFICIENT_SAMPLE",
            n=n,
            minimum_n=minimum_n,
            reason=f"Insufficient sample (n={n}, minimum {minimum_n}).",
        )
    return MetricResult(status="MEASURED", value=value, n=n, minimum_n=minimum_n)
