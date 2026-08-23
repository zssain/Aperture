"""THE feature registry — the single, versioned definition of every feature.

Each feature declares its metadata and a pure ``compute`` function. Money stays in
integer paise; the only float outputs are explicitly-declared ratio features. Missing
data yields NULL with a reason — never a zero, never an imputed value.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import ClassificationMethod, EventDirection
from app.services.classification.rules import (
    INCOME_CATEGORIES,
    TxnCategory,
)
from app.services.classification.service import ClassifiedEvent
from app.services.features.windows import (
    clamp,
    coefficient_of_variation,
    covered_buckets,
    median_int,
    monthly_totals,
    months_observed,
    percentile_int,
)

# --- Null reasons (facts, distinguished) ---
NO_EVENTS = "no_events"
INSUFFICIENT_HISTORY = "insufficient_history"
NO_INCOME_OBSERVED = "no_income_observed"
NO_EMIS_OBSERVED = "no_emis_observed"
NO_ESSENTIAL_OBSERVED = "no_essential_expense_observed"
NO_UTILITY_OBSERVED = "no_utility_observed"
NO_TELECOM_OBSERVED = "no_telecom_observed"
NO_BALANCE_DATA = "no_balance_data"
MEAN_BELOW_FLOOR = "mean_below_floor"
NO_BUREAU_DATA = "no_bureau_data"

# CV is undefined below this monthly-inflow mean (avoids a division blow-up).
CV_MEAN_FLOOR_PAISE = 100_000  # ₹1,000

_MONEY_RANGE = (0.0, 100_000_000_000.0)
_BALANCE_RANGE = (-100_000_000_000.0, 100_000_000_000.0)


@dataclass(frozen=True)
class FeatureResult:
    value: float | int | None
    null_reason: str | None = None
    lineage: list[str] = field(default_factory=list)
    clamped: bool = False


@dataclass(frozen=True)
class BureauRecord:
    """The latest credit-bureau reading for an applicant, when one exists. Distinct from
    cash-flow evidence; populated from a BUREAU_RECORD ledger event's payload. Any field
    may be None (the bureau returned no value for it)."""

    event_id: str
    score: int | None = None
    active_loans: int | None = None
    delinquencies_12m: int | None = None


@dataclass(frozen=True)
class FeatureContext:
    as_of: datetime
    events: list[ClassifiedEvent]
    # None when the applicant has no bureau file (the common thin-file case).
    bureau: BureauRecord | None = None


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    version: str
    dtype: str  # "int" | "float"
    window: str
    formula_doc: str
    null_policy: str
    monotonic_direction: str  # "higher_better" | "lower_better" | "none"
    allowed_range: tuple[float, float]
    compute: Callable[[FeatureContext], FeatureResult]


# --------------------------------------------------------------------------- #
# Predicates / small helpers
# --------------------------------------------------------------------------- #
def _is_income(item: ClassifiedEvent) -> bool:
    return item.category in INCOME_CATEGORIES and item.event.direction == EventDirection.CREDIT


def _is_category(item: ClassifiedEvent, category: TxnCategory) -> bool:
    return item.category is category and item.event.direction == EventDirection.DEBIT


def _ids(items: list[ClassifiedEvent]) -> list[str]:
    return [str(i.event.event_id) for i in items]


def _income_items(ctx: FeatureContext) -> list[ClassifiedEvent]:
    return [i for i in ctx.events if _is_income(i)]


def _null(reason: str) -> FeatureResult:
    return FeatureResult(value=None, null_reason=reason)


# --------------------------------------------------------------------------- #
# Feature compute functions
# --------------------------------------------------------------------------- #
def _history_depth_days(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return FeatureResult(value=0, lineage=[])  # zero events → 0, never null
    earliest = min(ctx.events, key=lambda i: i.event.occurred_at)
    days = (ctx.as_of - earliest.event.occurred_at).days
    return FeatureResult(value=max(0, days), lineage=[str(earliest.event.event_id)])


def _monthly_income_series(ctx: FeatureContext, months: int) -> tuple[list[int], list[str]] | None:
    """(per-covered-bucket income totals, contributing ids), or None when unusable."""
    if not ctx.events:
        return None
    if not _income_items(ctx):
        return None
    if months_observed(ctx.events, ctx.as_of) < 2:
        return None
    totals, lineage = monthly_totals(ctx.events, ctx.as_of, months, _is_income)
    series = [totals[b] for b in covered_buckets(ctx.events, ctx.as_of, months)]
    # Income exists historically but none falls within the window → not usable.
    if not series or not lineage:
        return None
    return series, lineage


def _median_monthly_inflow(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _income_items(ctx):
        return _null(NO_INCOME_OBSERVED)
    series = _monthly_income_series(ctx, 6)
    if series is None:
        return _null(INSUFFICIENT_HISTORY)
    values, lineage = series
    return FeatureResult(value=median_int(values), lineage=lineage)


def _p25_monthly_inflow(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _income_items(ctx):
        return _null(NO_INCOME_OBSERVED)
    series = _monthly_income_series(ctx, 6)
    if series is None:
        return _null(INSUFFICIENT_HISTORY)
    values, lineage = series
    return FeatureResult(value=percentile_int(values, 25), lineage=lineage)


def _monthly_inflow_cv(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _income_items(ctx):
        return _null(NO_INCOME_OBSERVED)
    series = _monthly_income_series(ctx, 6)
    if series is None:
        return _null(INSUFFICIENT_HISTORY)
    values, lineage = series
    cv = coefficient_of_variation(values, CV_MEAN_FLOOR_PAISE)
    if cv is None:
        return _null(MEAN_BELOW_FLOOR)
    clamped_value, was_clamped = clamp(cv, 0.0, 10.0)
    return FeatureResult(value=clamped_value, lineage=lineage, clamped=was_clamped)


def _inflow_trend_ratio(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _income_items(ctx):
        return _null(NO_INCOME_OBSERVED)
    if months_observed(ctx.events, ctx.as_of) < 4:
        return _null(INSUFFICIENT_HISTORY)
    totals, lineage = monthly_totals(ctx.events, ctx.as_of, 6, _is_income)
    recent = sum(totals.get(b, 0) for b in (0, 1, 2))
    prior = sum(totals.get(b, 0) for b in (3, 4, 5))
    if prior < CV_MEAN_FLOOR_PAISE:
        return _null(MEAN_BELOW_FLOOR)
    ratio, was_clamped = clamp(recent / prior, 0.0, 5.0)
    return FeatureResult(value=ratio, lineage=lineage, clamped=was_clamped)


def _inflow_source_count(ctx: FeatureContext) -> FeatureResult:
    income = _income_items(ctx)
    if not ctx.events:
        return _null(NO_EVENTS)
    if not income:
        return _null(NO_INCOME_OBSERVED)
    sources = {i.event.counterparty_hash for i in income if i.event.counterparty_hash}
    return FeatureResult(value=len(sources), lineage=_ids(income))


def _income_months_observed(ctx: FeatureContext) -> FeatureResult:
    income = _income_items(ctx)
    if not ctx.events:
        return _null(NO_EVENTS)
    if not income:
        return _null(NO_INCOME_OBSERVED)
    buckets = {i.event.occurred_at for i in income}
    from app.services.features.windows import bucket_of

    months = {bucket_of(t, ctx.as_of) for t in buckets}
    return FeatureResult(value=len(months), lineage=_ids(income))


def _total_inflow_6m(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _income_items(ctx):
        return _null(NO_INCOME_OBSERVED)
    totals, lineage = monthly_totals(ctx.events, ctx.as_of, 6, _is_income)
    if not lineage:  # income exists, but none within the 6-month window
        return _null(INSUFFICIENT_HISTORY)
    return FeatureResult(value=sum(totals.values()), lineage=lineage)


def _category_share(category: TxnCategory) -> Callable[[FeatureContext], FeatureResult]:
    def compute(ctx: FeatureContext) -> FeatureResult:
        income = _income_items(ctx)
        if not ctx.events:
            return _null(NO_EVENTS)
        if not income:
            return _null(NO_INCOME_OBSERVED)
        total = sum(i.event.amount_paise for i in income)
        if total == 0:
            return _null(NO_INCOME_OBSERVED)
        matched = [i for i in income if i.category is category]
        share = sum(i.event.amount_paise for i in matched) / total
        value, was_clamped = clamp(share, 0.0, 1.0)
        return FeatureResult(value=value, lineage=_ids(income), clamped=was_clamped)

    return compute


def _essential_items(ctx: FeatureContext, category: TxnCategory) -> list[ClassifiedEvent]:
    return [i for i in ctx.events if _is_category(i, category)]


def _monthly_median_expense(
    ctx: FeatureContext, category: TxnCategory, months: int, reason: str
) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    items = _essential_items(ctx, category)
    if not items:
        return _null(reason)
    totals, lineage = monthly_totals(
        ctx.events, ctx.as_of, months, lambda i: _is_category(i, category)
    )
    series = [totals[b] for b in covered_buckets(ctx.events, ctx.as_of, months) if totals[b] > 0]
    if not series:
        return _null(reason)
    return FeatureResult(value=median_int(series), lineage=lineage)


def _monthly_emi_paise(ctx: FeatureContext) -> FeatureResult:
    return _monthly_median_expense(ctx, TxnCategory.EMI, 3, NO_EMIS_OBSERVED)


def _essential_expense_paise(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    essential = [
        i
        for i in ctx.events
        if i.category
        in (TxnCategory.RENT, TxnCategory.EMI, TxnCategory.UTILITY, TxnCategory.TELECOM)
        and i.event.direction == EventDirection.DEBIT
    ]
    if not essential:
        return _null(NO_ESSENTIAL_OBSERVED)
    totals, lineage = monthly_totals(
        ctx.events,
        ctx.as_of,
        3,
        lambda i: (
            i.category
            in (TxnCategory.RENT, TxnCategory.EMI, TxnCategory.UTILITY, TxnCategory.TELECOM)
            and i.event.direction == EventDirection.DEBIT
        ),
    )
    series = [totals[b] for b in covered_buckets(ctx.events, ctx.as_of, 3) if totals[b] > 0]
    if not series:
        return _null(NO_ESSENTIAL_OBSERVED)
    return FeatureResult(value=median_int(series), lineage=lineage)


def _debt_service_ratio(ctx: FeatureContext) -> FeatureResult:
    emi = _monthly_emi_paise(ctx)
    inflow = _median_monthly_inflow(ctx)
    if emi.value is None:
        return _null(emi.null_reason or NO_EMIS_OBSERVED)
    if inflow.value is None:
        return _null(inflow.null_reason or NO_INCOME_OBSERVED)
    assert isinstance(emi.value, int) and isinstance(inflow.value, int)
    if inflow.value <= 0:
        return _null(NO_INCOME_OBSERVED)
    ratio, was_clamped = clamp(emi.value / inflow.value, 0.0, 2.0)
    return FeatureResult(value=ratio, lineage=emi.lineage + inflow.lineage, clamped=was_clamped)


def _essential_expense_ratio(ctx: FeatureContext) -> FeatureResult:
    essential = _essential_expense_paise(ctx)
    inflow = _median_monthly_inflow(ctx)
    if essential.value is None:
        return _null(essential.null_reason or NO_ESSENTIAL_OBSERVED)
    if inflow.value is None:
        return _null(inflow.null_reason or NO_INCOME_OBSERVED)
    assert isinstance(essential.value, int) and isinstance(inflow.value, int)
    if inflow.value <= 0:
        return _null(NO_INCOME_OBSERVED)
    ratio, was_clamped = clamp(essential.value / inflow.value, 0.0, 3.0)
    return FeatureResult(
        value=ratio, lineage=essential.lineage + inflow.lineage, clamped=was_clamped
    )


def _balance_items(ctx: FeatureContext, months: int) -> list[ClassifiedEvent]:
    from app.services.features.windows import bucket_of

    return [
        i
        for i in ctx.events
        if i.event.balance_paise is not None
        and 0 <= bucket_of(i.event.occurred_at, ctx.as_of) < months
    ]


def _mean_balance_paise(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    items = _balance_items(ctx, 3)
    if not items:
        return _null(NO_BALANCE_DATA)
    balances = [i.event.balance_paise for i in items if i.event.balance_paise is not None]
    return FeatureResult(value=round(sum(balances) / len(balances)), lineage=_ids(items))


def _min_balance_paise(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    items = _balance_items(ctx, 3)
    if not items:
        return _null(NO_BALANCE_DATA)
    balances = [i.event.balance_paise for i in items if i.event.balance_paise is not None]
    return FeatureResult(value=min(balances), lineage=_ids(items))


def _balance_min_to_mean_ratio(ctx: FeatureContext) -> FeatureResult:
    mean = _mean_balance_paise(ctx)
    minimum = _min_balance_paise(ctx)
    if mean.value is None or minimum.value is None:
        return _null(NO_BALANCE_DATA)
    assert isinstance(mean.value, int) and isinstance(minimum.value, int)
    if mean.value <= 0:
        return _null(NO_BALANCE_DATA)
    ratio, was_clamped = clamp(minimum.value / mean.value, 0.0, 1.0)
    return FeatureResult(value=ratio, lineage=mean.lineage, clamped=was_clamped)


def _expense_cover_months(ctx: FeatureContext) -> FeatureResult:
    mean_balance = _mean_balance_paise(ctx)
    essential = _essential_expense_paise(ctx)
    if mean_balance.value is None:
        return _null(NO_BALANCE_DATA)
    if essential.value is None:
        return _null(essential.null_reason or NO_ESSENTIAL_OBSERVED)
    assert isinstance(mean_balance.value, int) and isinstance(essential.value, int)
    if essential.value <= 0:
        return _null(NO_ESSENTIAL_OBSERVED)
    months, was_clamped = clamp(mean_balance.value / essential.value, 0.0, 60.0)
    return FeatureResult(
        value=months, lineage=mean_balance.lineage + essential.lineage, clamped=was_clamped
    )


def _covered_category_months(ctx: FeatureContext, category: TxnCategory, months: int) -> set[int]:
    from app.services.features.windows import bucket_of

    return {
        bucket_of(i.event.occurred_at, ctx.as_of)
        for i in ctx.events
        if _is_category(i, category) and 0 <= bucket_of(i.event.occurred_at, ctx.as_of) < months
    }


def _utility_payment_ratio(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _essential_items(ctx, TxnCategory.UTILITY):
        return _null(NO_UTILITY_OBSERVED)
    covered = covered_buckets(ctx.events, ctx.as_of, 6)
    if not covered:
        return _null(NO_EVENTS)
    paid = _covered_category_months(ctx, TxnCategory.UTILITY, 6)
    lineage = _ids([i for i in ctx.events if _is_category(i, TxnCategory.UTILITY)])
    ratio, was_clamped = clamp(len(paid) / len(covered), 0.0, 1.0)
    return FeatureResult(value=ratio, lineage=lineage, clamped=was_clamped)


def _utility_ontime_streak(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _essential_items(ctx, TxnCategory.UTILITY):
        return _null(NO_UTILITY_OBSERVED)
    paid = _covered_category_months(ctx, TxnCategory.UTILITY, 12)
    streak = 0
    while streak in paid:
        streak += 1
    lineage = _ids([i for i in ctx.events if _is_category(i, TxnCategory.UTILITY)])
    return FeatureResult(value=streak, lineage=lineage)


def _telecom_continuity_months(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    if not _essential_items(ctx, TxnCategory.TELECOM):
        return _null(NO_TELECOM_OBSERVED)
    months = _covered_category_months(ctx, TxnCategory.TELECOM, 12)
    lineage = _ids([i for i in ctx.events if _is_category(i, TxnCategory.TELECOM)])
    return FeatureResult(value=len(months), lineage=lineage)


def _source_diversity(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    sources = {
        i.event.source_connection_id for i in ctx.events if i.event.source_connection_id is not None
    }
    return FeatureResult(value=max(1, len(sources)), lineage=_ids(ctx.events))


def _other_share(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    other = [i for i in ctx.events if i.category is TxnCategory.OTHER]
    value, was_clamped = clamp(len(other) / len(ctx.events), 0.0, 1.0)
    return FeatureResult(value=value, lineage=_ids(other), clamped=was_clamped)


def _txn_density_per_month(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    months = max(1, months_observed(ctx.events, ctx.as_of))
    value, was_clamped = clamp(len(ctx.events) / months, 0.0, 10_000.0)
    return FeatureResult(value=value, lineage=_ids(ctx.events), clamped=was_clamped)


def _unclassified_inflow_share(ctx: FeatureContext) -> FeatureResult:
    inflows = [i for i in ctx.events if i.event.direction == EventDirection.CREDIT]
    if not ctx.events:
        return _null(NO_EVENTS)
    if not inflows:
        return _null(NO_INCOME_OBSERVED)
    total = sum(item.event.amount_paise for item in inflows)
    if total <= 0:
        return _null(NO_INCOME_OBSERVED)
    unknown = [
        item for item in inflows if item.classification_method is ClassificationMethod.UNCLASSIFIED
    ]
    value, clamped = clamp(sum(item.event.amount_paise for item in unknown) / total, 0.0, 1.0)
    return FeatureResult(value=value, lineage=_ids(inflows), clamped=clamped)


def _vector_classified_share(ctx: FeatureContext) -> FeatureResult:
    if not ctx.events:
        return _null(NO_EVENTS)
    matched = [
        item for item in ctx.events if item.classification_method is ClassificationMethod.VECTOR_KNN
    ]
    value, clamped = clamp(len(matched) / len(ctx.events), 0.0, 1.0)
    return FeatureResult(value=value, lineage=_ids(matched), clamped=clamped)


def _bureau_field(
    field: str, reason: str
) -> Callable[[FeatureContext], FeatureResult]:
    """Read one field from the applicant's bureau record. Absent record OR a field the
    bureau didn't return stays null-with-reason (never coerced to 0), and cites the
    bureau event when present so the value is traceable."""

    def compute(ctx: FeatureContext) -> FeatureResult:
        if ctx.bureau is None:
            return _null(reason)
        value = getattr(ctx.bureau, field)
        if value is None:
            return _null(reason)
        return FeatureResult(value=int(value), lineage=[ctx.bureau.event_id])

    return compute


REGISTRY: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        "history_depth_days",
        "1",
        "int",
        "all",
        "as_of - earliest occurred_at, in days",
        "0 for zero events",
        "higher_better",
        (0.0, 100_000.0),
        _history_depth_days,
    ),
    FeatureSpec(
        "median_monthly_inflow_paise",
        "1",
        "int",
        "6m",
        "median of monthly income totals",
        NO_INCOME_OBSERVED,
        "higher_better",
        _MONEY_RANGE,
        _median_monthly_inflow,
    ),
    FeatureSpec(
        "p25_monthly_inflow_paise",
        "1",
        "int",
        "6m",
        "25th pct of monthly income totals",
        NO_INCOME_OBSERVED,
        "higher_better",
        _MONEY_RANGE,
        _p25_monthly_inflow,
    ),
    FeatureSpec(
        "monthly_inflow_cv",
        "1",
        "float",
        "6m",
        "population CV of monthly income",
        MEAN_BELOW_FLOOR,
        "lower_better",
        (0.0, 10.0),
        _monthly_inflow_cv,
    ),
    FeatureSpec(
        "inflow_trend_ratio",
        "1",
        "float",
        "6m",
        "recent 3m income / prior 3m income",
        MEAN_BELOW_FLOOR,
        "higher_better",
        (0.0, 5.0),
        _inflow_trend_ratio,
    ),
    FeatureSpec(
        "inflow_source_count",
        "1",
        "int",
        "all",
        "distinct income counterparties",
        NO_INCOME_OBSERVED,
        "higher_better",
        (0.0, 1_000.0),
        _inflow_source_count,
    ),
    FeatureSpec(
        "income_months_observed",
        "1",
        "int",
        "all",
        "months with an income event",
        NO_INCOME_OBSERVED,
        "higher_better",
        (0.0, 1_000.0),
        _income_months_observed,
    ),
    FeatureSpec(
        "total_inflow_6m_paise",
        "1",
        "int",
        "6m",
        "sum of income over 6m",
        NO_INCOME_OBSERVED,
        "higher_better",
        _MONEY_RANGE,
        _total_inflow_6m,
    ),
    FeatureSpec(
        "salary_income_share",
        "1",
        "float",
        "all",
        "salary income / total income",
        NO_INCOME_OBSERVED,
        "none",
        (0.0, 1.0),
        _category_share(TxnCategory.SALARY),
    ),
    FeatureSpec(
        "gig_income_share",
        "1",
        "float",
        "all",
        "gig income / total income",
        NO_INCOME_OBSERVED,
        "none",
        (0.0, 1.0),
        _category_share(TxnCategory.GIG_INCOME),
    ),
    FeatureSpec(
        "business_income_share",
        "1",
        "float",
        "all",
        "business income / total income",
        NO_INCOME_OBSERVED,
        "none",
        (0.0, 1.0),
        _category_share(TxnCategory.BUSINESS_INCOME),
    ),
    FeatureSpec(
        "monthly_emi_paise",
        "1",
        "int",
        "3m",
        "median monthly EMI outflow",
        NO_EMIS_OBSERVED,
        "lower_better",
        _MONEY_RANGE,
        _monthly_emi_paise,
    ),
    FeatureSpec(
        "essential_expense_paise",
        "1",
        "int",
        "3m",
        "median monthly essential outflow",
        NO_ESSENTIAL_OBSERVED,
        "lower_better",
        _MONEY_RANGE,
        _essential_expense_paise,
    ),
    FeatureSpec(
        "debt_service_ratio",
        "1",
        "float",
        "3m",
        "EMI / median monthly inflow",
        NO_EMIS_OBSERVED,
        "lower_better",
        (0.0, 2.0),
        _debt_service_ratio,
    ),
    FeatureSpec(
        "essential_expense_ratio",
        "1",
        "float",
        "3m",
        "essential / median monthly inflow",
        NO_ESSENTIAL_OBSERVED,
        "lower_better",
        (0.0, 3.0),
        _essential_expense_ratio,
    ),
    FeatureSpec(
        "mean_balance_paise",
        "1",
        "int",
        "3m",
        "mean balance over 3m",
        NO_BALANCE_DATA,
        "higher_better",
        _BALANCE_RANGE,
        _mean_balance_paise,
    ),
    FeatureSpec(
        "min_balance_paise",
        "1",
        "int",
        "3m",
        "minimum balance over 3m",
        NO_BALANCE_DATA,
        "higher_better",
        _BALANCE_RANGE,
        _min_balance_paise,
    ),
    FeatureSpec(
        "balance_min_to_mean_ratio",
        "1",
        "float",
        "3m",
        "min balance / mean balance",
        NO_BALANCE_DATA,
        "higher_better",
        (0.0, 1.0),
        _balance_min_to_mean_ratio,
    ),
    FeatureSpec(
        "expense_cover_months",
        "1",
        "float",
        "3m",
        "mean balance / monthly essential",
        NO_ESSENTIAL_OBSERVED,
        "higher_better",
        (0.0, 60.0),
        _expense_cover_months,
    ),
    FeatureSpec(
        "utility_payment_ratio",
        "1",
        "float",
        "6m",
        "months paid / covered months",
        NO_UTILITY_OBSERVED,
        "higher_better",
        (0.0, 1.0),
        _utility_payment_ratio,
    ),
    FeatureSpec(
        "utility_ontime_streak_months",
        "1",
        "int",
        "12m",
        "consecutive recent months paid",
        NO_UTILITY_OBSERVED,
        "higher_better",
        (0.0, 120.0),
        _utility_ontime_streak,
    ),
    FeatureSpec(
        "telecom_continuity_months",
        "1",
        "int",
        "12m",
        "months with a telecom payment",
        NO_TELECOM_OBSERVED,
        "higher_better",
        (0.0, 120.0),
        _telecom_continuity_months,
    ),
    FeatureSpec(
        "source_diversity",
        "1",
        "int",
        "all",
        "distinct source connections",
        NO_EVENTS,
        "higher_better",
        (0.0, 1_000.0),
        _source_diversity,
    ),
    FeatureSpec(
        "other_share",
        "1",
        "float",
        "all",
        "OTHER events / all events",
        NO_EVENTS,
        "lower_better",
        (0.0, 1.0),
        _other_share,
    ),
    FeatureSpec(
        "txn_density_per_month",
        "1",
        "float",
        "all",
        "events / months observed",
        NO_EVENTS,
        "none",
        (0.0, 10_000.0),
        _txn_density_per_month,
    ),
    FeatureSpec(
        "unclassified_inflow_share",
        "1",
        "float",
        "all",
        "unclassified credit amount / all credit amount",
        NO_INCOME_OBSERVED,
        "lower_better",
        (0.0, 1.0),
        _unclassified_inflow_share,
    ),
    FeatureSpec(
        "vector_classified_share",
        "1",
        "float",
        "all",
        "VECTOR_KNN events / all events (transparency only)",
        NO_EVENTS,
        "none",
        (0.0, 1.0),
        _vector_classified_share,
    ),
    FeatureSpec(
        "bureau_score",
        "1",
        "int",
        "all",
        "bureau score when present",
        NO_BUREAU_DATA,
        "higher_better",
        (0.0, 900.0),
        _bureau_field("score", NO_BUREAU_DATA),
    ),
    FeatureSpec(
        "bureau_active_loans",
        "1",
        "int",
        "all",
        "active loans from bureau",
        NO_BUREAU_DATA,
        "lower_better",
        (0.0, 100.0),
        _bureau_field("active_loans", NO_BUREAU_DATA),
    ),
    FeatureSpec(
        "bureau_delinquencies_12m",
        "1",
        "int",
        "12m",
        "delinquencies from bureau",
        NO_BUREAU_DATA,
        "lower_better",
        (0.0, 100.0),
        _bureau_field("delinquencies_12m", NO_BUREAU_DATA),
    ),
)

FEATURE_KEYS: frozenset[str] = frozenset(spec.key for spec in REGISTRY)
