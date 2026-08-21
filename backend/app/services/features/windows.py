"""Rolling-window and numeric helpers for feature computation.

A "month" is a fixed 30-day bucket ending at ``as_of`` (bucket 0 = most recent 30
days). Only buckets that actually contain events are considered "covered" — a month
with no events at all is a data gap and is never imputed as zero.
"""

from collections.abc import Callable
from datetime import datetime

from app.services.classification.service import ClassifiedEvent

MONTH_DAYS = 30


def bucket_of(occurred_at: datetime, as_of: datetime) -> int:
    return (as_of - occurred_at).days // MONTH_DAYS


def months_observed(events: list[ClassifiedEvent], as_of: datetime) -> int:
    if not events:
        return 0
    first = min(item.event.occurred_at for item in events)
    return (as_of - first).days // MONTH_DAYS + 1


def covered_buckets(events: list[ClassifiedEvent], as_of: datetime, months: int) -> list[int]:
    """Buckets (< ``months``) that contain at least one event, most-recent first."""
    present = {
        bucket_of(item.event.occurred_at, as_of)
        for item in events
        if 0 <= bucket_of(item.event.occurred_at, as_of) < months
    }
    return sorted(present)


def monthly_totals(
    events: list[ClassifiedEvent],
    as_of: datetime,
    months: int,
    predicate: Callable[[ClassifiedEvent], bool],
) -> tuple[dict[int, int], list[str]]:
    """Per covered bucket, the summed paise of events matching ``predicate``.

    Every covered bucket is present in the result (0 if nothing matched — an observed
    zero for a month we have coverage for, not an imputed one). Returns the per-bucket
    totals and the contributing event id strings.
    """
    buckets = covered_buckets(events, as_of, months)
    totals: dict[int, int] = dict.fromkeys(buckets, 0)
    lineage: list[str] = []
    for item in events:
        bucket = bucket_of(item.event.occurred_at, as_of)
        if bucket in totals and predicate(item):
            totals[bucket] += item.event.amount_paise
            lineage.append(str(item.event.event_id))
    return totals, lineage


def median_int(values: list[int]) -> int:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2)


def percentile_int(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (percentile / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return round(ordered[low] + (ordered[high] - ordered[low]) * frac)


def coefficient_of_variation(values: list[int], mean_floor: float) -> float | None:
    """Population CV, or None when the mean is below the floor (no blow-up)."""
    if not values:
        return None
    mean = sum(values) / len(values)
    if mean < mean_floor:
        return None
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return float(variance**0.5) / mean


def clamp(value: float, low: float, high: float) -> tuple[float, bool]:
    if value < low:
        return low, True
    if value > high:
        return high, True
    return value, False
