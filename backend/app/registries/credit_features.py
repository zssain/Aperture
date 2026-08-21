"""Allow-list of features the CREDIT RISK model may read. Nothing outside this set may
reach the risk model, and no fairness attribute may ever be added here."""

CREDIT_FEATURES: frozenset[str] = frozenset(
    {
        "history_depth_days",
        "median_monthly_inflow_paise",
        "p25_monthly_inflow_paise",
        "monthly_inflow_cv",
        "inflow_trend_ratio",
        "inflow_source_count",
        "income_months_observed",
        "total_inflow_6m_paise",
        "salary_income_share",
        "gig_income_share",
        "business_income_share",
        "monthly_emi_paise",
        "essential_expense_paise",
        "debt_service_ratio",
        "essential_expense_ratio",
        "mean_balance_paise",
        "min_balance_paise",
        "balance_min_to_mean_ratio",
        "expense_cover_months",
        "utility_payment_ratio",
        "utility_ontime_streak_months",
        "telecom_continuity_months",
        "source_diversity",
        "other_share",
        "txn_density_per_month",
        "bureau_score",
        "bureau_active_loans",
        "bureau_delinquencies_12m",
    }
)
