"""D7 - Claimed history vs observed first-transaction age.

If the applicant claims a statement period far longer than the observed transactions can
support, the document's date range was likely stretched. Fires when the claimed span
exceeds the observed first-transaction age by more than the margin. Fewer than 30 days of
observed data is INSUFFICIENT_DATA, not CLEAR.
"""

from app.services.manipulation.base import DetectorResult, DetectorStatus, Finding
from app.services.manipulation.config import get_manipulation_config
from app.services.manipulation.context import ManipulationContext


class _D7AccountAgeMismatch:
    detector_id = "D7"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d7"]
        margin = int(cfg["margin_days"])
        min_days = int(cfg["min_days_required"])

        if not context.events:
            return DetectorResult(self.detector_id, DetectorStatus.INSUFFICIENT_DATA)

        earliest = min(context.events, key=lambda e: e.occurred_at)
        observed_age = (context.as_of - earliest.occurred_at).days
        if observed_age < min_days:
            return DetectorResult(self.detector_id, DetectorStatus.INSUFFICIENT_DATA)

        claimed_start = context.declared.claimed_period_start
        if claimed_start is None:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        claimed_span = (context.as_of - claimed_start).days
        gap = claimed_span - observed_age
        if gap <= margin:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        finding = Finding(
            detector_id=self.detector_id,
            severity="MEDIUM",
            statement=(
                f"Claimed statement period spans {claimed_span} days but the first "
                f"observed transaction is only {observed_age} days old (gap {gap} days "
                f"exceeds the {margin}-day margin)."
            ),
            cited_event_ids=(earliest.event_id,),
            confidence=round(min(1.0, gap / (margin * 2)), 4),
            values={
                "claimed_span_days": claimed_span,
                "observed_age_days": observed_age,
                "gap_days": gap,
                "margin_days": margin,
            },
        )
        return DetectorResult(self.detector_id, DetectorStatus.OK, (finding,))


DETECTOR: _D7AccountAgeMismatch = _D7AccountAgeMismatch()
