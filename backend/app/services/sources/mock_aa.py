"""Mock Account-Aggregator adapter — a SIMULATED provider behind a real interface.

It generates *behaviour* (salary/gig/business inflows, rent, EMI, utilities, merchant
spend) deterministically from a per-applicant seed, NOT target feature values — every
feature must be derived from these events later, so the traceability chain is real.
The same applicant + period yields byte-identical events across runs and processes.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.models.enums import EventDirection, SourceTier, SourceType
from app.models.source import SourceConnection
from app.services.sources.base import (
    FetchPeriod,
    NormalizedEvent,
    ProviderError,
    ProviderTimeoutError,
    RawSourcePayload,
)

_MERCHANTS = ("Zomato", "Swiggy", "Amazon", "BigBasket", "Uber")
_PERSONAS = ("SALARIED", "GIG", "BUSINESS")


@dataclass(frozen=True)
class _Txn:
    txn_id: str
    value_date: str
    txn_type: str
    amount: str
    narration: str
    merchant: str
    current_balance: str


class MockAccountAggregatorAdapter:
    """Deterministic simulated AA. ``failure_mode`` injects provider faults for tests."""

    source_type: SourceType = SourceType.BANK
    tier: SourceTier = SourceTier.AA_VERIFIED

    def __init__(self, failure_mode: str | None = None) -> None:
        self._failure_mode = failure_mode

    async def fetch(self, connection: SourceConnection, period: FetchPeriod) -> RawSourcePayload:
        if self._failure_mode == "timeout":
            raise ProviderTimeoutError("mock AA provider timed out")
        if self._failure_mode == "error":
            raise ProviderError("mock AA provider error")

        effective_end = period.end
        if self._failure_mode == "partial":
            effective_end = period.start + (period.end - period.start) / 2

        transactions = self._generate(connection.applicant_id, period.start, effective_end)
        return RawSourcePayload(
            provider="MockAA",
            account_ref=str(connection.id),
            period=period,
            raw={
                "transactions": [t.__dict__ for t in transactions],
                "covered_to": effective_end.isoformat(),
            },
        )

    def normalize(self, payload: RawSourcePayload) -> list[NormalizedEvent]:
        events: list[NormalizedEvent] = []
        transactions: list[dict[str, Any]] = payload.raw["transactions"]
        for txn in transactions:
            events.append(
                NormalizedEvent(
                    occurred_at=datetime.fromisoformat(txn["value_date"]),
                    direction=(
                        EventDirection.CREDIT
                        if txn["txn_type"] == "CREDIT"
                        else EventDirection.DEBIT
                    ),
                    amount_paise=_to_paise(txn["amount"]),
                    description=txn["narration"],
                    counterparty=txn["merchant"],
                    balance_paise=_to_paise(txn["current_balance"]),
                    external_id=txn["txn_id"],
                )
            )
        return events

    def _generate(self, applicant_id: uuid.UUID, start: datetime, end: datetime) -> list[_Txn]:
        rng = random.Random(applicant_id.int % (2**32))
        persona = _PERSONAS[applicant_id.int % 3]
        transactions: list[_Txn] = []
        state = {"balance": 20_000_00, "index": 0}
        start_date, end_date = start.date(), end.date()

        def add(when: date, txn_type: str, paise: int, narration: str, merchant: str) -> None:
            if not (start_date <= when <= end_date):
                return
            state["balance"] += paise if txn_type == "CREDIT" else -paise
            transactions.append(
                _Txn(
                    txn_id=f"MOCKAA-{applicant_id.hex[:8]}-{state['index']:05d}",
                    value_date=f"{when.isoformat()}T10:00:00+00:00",
                    txn_type=txn_type,
                    amount=f"{paise / 100:.2f}",
                    narration=narration,
                    merchant=merchant,
                    current_balance=f"{state['balance'] / 100:.2f}",
                )
            )
            state["index"] += 1

        month = date(start.year, start.month, 1)
        while month <= end_date:
            year, mon = month.year, month.month

            if persona == "SALARIED":
                add(
                    _clamp_day(year, mon, 1 + rng.randint(0, 2)),
                    "CREDIT",
                    5_000_000 + rng.randint(-50_000, 50_000),
                    "Salary credit",
                    "ACME PAYROLL",
                )
            elif persona == "GIG":
                for _ in range(rng.randint(6, 10)):
                    add(
                        _clamp_day(year, mon, rng.randint(1, 27)),
                        "CREDIT",
                        300_000 + rng.randint(-100_000, 200_000),
                        "Gig payout",
                        "GIG PLATFORM",
                    )
            else:
                for _ in range(rng.randint(2, 4)):
                    add(
                        _clamp_day(year, mon, rng.randint(1, 27)),
                        "CREDIT",
                        8_000_000 + rng.randint(-2_000_000, 3_000_000),
                        "Business inflow",
                        "CLIENT SETTLEMENT",
                    )

            rent = 1_500_000 + rng.randint(-20_000, 20_000)
            emi = 1_200_000 + rng.randint(-10_000, 10_000)
            utility = 200_000 + rng.randint(-50_000, 50_000)
            add(_clamp_day(year, mon, 5), "DEBIT", rent, "Rent debit", "URBAN RENTALS")
            add(_clamp_day(year, mon, 7), "DEBIT", emi, "EMI debit", "HDFC EMI")
            add(_clamp_day(year, mon, 12), "DEBIT", utility, "Utility bill", "BESCOM")
            for _ in range(rng.randint(8, 15)):
                add(
                    _clamp_day(year, mon, rng.randint(1, 27)),
                    "DEBIT",
                    rng.randint(15_000, 250_000),
                    "UPI debit",
                    rng.choice(_MERCHANTS),
                )

            month = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)

        transactions.sort(key=lambda t: (t.value_date, t.txn_id))
        return transactions


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(28, max(1, day)))


def _to_paise(rupees: str) -> int:
    return round(float(rupees) * 100)
