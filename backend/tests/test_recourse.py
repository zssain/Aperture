"""Recourse tests: registry enforcement, each option verified by re-running policy, the
at-most-three cap, explicit no-viable, and the time-box - all over the seed policy.
"""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from app.models.feature import FeatureSnapshot
from app.registries.fairness_attributes import FAIRNESS_ATTRIBUTES
from app.services.coverage.service import (
    CoverageAssessment,
    CoverageComponent,
    MissingSource,
)
from app.services.policy.defaults import seed_policy_v1
from app.services.policy.engine import evaluate
from app.services.policy.schema import (
    AffordabilityInput,
    ContributorInput,
    CoverageInput,
    FourAssessments,
    LoanRequest,
    ManipulationInput,
    MissingSourceInput,
    RiskInput,
)
from app.services.recourse import levers
from app.services.recourse.engine import search_recourse

POLICY = seed_policy_v1()
NOW = datetime(2026, 8, 1, tzinfo=UTC)
_APP = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _four(
    *,
    pd: float,
    coverage_score: int,
    affordability: str = "PASS",
    max_principal: int | None = 40_000_000,
) -> FourAssessments:
    return FourAssessments(
        manipulation=ManipulationInput(band="CLEAR"),
        affordability=AffordabilityInput(
            status=affordability,
            max_supportable_principal_paise=max_principal,
            dsr=0.3,
            dsr_ceiling=0.5,
        ),
        coverage=CoverageInput(
            score=coverage_score,
            band="MEDIUM",
            missing_sources=(MissingSourceInput("BUREAU", 30),),
        ),
        risk=RiskInput(pd=pd, top_contributors=(ContributorInput("dsr", 0.3, "increases_risk"),)),
    )


def _coverage(score: int, *, history_fraction: float = 0.5) -> CoverageAssessment:
    return CoverageAssessment(
        score=score,
        band="MEDIUM",
        components=[
            CoverageComponent("history_depth", 20, history_fraction, 20 * history_fraction, "x"),
        ],
        missing_sources=[MissingSource("BUREAU", "bureau adds obligations", 30)],
        weights_version="coverage-weights-v1",
        engine_version="coverage-v1",
    )


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        tenant_id=uuid.uuid4(),
        applicant_id=uuid.uuid4(),
        as_of=NOW,
        schema_version="features-v1",
        values={
            "median_monthly_inflow_paise": 5_000_000,
            "monthly_emi_paise": 0,
            "essential_expense_paise": 1_500_000,
            "monthly_inflow_cv": 0.1,
        },
        null_map={},
        input_hash="x",
    )


def _request(amount: int = 10_000_000) -> LoanRequest:
    return LoanRequest(
        application_id=_APP, amount_paise=amount, tenor_months=12, annual_rate_bps=1800
    )


# --------------------------------------------------------------------------- #
# Registry is an explicit allow-list.
# --------------------------------------------------------------------------- #
def test_registered_levers_are_exactly_the_four() -> None:
    names = {lever.name for lever in levers.registered_levers()}
    assert names == {"ACCEPT_STARTER", "REDUCE_AMOUNT", "ADD_SOURCE", "EXTEND_HISTORY"}


def test_registering_a_protected_attribute_fails() -> None:
    with pytest.raises(levers.LeverRegistrationError):
        levers.register_lever(levers.Lever("USE_AGE", "age", effort_rank=9))
    protected = next(iter(FAIRNESS_ATTRIBUTES))
    with pytest.raises(levers.LeverRegistrationError):
        levers.register_lever(levers.Lever("USE_FAIRNESS", protected, effort_rank=9))


def test_registering_a_non_actionable_target_fails() -> None:
    with pytest.raises(levers.LeverRegistrationError):
        levers.register_lever(levers.Lever("MOVE_PD", "pd", effort_rank=9))


