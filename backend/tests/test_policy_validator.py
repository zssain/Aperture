"""Policy validator tests: totality (positive + a deliberately incomplete policy),
reachability (a deliberately shadowed rule identified by number), ordering, and bounds.

The seed policy v1 must pass every check.
"""

from app.services.policy.defaults import seed_policy_v1, seed_policy_v2
from app.services.policy.engine import GATES, Gate
from app.services.policy.schema import PolicyOutcome, PolicyRules, TermsBand
from app.services.policy.validator import (
    check_bounds,
    check_ordering,
    check_reachability,
    check_totality,
    validate,
)

POLICY = seed_policy_v1()


# --------------------------------------------------------------------------- #
# The seed policy passes everything.
# --------------------------------------------------------------------------- #
def test_seed_policy_v1_is_valid() -> None:
    result = validate(POLICY)
    assert result.ok, result.errors


def test_seed_policy_totality_and_reachability_clean() -> None:
    assert check_totality(POLICY) == []
    assert check_reachability(POLICY) == []
    assert check_ordering() == []


def test_seed_policy_v2_is_valid_and_keeps_the_core_risk_guards() -> None:
    """The improved v2 must pass the validator (so it is publishable) and must not touch
    the PD thresholds or the coverage floor — those stay put while the PD is
    uncalibrated; v2 only widens access and the learning cohort."""
    v1, v2 = seed_policy_v1(), seed_policy_v2()
    assert validate(v2).ok, validate(v2).errors
    guards = lambda p: (  # noqa: E731
        p.min_coverage,
        p.pd_enhanced,
        p.pd_standard,
        p.pd_decline_threshold,
        p.cov_mid,
    )
    assert guards(v1) == guards(v2)
    # The deliberate, defensible changes.
    assert v2.cov_high < v1.cov_high
    assert v2.mandatory_review_ceiling_paise > v1.mandatory_review_ceiling_paise
    assert v2.exploration_budget > v1.exploration_budget
    assert check_bounds(POLICY) == []


# --------------------------------------------------------------------------- #
# Totality: exhaustive enumeration passes on seed, fails on an incomplete policy.
# --------------------------------------------------------------------------- #
def test_totality_fails_on_incomplete_terms_ladder() -> None:
    # Remove the STARTER band: states that reach gate 9 now have no valid terminal terms.
    incomplete_terms = {
        k: v for k, v in POLICY.terms.items() if k != PolicyOutcome.APPROVE_STARTER.value
    }
    broken = POLICY.model_copy(update={"terms": incomplete_terms})
    errors = check_totality(broken)
    assert errors, "an incomplete terms ladder must fail totality"
    assert any("no terminal outcome" in e for e in errors)
    assert validate(broken).ok is False


# --------------------------------------------------------------------------- #
# Reachability: a shadowed rule is identified by number.
# --------------------------------------------------------------------------- #
def test_reachability_identifies_a_shadowed_rule_by_number() -> None:
    # cov_mid >= cov_high and pd_standard <= pd_enhanced make gate 8 (standard) a strict
    # subset of gate 7 (enhanced): every state where 8 could fire fires 7 first.
    shadowed = PolicyRules(
        policy_version="shadow-test",
        min_coverage=40,
        pd_enhanced=0.20,
        pd_standard=0.10,
        pd_decline_threshold=0.30,
        cov_mid=80,
        cov_high=70,
        mandatory_review_ceiling_paise=20_000_000,
        exploration_margin=0.03,
        exploration_budget=0.05,
        terms=POLICY.terms,
    )
    errors = check_reachability(shadowed)
    assert any("Rule 8 unreachable" in e and "rule 7" in e for e in errors), errors


# --------------------------------------------------------------------------- #
# Ordering: a terminal gate placed after a scoring gate is reported.
# --------------------------------------------------------------------------- #
def test_ordering_passes_for_the_real_gate_ladder() -> None:
    assert check_ordering(GATES) == []


def test_ordering_flags_a_terminal_gate_after_a_scoring_gate() -> None:
    scrambled = (
        Gate(7, "approve", True, lambda s: True, PolicyOutcome.APPROVE_STARTER),
        Gate(8, "late_decline", False, lambda s: False, PolicyOutcome.DECLINE_RISK),
    )
    errors = check_ordering(scrambled)
    assert any("Rule 8" in e and "scoring rule 7" in e for e in errors), errors


# --------------------------------------------------------------------------- #
# Bounds: budget ceiling, monotonic ladder, threshold ordering.
# --------------------------------------------------------------------------- #
def test_bounds_flags_exploration_budget_over_ceiling() -> None:
    over = POLICY.model_copy(update={"exploration_budget": 0.5})
    errors = check_bounds(over)
    assert any("exploration_budget" in e for e in errors)
    assert validate(over).ok is False


def test_bounds_flags_non_monotonic_terms_ladder() -> None:
    # Give STARTER a bigger principal than ENHANCED: the ladder is no longer monotonic.
    bad_terms = dict(POLICY.terms)
    bad_terms[PolicyOutcome.APPROVE_STARTER.value] = TermsBand(
        max_principal_paise=99_000_000,
        max_tenor_months=12,
        rate_band="C",
        annual_rate_bps=2200,
    )
    bad = POLICY.model_copy(update={"terms": bad_terms})
    errors = check_bounds(bad)
    assert any("monotonic" in e for e in errors)


def test_bounds_flags_inverted_pd_thresholds() -> None:
    inverted = POLICY.model_copy(
        update={"pd_enhanced": 0.30, "pd_standard": 0.20, "pd_decline_threshold": 0.10}
    )
    errors = check_bounds(inverted)
    assert any("pd thresholds must satisfy" in e for e in errors)
