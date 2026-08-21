"""Versioned, deterministic classification rule set.

No ML. Signals are keyword patterns, counterparty repetition, and recurrence (detected
as periodicity + amount stability over a window — never as a keyword). Bumping any rule
requires bumping ``CLASSIFIER_VERSION``.
"""

import enum
from dataclasses import dataclass

CLASSIFIER_VERSION = "clf-v2"


class TxnCategory(enum.StrEnum):
    SALARY = "SALARY"
    GIG_INCOME = "GIG_INCOME"
    BUSINESS_INCOME = "BUSINESS_INCOME"
    TRANSFER_IN = "TRANSFER_IN"
    RENT = "RENT"
    EMI = "EMI"
    UTILITY = "UTILITY"
    TELECOM = "TELECOM"
    MERCHANT = "MERCHANT"
    CASH = "CASH"
    OTHER = "OTHER"


INCOME_CATEGORIES = frozenset(
    {TxnCategory.SALARY, TxnCategory.GIG_INCOME, TxnCategory.BUSINESS_INCOME}
)
ESSENTIAL_EXPENSE_CATEGORIES = frozenset(
    {TxnCategory.RENT, TxnCategory.EMI, TxnCategory.UTILITY, TxnCategory.TELECOM}
)


@dataclass(frozen=True)
class KeywordRule:
    rule_id: str
    category: TxnCategory
    direction: str | None  # "CREDIT" | "DEBIT" | None
    keywords: tuple[str, ...]


# Ordered: the first matching rule wins.
KEYWORD_RULES: tuple[KeywordRule, ...] = (
    KeywordRule("KW_SALARY", TxnCategory.SALARY, "CREDIT", ("salary", "payroll", "wages")),
    KeywordRule(
        "KW_GIG", TxnCategory.GIG_INCOME, "CREDIT", ("gig", "payout", "freelance", "stipend")
    ),
    KeywordRule(
        "KW_BUSINESS",
        TxnCategory.BUSINESS_INCOME,
        "CREDIT",
        ("business", "settlement", "invoice", "sales"),
    ),
    KeywordRule("KW_RENT", TxnCategory.RENT, "DEBIT", ("rent", "lease")),
    KeywordRule("KW_EMI", TxnCategory.EMI, "DEBIT", ("emi", "loan", "instal")),
    KeywordRule(
        "KW_UTILITY",
        TxnCategory.UTILITY,
        "DEBIT",
        ("utility", "electricity", "water", "power", "bill"),
    ),
    KeywordRule(
        "KW_TELECOM", TxnCategory.TELECOM, "DEBIT", ("telecom", "mobile", "recharge", "broadband")
    ),
    KeywordRule("KW_CASH", TxnCategory.CASH, None, ("atm", "cash withdrawal", "cash deposit")),
    KeywordRule(
        "KW_TRANSFER", TxnCategory.TRANSFER_IN, "CREDIT", ("transfer", "neft", "imps", "refund")
    ),
    KeywordRule(
        "KW_MERCHANT", TxnCategory.MERCHANT, "DEBIT", ("upi", "pos", "purchase", "merchant", "card")
    ),
)

# Confidence by signal source.
CONF_KEYWORD = 0.9
CONF_RECURRENCE = 0.7
CONF_TRANSFER = 0.8
CONF_NONE = 0.0

# Recurrence: >= N occurrences, roughly monthly spacing, stable amounts.
RECURRENCE_MIN_OCCURRENCES = 3
RECURRENCE_PERIOD_DAYS = 30
RECURRENCE_PERIOD_TOLERANCE_DAYS = 10
RECURRENCE_AMOUNT_CV_MAX = 0.2

# Same counterparty in both directions within this window → transfer round-trip.
TRANSFER_ROUNDTRIP_WINDOW_DAYS = 7