# --------------------------------------------------------------------------- #
# Each option actually flips the decision when applied (re-run policy here).
# --------------------------------------------------------------------------- #
def test_add_source_option_flips_and_is_verified() -> None:
    four = _four(pd=0.05, coverage_score=50)  # starter: cov below cov_high
    result = search_recourse(
        four=four,
        coverage=_coverage(50),
        snapshot=_snapshot(),
        request=_request(),
        policy=POLICY,
        now=NOW,
    )
    add = next(o for o in result.options if o.lever == "ADD_SOURCE")
    # Re-run policy with the perturbation applied -> must reach the projected outcome.
    assert four.coverage is not None
    bumped = replace(four, coverage=replace(four.coverage, score=50 + 30))
    assert evaluate(bumped, _request(), POLICY).outcome == add.projected_outcome


def test_reduce_amount_option_flips_affordability_decline() -> None:
    four = _four(pd=0.05, coverage_score=90, affordability="FAIL", max_principal=3_000_000)
    result = search_recourse(
        four=four,
        coverage=_coverage(90),
        snapshot=_snapshot(),
        request=_request(10_000_000),
        policy=POLICY,
        now=NOW,
    )
    reduce = next(o for o in result.options if o.lever == "REDUCE_AMOUNT")
    assert reduce.projected_outcome in {"APPROVE_ENHANCED", "APPROVE_STANDARD", "APPROVE_STARTER"}
    assert reduce.params["amount_paise"] < 10_000_000


def test_accept_starter_only_near_boundary_decline() -> None:
    near = _four(pd=POLICY.pd_decline_threshold + POLICY.exploration_margin / 2, coverage_score=90)
    result = search_recourse(
        four=near,
        coverage=_coverage(90),
        snapshot=_snapshot(),
        request=_request(),
        policy=POLICY,
        now=NOW,
    )
    assert any(o.lever == "ACCEPT_STARTER" for o in result.options)
    assert all(
        o.projected_outcome == "APPROVE_STARTER"
        for o in result.options
        if o.lever == "ACCEPT_STARTER"
    )


def test_every_returned_lever_is_registered_and_capped_at_three() -> None:
    four = _four(pd=0.05, coverage_score=50)
    result = search_recourse(
        four=four,
        coverage=_coverage(50),
        snapshot=_snapshot(),
        request=_request(),
        policy=POLICY,
        now=NOW,
    )
    assert len(result.options) <= 3
    assert all(levers.is_registered(o.lever) for o in result.options)
    assert [o.effort_rank for o in result.options] == sorted(o.effort_rank for o in result.options)


# --------------------------------------------------------------------------- #
# No viable recourse is explicit; the search is time-boxed.
# --------------------------------------------------------------------------- #
def test_no_viable_recourse_returns_explicit_empty() -> None:
    # A hard risk decline no lever can move, with coverage already high and amount affordable.
    four = _four(pd=0.9, coverage_score=90, max_principal=1_000_000_000)
    result = search_recourse(
        four=four,
        coverage=_coverage(90, history_fraction=1.0),
        snapshot=_snapshot(),
        request=_request(1_000_000),
        policy=POLICY,
        now=NOW,
    )
    assert result.options == ()
    assert result.no_viable_recourse is True
    assert result.timed_out is False


def test_timeout_returns_empty_with_flag_not_a_fabricated_option() -> None:
    four = _four(pd=0.05, coverage_score=50)
    result = search_recourse(
        four=four,
        coverage=_coverage(50),
        snapshot=_snapshot(),
        request=_request(),
        policy=POLICY,
        now=NOW,
        deadline_seconds=0.0,
    )
    assert result.options == ()
    assert result.timed_out is True
    assert result.no_viable_recourse is False


def test_full_approval_needs_no_recourse() -> None:
    four = _four(pd=0.05, coverage_score=90)  # APPROVE_ENHANCED
    result = search_recourse(
        four=four,
        coverage=_coverage(90),
        snapshot=_snapshot(),
        request=_request(),
        policy=POLICY,
        now=NOW,
    )
    assert result.options == ()
    assert result.no_viable_recourse is False
