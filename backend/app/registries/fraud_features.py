"""Allow-list of features the MANIPULATION (fraud) engine may read.

A deliberately small set of structure/consistency signals — independent of the credit
risk score. No fairness attribute may ever appear here."""

FRAUD_FEATURES: frozenset[str] = frozenset(
    {
        "other_share",
        "txn_density_per_month",
        "source_diversity",
        "balance_min_to_mean_ratio",
        "inflow_trend_ratio",
        "monthly_inflow_cv",
    }
)
