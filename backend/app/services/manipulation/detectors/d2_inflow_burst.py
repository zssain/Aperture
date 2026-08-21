"""D2 - Pre-application inflow burst.

The moment a lender underwrites on cash flow, an applicant can manufacture a spike right
before applying. Fires when mean daily inflow in the 45 days pre-application is >= K x the
trailing six-month daily mean. Fewer than 30 days of data is INSUFFICIENT_DATA, never
CLEAR - the difference is the whole point.
"""

from datetime import timedelta

from app.models.enums import EventDirection
from app.services.manipulation.base import (
    DetectorResult,
    DetectorStatus,
    Finding,
    format_rupees,
)
from app.services.manipulation.config import get_manipulation_config
from app.services.manipulation.context import ManipulationContext


class _D2InflowBurst:
    detector_id = "D2"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d2"]
        pre_days = int(cfg["pre_days"])
        baseline_days = int(cfg["baseline_days"])
        multiple = float(cfg["burst_multiple"])
        min_days = int(cfg["min_days_required"])

        if not context.events:
            return DetectorResult(self.detector_id, DetectorStatus.INSUFFICIENT_DATA)

        as_of = context.as_of
        span_days = (as_of - min(e.occurred_at for e in context.events)).days
        if span_days < min_days:
            return DetectorResult(self.detector_id, DetectorStatus.INSUFFICIENT_DATA)

        pre_start = as_of - timedelta(days=pre_days)
        base_start = pre_start - timedelta(days=baseline_days)
        credits = [e for e in context.events if e.direction == EventDirection.CREDIT]

        pre = [e for e in credits if pre_start < e.occurred_at <= as_of]
        baseline = [e for e in credits if base_start < e.occurred_at <= pre_start]

        pre_daily = sum(e.amount_paise for e in pre) / pre_days
        base_daily = sum(e.amount_paise for e in baseline) / baseline_days

        # No established baseline inflow: cannot claim a "burst" without inventing one -
        # a brand-new legitimate account would be falsely flagged. Report nothing.
        if base_daily <= 0:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        ratio = pre_daily / base_daily
        if ratio < multiple:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        finding = Finding(
            detector_id=self.detector_id,
            severity="HIGH",
            statement=(
                f"Mean daily inflow in the {pre_days} days pre-application "
                f"({format_rupees(round(pre_daily))}/day) is {ratio:.1f}x the trailing "
                f"6-month mean ({format_rupees(round(base_daily))}/day)."
            ),
            cited_event_ids=tuple(e.event_id for e in pre),
            confidence=round(min(1.0, ratio / (multiple * 2)), 4),
            values={
                "pre_daily_paise": round(pre_daily),
                "baseline_daily_paise": round(base_daily),
                "ratio": round(ratio, 4),
                "pre_days": pre_days,
                "baseline_days": baseline_days,
            },
        )
        return DetectorResult(self.detector_id, DetectorStatus.OK, (finding,))


DETECTOR: _D2InflowBurst = _D2InflowBurst()
