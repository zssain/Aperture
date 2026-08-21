"""Versioned reason-code catalogue.

Reason codes map a (feature, direction) pair to a stable human-readable code. They are
derived from the SIGN of each contribution, independent of the attribution method, so
they remain stable if the attribution implementation changes.
"""

REASONS_VERSION = "risk-reasons-v1"

# (feature_key, "RISK" | "PROTECTIVE") -> code. RISK = contribution pushes PD up.
_CATALOGUE: dict[tuple[str, str], str] = {
    ("monthly_inflow_cv", "RISK"): "INCOME_VOLATILITY_HIGH",
    ("monthly_inflow_cv", "PROTECTIVE"): "INCOME_STABLE",
    ("median_monthly_inflow_paise", "RISK"): "INCOME_LOW",
    ("median_monthly_inflow_paise", "PROTECTIVE"): "INCOME_STRONG",
    ("inflow_trend_ratio", "RISK"): "INCOME_TREND_DOWN",
    ("inflow_trend_ratio", "PROTECTIVE"): "INCOME_TREND_UP",
    ("debt_service_ratio", "RISK"): "DSR_HIGH",
    ("debt_service_ratio", "PROTECTIVE"): "DSR_LOW",
    ("essential_expense_ratio", "RISK"): "ESSENTIAL_BURDEN_HIGH",
    ("essential_expense_ratio", "PROTECTIVE"): "ESSENTIAL_BURDEN_LOW",
    ("balance_min_to_mean_ratio", "RISK"): "BALANCE_BUFFER_THIN",
    ("balance_min_to_mean_ratio", "PROTECTIVE"): "BALANCE_BUFFER_STABLE",
    ("mean_balance_paise", "RISK"): "BALANCE_LOW",
    ("mean_balance_paise", "PROTECTIVE"): "BALANCE_HEALTHY",
    ("utility_ontime_streak_months", "RISK"): "UTILITY_HISTORY_WEAK",
    ("utility_ontime_streak_months", "PROTECTIVE"): "UTILITY_HISTORY_STRONG",
    ("telecom_continuity_months", "RISK"): "TELECOM_CONTINUITY_WEAK",
    ("telecom_continuity_months", "PROTECTIVE"): "TELECOM_CONTINUITY_STRONG",
    ("other_share", "RISK"): "UNEXPLAINED_ACTIVITY_HIGH",
    ("other_share", "PROTECTIVE"): "ACTIVITY_WELL_EXPLAINED",
    ("history_depth_days", "RISK"): "HISTORY_SHALLOW",
    ("history_depth_days", "PROTECTIVE"): "HISTORY_DEEP",
}


def reason_codes(contributions: list[tuple[str, float]], top_n: int = 3) -> list[str]:
    """Deterministic reason codes from the top contributors by magnitude.

    ``contributions`` is a list of (feature, signed_contribution) in log-odds; a
    positive contribution raises PD (a risk), a negative one lowers it (protective).
    """
    ranked = sorted(contributions, key=lambda item: (-abs(item[1]), item[0]))
    codes: list[str] = []
    for feature, contribution in ranked:
        if len(codes) >= top_n or contribution == 0.0:
            break
        direction = "RISK" if contribution > 0 else "PROTECTIVE"
        code = _CATALOGUE.get((feature, direction))
        if code is None:
            # Unknown feature (e.g. a benchmark UCI column) → deterministic fallback.
            code = f"{feature.upper()}_{'UP' if contribution > 0 else 'DOWN'}"
        codes.append(code)
    return codes
