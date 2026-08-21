"""Policy engine tests: purity, gate boundaries, the affordability cap, exploration
reproducibility and gating, missing-assessment raise, fired-rule ordering, and pd-null routing.

The engine is a pure function; none of these tests touch a database or a clock.
"""

import uuid

import pytest
from app.services.policy.defaults import seed_policy_v1
from app.services.policy.engine import (
    RULE_EXPLORATION,
    RULE_MANDATORY_REVIEW,
    evaluate,
    exploration_draw,
)
from app.services.policy.reasons import REASON_CODES, REASONS_CATALOGUE_VERSION
from app.services.policy.schema import (
    AffordabilityInput,
    ContributorInput,
    CoverageInput,
    FourAssessments,
    LoanRequest,
    ManipulationInput,
    MissingAssessmentError,
    MissingSourceInput,
    PolicyOutcome,
    RiskInput,
    Routing,
)
from hypothesis import given
from hypothesis import strategies as st

POLICY = seed_policy_v1()
EPS = 1e-9
_APP = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _assessments(
    *,
    manipulation: str = "CLEAR",
    affordability: str = "PASS",
    coverage: int = 90,
    pd: float | None = 0.05,
    max_principal: int | None = 1_000_000_000,
) -> FourAssessments:
    return FourAssessments(
        manipulation=ManipulationInput(band=manipulation),
        affordability=AffordabilityInput(
            status=affordability,
            max_supportable_principal_paise=max_principal,
            dsr=0.3,
            dsr_ceiling=0.5,
        ),
        coverage=CoverageInput(
            score=coverage,
            band="HIGH",
            missing_sources=(MissingSourceInput("BUREAU", 8),),
        ),
        risk=RiskInput(
            pd=pd,
            top_contributors=(
                ContributorInput("debt_service_ratio", 0.4, "increases_risk"),
                ContributorInput("mean_balance_paise", -0.2, "decreases_risk"),
            ),
            reason_codes=("HIGH_DSR",),
        ),
    )


def _request(amount: int = 10_000_000, tenor: int = 12) -> LoanRequest:
    return LoanRequest(
        application_id=_APP, amount_paise=amount, tenor_months=tenor, annual_rate_bps=1800
    )


# --------------------------------------------------------------------------- #
# Purity.
# --------------------------------------------------------------------------- #
def test_evaluate_is_pure_over_1000_identical_calls() -> None:
    assessments, request = _assessments(pd=0.12, coverage=60), _request()
    first = evaluate(assessments, request, POLICY)
    for _ in range(1000):
        assert evaluate(assessments, request, POLICY) == first


# --------------------------------------------------------------------------- #
# Gate outcomes and ordering (first matching gate wins).
# --------------------------------------------------------------------------- #
def test_gate_precedence_manipulation_high_beats_affordability_fail() -> None:
    # Both gate 1 and gate 2 conditions hold; gate 1 (fraud) must win.
    decision = evaluate(
        _assessments(manipulation="HIGH", affordability="FAIL", max_principal=None),
        _request(),
        POLICY,
    )
    assert decision.outcome == PolicyOutcome.FRAUD_REVIEW.value
    assert decision.fired_rules[0].number == 1


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"manipulation": "HIGH"}, PolicyOutcome.FRAUD_REVIEW),
        ({"affordability": "FAIL", "max_principal": None}, PolicyOutcome.DECLINE_AFFORDABILITY),
        ({"affordability": "INDETERMINATE", "max_principal": None}, PolicyOutcome.REVIEW_EVIDENCE),
        ({"coverage": 30}, PolicyOutcome.REVIEW_EVIDENCE),
        ({"manipulation": "ELEVATED"}, PolicyOutcome.REVIEW_FRAUD),
        ({"pd": 0.30}, PolicyOutcome.DECLINE_RISK),
        ({"pd": 0.05, "coverage": 90}, PolicyOutcome.APPROVE_ENHANCED),
        ({"pd": 0.12, "coverage": 60}, PolicyOutcome.APPROVE_STANDARD),
        ({"pd": 0.20, "coverage": 45}, PolicyOutcome.APPROVE_STARTER),
    ],
)
def test_each_gate_reaches_its_outcome(kwargs: dict[str, object], expected: PolicyOutcome) -> None:
    decision = evaluate(_assessments(**kwargs), _request(), POLICY)  # type: ignore[arg-type]
    assert decision.outcome == expected.value


