"""Non-production demonstration sequences that still use the real event path."""

from datetime import UTC, datetime, timedelta

from app.models.enums import EventDirection, SourceType
from app.schemas.event import EventCreate


def income_consistency_sequence(
    applicant_ref: str,
    *,
    source_type: SourceType = SourceType.BANK,
    now: datetime | None = None,
) -> list[EventCreate]:
    """Six verified-looking, equal monthly business receipts.

    The generator emits evidence only. Classification, feature values, PD and policy
    outcome are deliberately left to the production engines.
    """
    anchor = now or datetime.now(UTC)
    return [
        EventCreate(
            applicant_ref=applicant_ref,
            source_type=source_type,
            # Stay outside the manipulation engine's 14-day pre-application burst
            # window while retaining six distinct monthly buckets.
            occurred_at=anchor - timedelta(days=30 * month + 16),
            amount_paise=18_000_000 + ((month % 3) - 1) * 137_900,
            direction=EventDirection.CREDIT,
            description=f"Invoice settlement monthly business income {month + 1}",
            counterparty=f"Demo Verified Customer {month + 1}",
            external_id=(
                f"demo-income-consistency-{applicant_ref}-{anchor.date().isoformat()}-{month + 1}"
            ),
        )
        for month in reversed(range(6))
    ]
