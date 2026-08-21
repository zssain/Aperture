"""Versioned manipulation thresholds - exported with the policy artifact.

Every number a detector uses lives here (not scattered as code constants) so the whole
fraud posture can be diffed, simulated and shipped as one versioned artifact. Bumping any
threshold requires bumping ``MANIPULATION_CONFIG_VERSION``.
"""

from typing import Any

MANIPULATION_CONFIG_VERSION = "manip-config-v1"
MANIPULATION_ENGINE = "manip-v1"

# Rupee amounts are stored as integer paise everywhere (invariant 6). Five thousand
# rupees is 500000 paise.
_FIVE_THOUSAND_PAISE = 500_000

_ARTIFACT: dict[str, Any] = {
    "version": MANIPULATION_CONFIG_VERSION,
    # D1 - circular flow.
    "d1": {
        "window_days": 7,
        "min_cycles": 3,
        "min_pct": 0.30,
    },
    # D2 - pre-application inflow burst.
    "d2": {
        "pre_days": 45,
        "baseline_days": 180,
        "burst_multiple": 3.0,
        "min_days_required": 30,
    },
    # D3 - counterparty concentration for declared gig/self-employed income.
    "d3": {
        "concentration_pct": 0.80,
        "gig_occupations": ["GIG", "SELF_EMPLOYED"],
    },
    # D4 - round-number pseudo-salary (both conditions required).
    "d4": {
        "multiple_paise": _FIVE_THOUSAND_PAISE,
        "min_round_share": 0.80,
        "min_income_credits": 3,
        "salary_date_variance_days": 5.0,
    },
    # D5 - running-balance arithmetic.
    "d5": {
        "tolerance_paise": 100,
    },
    # D6 - document provenance. Only native-HIGH provenance codes become manipulation
    # findings; a missing signature on a declared document is normal and must not flag.
    "d6": {
        "trigger_severity": "HIGH",
    },
    # D7 - claimed history vs observed first-transaction age.
    "d7": {
        "margin_days": 60,
        "min_days_required": 30,
    },
    # D8 - cross-applicant reuse.
    "d8": {
        "min_applications": 3,
        "window_days": 14,
    },
    # Weighted-severity banding.
    "banding": {
        # A lone Medium only escalates to ELEVATED when it is confident enough.
        "single_medium_confidence_threshold": 0.75,
    },
}


def get_manipulation_config(version: str = MANIPULATION_CONFIG_VERSION) -> dict[str, Any]:
    if version != MANIPULATION_CONFIG_VERSION:
        raise ValueError(f"unknown manipulation config version: {version!r}")
    return _ARTIFACT