# --------------------------------------------------------------------------- #
# Boundary tests: threshold, threshold +/- epsilon.
# --------------------------------------------------------------------------- #
def test_pd_decline_boundary() -> None:
    at = evaluate(_assessments(pd=POLICY.pd_decline_threshold, coverage=45), _request(), POLICY)
    above = evaluate(
        _assessments(pd=POLICY.pd_decline_threshold + EPS, coverage=45), _request(), POLICY
    )
    assert at.outcome == PolicyOutcome.APPROVE_STARTER.value  # pd > threshold is strict
    assert above.outcome == PolicyOutcome.DECLINE_RISK.value


def test_pd_enhanced_and_cov_high_boundary() -> None:
    on = evaluate(_assessments(pd=POLICY.pd_enhanced, coverage=POLICY.cov_high), _request(), POLICY)
    assert on.outcome == PolicyOutcome.APPROVE_ENHANCED.value
    just_over_pd = evaluate(
        _assessments(pd=POLICY.pd_enhanced + EPS, coverage=POLICY.cov_high), _request(), POLICY
    )
    assert just_over_pd.outcome == PolicyOutcome.APPROVE_STANDARD.value
    just_under_cov = evaluate(
        _assessments(pd=POLICY.pd_enhanced, coverage=POLICY.cov_high - 1), _request(), POLICY
    )
    assert just_under_cov.outcome == PolicyOutcome.APPROVE_STANDARD.value


def test_pd_standard_and_cov_mid_boundary() -> None:
    on = evaluate(_assessments(pd=POLICY.pd_standard, coverage=POLICY.cov_mid), _request(), POLICY)
    assert on.outcome == PolicyOutcome.APPROVE_STANDARD.value
    just_over_pd = evaluate(
        _assessments(pd=POLICY.pd_standard + EPS, coverage=POLICY.cov_mid), _request(), POLICY
    )
    assert just_over_pd.outcome == PolicyOutcome.APPROVE_STARTER.value
    just_under_cov = evaluate(
        _assessments(pd=POLICY.pd_standard, coverage=POLICY.cov_mid - 1), _request(), POLICY
    )
    assert just_under_cov.outcome == PolicyOutcome.APPROVE_STARTER.value


def test_coverage_min_boundary() -> None:
    below = evaluate(_assessments(coverage=POLICY.min_coverage - 1), _request(), POLICY)
    at = evaluate(_assessments(coverage=POLICY.min_coverage, pd=0.05), _request(), POLICY)
    assert below.outcome == PolicyOutcome.REVIEW_EVIDENCE.value
    assert at.outcome != PolicyOutcome.REVIEW_EVIDENCE.value


def test_mandatory_review_ceiling_boundary_forces_human() -> None:
    ceiling = POLICY.mandatory_review_ceiling_paise
    at = evaluate(_assessments(pd=0.05), _request(amount=ceiling), POLICY)
    over = evaluate(_assessments(pd=0.05), _request(amount=ceiling + 1), POLICY)
    assert at.routing == Routing.AUTOMATED.value
    assert over.routing == Routing.HUMAN.value
    assert any(r.number == RULE_MANDATORY_REVIEW for r in over.fired_rules)


# --------------------------------------------------------------------------- #
# Terms: affordability always binds the principal.
# --------------------------------------------------------------------------- #
def test_affordability_cap_binds_the_principal() -> None:
    decision = evaluate(
        _assessments(pd=0.05, coverage=90, max_principal=3_000_000),
        _request(amount=40_000_000),
        POLICY,
    )
    assert decision.outcome == PolicyOutcome.APPROVE_ENHANCED.value
    assert decision.approved_limit_paise == 3_000_000  # capped by affordability, not band


@given(
    pd=st.floats(min_value=0.0, max_value=0.2),
    coverage=st.integers(min_value=40, max_value=100),
    max_principal=st.integers(min_value=1, max_value=1_000_000_000),
    requested=st.integers(min_value=1, max_value=1_000_000_000),
)
def test_no_approval_ever_exceeds_max_supportable_principal(
    pd: float, coverage: int, max_principal: int, requested: int
) -> None:
    decision = evaluate(
        _assessments(pd=pd, coverage=coverage, max_principal=max_principal),
        _request(amount=requested),
        POLICY,
    )
    if decision.outcome in {
        o.value
        for o in (
            PolicyOutcome.APPROVE_ENHANCED,
            PolicyOutcome.APPROVE_STANDARD,
            PolicyOutcome.APPROVE_STARTER,
        )
    }:
        assert decision.approved_limit_paise is not None
        assert decision.approved_limit_paise <= max_principal
        assert decision.approved_limit_paise <= requested


# --------------------------------------------------------------------------- #
# Exploration cohort: seeded, reproducible, and gated.
# --------------------------------------------------------------------------- #
def test_exploration_draw_is_reproducible() -> None:
    a = exploration_draw(str(_APP), "policy-v1", 0.5)
    b = exploration_draw(str(_APP), "policy-v1", 0.5)
    assert a == b
    # A different seed input can draw differently, but each is stable.
    assert exploration_draw("other-app", "policy-v1", 0.5) == exploration_draw(
        "other-app", "policy-v1", 0.5
    )


