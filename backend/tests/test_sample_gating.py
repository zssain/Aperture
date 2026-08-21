import pytest
from app.services.monitoring.gating import MetricResult
from pydantic import ValidationError


def test_unmeasured_metric_rejects_value() -> None:
    with pytest.raises(ValidationError):
        MetricResult(
            status="INSUFFICIENT_SAMPLE",
            value=0.2,
            n=17,
            minimum_n=200,
            reason="too few",
        )


def test_measured_metric_requires_value() -> None:
    with pytest.raises(ValidationError):
        MetricResult(status="MEASURED", n=200, minimum_n=200)
