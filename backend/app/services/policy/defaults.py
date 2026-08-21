"""Seed policy v1 - the first live lending policy. It passes the validator.

These are the only thresholds in the system; changing lending behaviour means diffing this
artifact, not editing a classifier.
"""

from app.services.policy.schema import Graduation, PolicyOutcome, PolicyRules, TermsBand

SEED_POLICY_VERSION = "policy-v1"


def seed_policy_v1() -> PolicyRules:
    return PolicyRules(
        policy_version=SEED_POLICY_VERSION,
        min_coverage=40,
        pd_enhanced=0.08,
        pd_standard=0.15,
        pd_decline_threshold=0.25,
        cov_mid=55,
        cov_high=75,
        mandatory_review_ceiling_paise=20_000_000,  # Rs 200,000
        exploration_margin=0.03,
        exploration_budget=0.05,
        terms={
            PolicyOutcome.APPROVE_STARTER.value: TermsBand(
                max_principal_paise=5_000_000,  # Rs 50,000
                max_tenor_months=12,
                rate_band="C",
                annual_rate_bps=2200,
                graduation=Graduation(
                    review_months=6,
                    on_time_emis_required=6,
                    next_band=PolicyOutcome.APPROVE_STANDARD.value,
                ),
            ),
            PolicyOutcome.APPROVE_STANDARD.value: TermsBand(
                max_principal_paise=25_000_000,  # Rs 250,000
                max_tenor_months=24,
                rate_band="B",
                annual_rate_bps=1800,
                graduation=Graduation(
                    review_months=6,
                    on_time_emis_required=6,
                    next_band=PolicyOutcome.APPROVE_ENHANCED.value,
                ),
            ),
            PolicyOutcome.APPROVE_ENHANCED.value: TermsBand(
                max_principal_paise=50_000_000,  # Rs 500,000
                max_tenor_months=36,
                rate_band="A",
                annual_rate_bps=1500,
                graduation=None,
            ),
        },
    )
