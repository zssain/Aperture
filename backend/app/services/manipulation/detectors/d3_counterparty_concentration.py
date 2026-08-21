"""D3 - Counterparty concentration for declared gig/self-employed income.

A salaried applicant with one employer is normal, so this only fires when the applicant
DECLARED gig/self-employed income (which should be diversified across payers) yet a single
counterparty is >= 80% of inflow value - a single fabricated payer dressed up as gig work.
"""

from collections import defaultdict

from app.models.enums import EventDirection
from app.services.manipulation.base import (
    DetectorResult,
    DetectorStatus,
    Finding,
    format_rupees,
)
from app.services.manipulation.config import get_manipulation_config
from app.services.manipulation.context import LedgerEventView, ManipulationContext


class _D3CounterpartyConcentration:
    detector_id = "D3"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d3"]
        pct = float(cfg["concentration_pct"])
        gig_occupations = {str(o).upper() for o in cfg["gig_occupations"]}

        occupation = (context.declared.occupation or "").upper()
        if occupation not in gig_occupations:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        credits = [
            e
            for e in context.events
            if e.direction == EventDirection.CREDIT and e.counterparty_hash
        ]
        total = sum(e.amount_paise for e in credits)
        if total <= 0:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        by_cp_value: dict[str, int] = defaultdict(int)
        by_cp_events: dict[str, list[LedgerEventView]] = defaultdict(list)
        for event in credits:
            assert event.counterparty_hash is not None
            by_cp_value[event.counterparty_hash] += event.amount_paise
            by_cp_events[event.counterparty_hash].append(event)

        top = max(by_cp_value, key=lambda k: by_cp_value[k])
        share = by_cp_value[top] / total
        if share < pct:
            return DetectorResult(self.detector_id, DetectorStatus.OK)

        finding = Finding(
            detector_id=self.detector_id,
            severity="MEDIUM",
            statement=(
                f"One counterparty is {share:.0%} of inflow value "
                f"({format_rupees(by_cp_value[top])} of {format_rupees(total)}) while "
                f"occupation is declared {occupation}."
            ),
            cited_event_ids=tuple(e.event_id for e in by_cp_events[top]),
            confidence=round(share, 4),
            values={
                "counterparty": top,
                "counterparty_value_paise": by_cp_value[top],
                "total_inflow_paise": total,
                "share": round(share, 4),
                "occupation": occupation,
            },
        )
        return DetectorResult(self.detector_id, DetectorStatus.OK, (finding,))


DETECTOR: _D3CounterpartyConcentration = _D3CounterpartyConcentration()
