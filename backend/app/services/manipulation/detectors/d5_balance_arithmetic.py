"""D5 - Balance arithmetic. The running balance must reconcile with the transactions.

Hand-edited statements almost always leave the running balance inconsistent with the
signed transaction sequence. Each step is checked: prior balance + signed amount must
equal the new balance within a rounding tolerance. No balance column at all is
INSUFFICIENT_DATA, not CLEAR.
"""

from itertools import pairwise

from app.models.enums import EventDirection
from app.services.manipulation.base import (
    DetectorResult,
    DetectorStatus,
    Finding,
    format_rupees,
)
from app.services.manipulation.config import get_manipulation_config
from app.services.manipulation.context import ManipulationContext


class _D5BalanceArithmetic:
    detector_id = "D5"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d5"]
        tolerance = int(cfg["tolerance_paise"])

        sequence = sorted(
            (e for e in context.events if e.balance_paise is not None),
            key=lambda e: (e.occurred_at, str(e.event_id)),
        )
        if not sequence:
            return DetectorResult(self.detector_id, DetectorStatus.INSUFFICIENT_DATA)

        findings: list[Finding] = []
        for prev, cur in pairwise(sequence):
            assert prev.balance_paise is not None and cur.balance_paise is not None
            signed = (
                cur.amount_paise if cur.direction == EventDirection.CREDIT else -cur.amount_paise
            )
            expected = prev.balance_paise + signed
            drift = cur.balance_paise - expected
            if abs(drift) <= tolerance:
                continue

            operator = "plus" if signed >= 0 else "minus"
            findings.append(
                Finding(
                    detector_id=self.detector_id,
                    severity="HIGH",
                    statement=(
                        f"Running balance reads {format_rupees(cur.balance_paise)} but the "
                        f"prior balance {format_rupees(prev.balance_paise)} {operator} the "
                        f"transaction {format_rupees(abs(cur.amount_paise))} implies "
                        f"{format_rupees(expected)} (off by {format_rupees(drift)})."
                    ),
                    cited_event_ids=(prev.event_id, cur.event_id),
                    confidence=1.0,
                    values={
                        "prior_balance_paise": prev.balance_paise,
                        "amount_paise": cur.amount_paise,
                        "direction": cur.direction.value,
                        "expected_balance_paise": expected,
                        "actual_balance_paise": cur.balance_paise,
                        "drift_paise": drift,
                    },
                )
            )

        return DetectorResult(self.detector_id, DetectorStatus.OK, tuple(findings))


DETECTOR: _D5BalanceArithmetic = _D5BalanceArithmetic()
