"""Versioned coverage weights — part of the policy artifact.

These live here (not as scattered code constants) so they can be diffed and simulated.
Component weights sum to 100; each component contributes ``weight x fraction`` to the
0-100 score.
"""

from typing import Any

COVERAGE_WEIGHTS_VERSION = "coverage-weights-v1"

_ARTIFACT: dict[str, Any] = {
    "version": COVERAGE_WEIGHTS_VERSION,
    # Component weights (must sum to 100).
    "component_weights": {
        "tier": 20,
        "verification": 15,
        "history_depth": 20,
        "freshness": 15,
        "diversity": 15,
        "completeness": 15,
    },
    # Band thresholds on the 0-100 score.
    "band_thresholds": {"HIGH": 75, "MEDIUM": 50},
    # A HIGH band additionally requires full source diversity — a single source (or
    # sources of one type) can never reach HIGH however deep/fresh they are.
    "high_requires_full_diversity": True,
    # History depth is measured against this required window (days).
    "required_window_days": 180,
    # Evidential tier weights (AA-verified > bank-verified > declared document).
    "tier_weights": {
        "AA_VERIFIED": 1.0,
        "BANK_VERIFIED": 0.7,
        "DECLARED_DOCUMENT": 0.4,
    },
    # Freshness: full credit at/under full_days, zero at/over zero_days, linear between.
    "freshness": {"full_days": 30, "zero_days": 120},
    # Diversity: extra sources of the SAME type get geometrically diminishing credit.
    "diversity": {"decay": 0.3, "target": 2.0},
    # Required features for completeness (present, i.e. not null, in the snapshot).
    "required_features": [
        "median_monthly_inflow_paise",
        "monthly_emi_paise",
        "essential_expense_paise",
        "mean_balance_paise",
        "history_depth_days",
    ],
    # Canonical source types + a representative "good" source of each, used to compute
    # the exact coverage delta a missing source would contribute (recourse input).
    "canonical_sources": {
        "BANK": {
            "tier": "AA_VERIFIED",
            "freshness_days": 5,
            "why": "Bank/UPI transactions are the primary evidence of income and spending.",
        },
        "BUREAU": {
            "tier": "BANK_VERIFIED",
            "freshness_days": 5,
            "why": "Bureau data reveals existing obligations and repayment history.",
        },
        "UTILITY": {
            "tier": "DECLARED_DOCUMENT",
            "freshness_days": 5,
            "why": "Utility payments evidence residential stability and bill discipline.",
        },
        "TELECOM": {
            "tier": "DECLARED_DOCUMENT",
            "freshness_days": 5,
            "why": "Telecom continuity is a positive thin-file signal.",
        },
    },
}


def get_coverage_weights(version: str) -> dict[str, Any]:
    if version != COVERAGE_WEIGHTS_VERSION:
        raise ValueError(f"unknown coverage weights version: {version!r}")
    return _ARTIFACT
