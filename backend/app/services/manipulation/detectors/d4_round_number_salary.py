"""D4 - Round-number pseudo-salary (both conditions required).

A fabricated salary tends to be tidy round numbers, but real payroll also lands on a
consistent date. So this fires ONLY when >= 80% of income-classified credits are exact
multiples of Rs 5,000 AND their pay-day varies more than a real salary would - both, or
neither. Real payroll (round but regular) and lumpy gig income (irregular but not round)
both survive.
"""

from statistics import pstdev

from app.models.enums import EventDirection
from app.services.manipulation.base import (
    DetectorResult,
    DetectorStatus,
    Finding,
)
from app.services.manipulation.config import get_manipulation_config
from app.services.manipulation.context import ManipulationContext


class _D4RoundNumberSalary:
    detector_id = "D4"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d4"]
        multiple = int(cfg["multiple_paise"])
        min_share = float(cfg["min_round_share"])
        min_credits = int(cfg["min_income_credits"])
        variance_threshold = float(cfg["salary_date_variance_days"])

        income = [
            e
            for e in context.events
            if e.event_id in context.income_event_ids and e.direction == EventDirection.CREDIT
        ]
        if len(income) < min_credits:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        round_credits = [e for e in income if e.amount_paise > 0 and e.amount_paise % multiple == 0]
        share = len(round_credits) / len(income)
        if share < min_share:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        pay_days = [e.occurred_at.day for e in income]
        variance = pstdev(pay_days) if len(pay_days) > 1 else 0.0
        if variance <= variance_threshold:
            # Round but regular -> a genuine salary, not a manufactured one.
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        finding = Finding(
            detector_id=self.detector_id,
            severity="MEDIUM",
            statement=(
                f"{len(round_credits)} of {len(income)} income credits ({share:.0%}) are "
                f"exact multiples of ₹5,000 and their pay-day varies by {variance:.1f} "
                f"days (> {variance_threshold}), unlike a real salary."
            ),
            cited_event_ids=tuple(e.event_id for e in income),
            confidence=round(share, 4),
            values={
                "income_credits": len(income),
                "round_credits": len(round_credits),
                "round_share": round(share, 4),
                "pay_day_variance_days": round(variance, 4),
                "variance_threshold_days": variance_threshold,
            },
        )
        return DetectorResult(self.detector_id, DetectorStatus.OK, (finding,))


DETECTOR: _D4RoundNumberSalary = _D4RoundNumberSalary()