def test_exploration_flips_near_miss_decline_to_starter_when_drawn() -> None:
    forced_in = POLICY.model_copy(update={"exploration_budget": 1.0})
    near_miss = _assessments(pd=POLICY.pd_decline_threshold + POLICY.exploration_margin / 2)
    decision = evaluate(near_miss, _request(), forced_in)
    assert decision.outcome == PolicyOutcome.APPROVE_STARTER.value
    assert decision.exploration_cohort is True
    assert [r.number for r in decision.fired_rules] == [6, RULE_EXPLORATION]


def test_exploration_does_not_fire_when_budget_zero() -> None:
    forced_out = POLICY.model_copy(update={"exploration_budget": 0.0})
    near_miss = _assessments(pd=POLICY.pd_decline_threshold + POLICY.exploration_margin / 2)
    decision = evaluate(near_miss, _request(), forced_out)
    assert decision.outcome == PolicyOutcome.DECLINE_RISK.value
    assert decision.exploration_cohort is False


def test_exploration_does_not_fire_beyond_margin() -> None:
    forced_in = POLICY.model_copy(update={"exploration_budget": 1.0})
    far = _assessments(pd=POLICY.pd_decline_threshold + POLICY.exploration_margin + 0.05)
    decision = evaluate(far, _request(), forced_in)
    assert decision.outcome == PolicyOutcome.DECLINE_RISK.value


def test_exploration_never_fires_when_manipulation_not_clear() -> None:
    forced_in = POLICY.model_copy(update={"exploration_budget": 1.0})
    decision = evaluate(_assessments(manipulation="ELEVATED"), _request(), forced_in)
    assert decision.outcome == PolicyOutcome.REVIEW_FRAUD.value
    assert decision.exploration_cohort is False


def test_exploration_never_fires_when_affordability_not_pass() -> None:
    forced_in = POLICY.model_copy(update={"exploration_budget": 1.0})
    decision = evaluate(
        _assessments(affordability="INDETERMINATE", max_principal=None), _request(), forced_in
    )
    assert decision.exploration_cohort is False
    assert decision.outcome == PolicyOutcome.REVIEW_EVIDENCE.value


# --------------------------------------------------------------------------- #
# Missing assessment and pd-null routing.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("missing", ["manipulation", "affordability", "coverage", "risk"])
def test_missing_assessment_raises_rather_than_deciding(missing: str) -> None:
    full = _assessments()
    partial = FourAssessments(
        manipulation=None if missing == "manipulation" else full.manipulation,
        affordability=None if missing == "affordability" else full.affordability,
        coverage=None if missing == "coverage" else full.coverage,
        risk=None if missing == "risk" else full.risk,
    )
    with pytest.raises(MissingAssessmentError):
        evaluate(partial, _request(), POLICY)


def test_pd_null_routes_system_unavailable_with_no_outcome() -> None:
    decision = evaluate(_assessments(pd=None), _request(), POLICY)
    assert decision.outcome == PolicyOutcome.SYSTEM_UNAVAILABLE.value
    assert decision.routing == Routing.SYSTEM_UNAVAILABLE.value
    assert decision.terms is None
    assert decision.approved_limit_paise is None


def test_pd_null_still_reaches_terminal_fraud_gate_first() -> None:
    # A fraud case is a fraud case even if the risk model is down (gate 1 precedes pd).
    decision = evaluate(_assessments(manipulation="HIGH", pd=None), _request(), POLICY)
    assert decision.outcome == PolicyOutcome.FRAUD_REVIEW.value


# --------------------------------------------------------------------------- #
# Reasons and fired-rule recording.
# --------------------------------------------------------------------------- #
def test_every_decision_records_fired_rules_in_order() -> None:
    decision = evaluate(_assessments(pd=0.05), _request(amount=30_000_000), POLICY)
    numbers = [r.number for r in decision.fired_rules]
    assert numbers == sorted(numbers)
    assert numbers[0] == 7  # the determining gate is recorded first
    assert RULE_MANDATORY_REVIEW in numbers  # amount over ceiling forced review


def test_reasons_lead_with_the_gate_and_use_the_catalogue() -> None:
    decision = evaluate(_assessments(pd=0.30), _request(), POLICY)
    assert decision.reasons[0].code == "GATE_DECLINE_RISK"
    assert decision.reasons_catalogue_version == REASONS_CATALOGUE_VERSION
    for reason in decision.reasons:
        assert reason.code in REASON_CODES
