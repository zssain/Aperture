"""Fairness attributes — for MONITORING ONLY. Never a model input.

These must never be readable by the risk model or the manipulation engine. They are
listed here so the enforcement check can prove they never leak into a model allow-list.
"""

FAIRNESS_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "age",
        "gender",
        "city_tier",
        "religion",
        "caste",
        "marital_status",
    }
)
