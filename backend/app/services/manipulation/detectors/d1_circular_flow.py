"""D1 - Circular flow. Inflow from counterparty X returned to X within N days.

Money laundered in a loop inflates apparent income without any real economic activity.
Triggers on >= M return cycles OR when the looped value is >= P% of total inflow.
"""

import uuid
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


class _D1CircularFlow:
    detector_id = "D1"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d1"]
        window = int(cfg["window_days"])
        min_cycles = int(cfg["min_cycles"])
        min_pct = float(cfg["min_pct"])

        total_inflow = sum(
            e.amount_paise for e in context.events if e.direction == EventDirection.CREDIT
        )

        by_cp: dict[str, list[LedgerEventView]] = defaultdict(list)
        for event in context.events:
            if event.counterparty_hash:
                by_cp[event.counterparty_hash].append(event)

        findings: list[Finding] = []
        for counterparty, events in sorted(by_cp.items()):
            credits = sorted(
                (e for e in events if e.direction == EventDirection.CREDIT),
                key=lambda e: e.occurred_at,
            )
            debits = sorted(
                (e for e in events if e.direction == EventDirection.DEBIT),
                key=lambda e: e.occurred_at,
            )
            if not credits or not debits:
                continue

            used: set[int] = set()
            cited: list[uuid.UUID] = []
            cycles = 0
            looped_value = 0
            for credit in credits:
                for index, debit in enumerate(debits):
                    if index in used:
                        continue
                    if debit.occurred_at < credit.occurred_at:
                        continue
                    if (debit.occurred_at - credit.occurred_at).days <= window:
                        used.add(index)
                        cycles += 1
                        looped_value += min(credit.amount_paise, debit.amount_paise)
                        cited.extend([credit.event_id, debit.event_id])
                        break

            if cycles == 0:
                continue
            share = looped_value / total_inflow if total_inflow else 0.0
            if cycles < min_cycles and share < min_pct:
                continue

            confidence = min(1.0, max(cycles / min_cycles, share / min_pct if min_pct else 0.0))
            findings.append(
                Finding(
                    detector_id=self.detector_id,
                    severity="HIGH",
                    statement=(
                        f"Counterparty {counterparty[:8]}: {cycles} inflow->return "
                        f"cycles totalling {format_rupees(looped_value)} within "
                        f"{window} days ({share:.0%} of total inflow "
                        f"{format_rupees(total_inflow)})."
                    ),
                    cited_event_ids=tuple(cited),
                    confidence=round(confidence, 4),
                    values={
                        "counterparty": counterparty,
                        "cycles": cycles,
                        "looped_value_paise": looped_value,
                        "total_inflow_paise": total_inflow,
                        "share": round(share, 4),
                    },
                )
            )

        return DetectorResult(self.detector_id, DetectorStatus.OK, tuple(findings))


DETECTOR: _D1CircularFlow = _D1CircularFlow()
