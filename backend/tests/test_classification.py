"""Deterministic classification tests."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models.enums import EventDirection
from app.services.classification.rules import CLASSIFIER_VERSION, TxnCategory
from app.services.classification.service import TxnEvent, classify

AS_OF = datetime(2026, 6, 1, tzinfo=UTC)


def _event(
    days_ago: int,
    direction: EventDirection,
    amount_paise: int,
    description: str,
    counterparty: str | None = "CP",
) -> TxnEvent:
    return TxnEvent(
        event_id=uuid.uuid4(),
        occurred_at=AS_OF - timedelta(days=days_ago),
        direction=direction,
        amount_paise=amount_paise,
        balance_paise=None,
        description=description,
        counterparty_hash=counterparty,
        source_connection_id=uuid.uuid4(),
    )


def test_keyword_categories() -> None:
    events = [
        _event(1, EventDirection.CREDIT, 5000000, "Salary credit", "SAL"),
        _event(2, EventDirection.CREDIT, 300000, "Gig payout", "GIG"),
        _event(3, EventDirection.CREDIT, 8000000, "Business settlement", "BIZ"),
        _event(4, EventDirection.DEBIT, 1500000, "Rent debit", "RENT"),
        _event(5, EventDirection.DEBIT, 1200000, "EMI debit", "EMI"),
        _event(6, EventDirection.DEBIT, 200000, "Utility bill", "UTIL"),
        _event(7, EventDirection.DEBIT, 50000, "Mobile recharge", "TEL"),
        _event(8, EventDirection.DEBIT, 40000, "Groceries xyz", "SHOP"),
    ]
    result = classify(events)
    by_desc = {c.event.description: c.category for c in result.events}
    assert by_desc["Salary credit"] is TxnCategory.SALARY
    assert by_desc["Gig payout"] is TxnCategory.GIG_INCOME
    assert by_desc["Business settlement"] is TxnCategory.BUSINESS_INCOME
    assert by_desc["Rent debit"] is TxnCategory.RENT
    assert by_desc["EMI debit"] is TxnCategory.EMI
    assert by_desc["Utility bill"] is TxnCategory.UTILITY
    assert by_desc["Mobile recharge"] is TxnCategory.TELECOM
    assert by_desc["Groceries xyz"] is TxnCategory.OTHER
    assert result.classifier_version == CLASSIFIER_VERSION


def test_is_deterministic_across_runs() -> None:
    events = [
        _event(1, EventDirection.CREDIT, 5000000, "Salary credit", "SAL"),
        _event(4, EventDirection.DEBIT, 1500000, "Rent debit", "RENT"),
        _event(8, EventDirection.DEBIT, 40000, "Mystery", "SHOP"),
    ]
    first = classify(events)
    second = classify(list(reversed(events)))
    assert [(c.category, c.rule_id, c.confidence) for c in first.events] == [
        (c.category, c.rule_id, c.confidence) for c in second.events
    ]


def test_recurrence_reclassifies_unlabelled_credit_as_income() -> None:
    # Three monthly, amount-stable credits with a description that matches no keyword.
    events = [
        _event(5, EventDirection.CREDIT, 4000000, "Inbound xyz", "REPEAT"),
        _event(35, EventDirection.CREDIT, 4050000, "Inbound xyz", "REPEAT"),
        _event(65, EventDirection.CREDIT, 3950000, "Inbound xyz", "REPEAT"),
    ]
    result = classify(events)
    categories = {c.category for c in result.events}
    assert categories == {TxnCategory.GIG_INCOME}
    assert all(c.rule_id == "RECURRENCE_CREDIT" for c in result.events)


def test_transfer_roundtrip_reclassifies_and_signals() -> None:
    events = [
        _event(10, EventDirection.CREDIT, 2000000, "Inbound", "SELF"),
        _event(12, EventDirection.DEBIT, 2000000, "Outbound", "SELF"),
        _event(1, EventDirection.CREDIT, 5000000, "Salary credit", "SAL"),
    ]
    result = classify(events)
    by_cp = {(c.event.counterparty_hash, c.event.direction): c.category for c in result.events}
    assert by_cp[("SELF", EventDirection.CREDIT)] is TxnCategory.TRANSFER_IN
    assert any(s.code == "TRANSFER_ROUNDTRIP" for s in result.signals)


def test_unmatched_event_is_other_with_zero_confidence() -> None:
    result = classify([_event(1, EventDirection.DEBIT, 10000, "???", "X")])
    assert result.events[0].category is TxnCategory.OTHER
    assert result.events[0].confidence == 0.0
