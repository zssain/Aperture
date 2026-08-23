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


def seed_policy_v2() -> PolicyRules:
    """An improved draft over v1. It keeps the core risk guards untouched — the PD
    thresholds and the coverage floor stay exactly where they are, because the PD is
    uncalibrated and moving them would be guessing — and instead makes three defensible
    changes that lift straight-through approvals for the thin-file mission without
    lending on less evidence:

      - cov_mid 55 -> 50: a low-PD applicant with decent (50%+) evidence earns STANDARD
        terms — a bigger, cheaper, longer loan — instead of only a small STARTER one.
        Coverage is observed evidence completeness, not a risk estimate, so this expands
        access without loosening any risk guard.
      - cov_high 75 -> 70: a well-evidenced thin-file applicant reaches the best
        (ENHANCED) terms a little sooner. Still demands strong evidence; only widens who
        earns the good rate.
      - mandatory_review_ceiling ₹2,00,000 -> ₹3,00,000: a flawless applicant (all four
        signals clean) up to ₹3L is auto-approved instead of being sent to a human for
        the amount alone — the fraud/affordability/coverage/risk gates still apply.
      - exploration widened (margin 0.03 -> 0.05, budget 0.05 -> 0.10): a larger,
        still-bounded slice of near-miss declines gets a small starter loan, so the
        model gathers the closed outcomes it needs to actually become calibrated.

    Everything else is inherited from v1 unchanged."""
    return seed_policy_v1().model_copy(
        update={
            "policy_version": "policy-v2",
            "cov_mid": 50,
            "cov_high": 70,
            "mandatory_review_ceiling_paise": 30_000_000,  # Rs 300,000
            "exploration_margin": 0.05,
            "exploration_budget": 0.10,
        }
    )
