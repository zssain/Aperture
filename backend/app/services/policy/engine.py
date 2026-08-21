"""The deterministic policy engine: ``evaluate`` is a PURE FUNCTION.

No I/O, no database, no clock, no randomness - except one seeded exploration draw whose seed
is ``hash(application_id, policy_version)`` so it is reproducible on replay. This is invariant
1 made concrete: risk estimation and the decision are separate, and every threshold that fires
is recorded in order. Treat every branch here as something that will be read out in an audit.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from app.services.policy.reasons import REASONS_CATALOGUE_VERSION, assemble_reasons
from app.services.policy.schema import (
    APPROVAL_OUTCOMES,
    FiredRule,
    FourAssessments,
    LoanRequest,
    MissingAssessmentError,
    PolicyDecision,
    PolicyOutcome,
    PolicyRules,
    Routing,
    Terms,
)
from app.services.policy.terms import build_terms


@dataclass(frozen=True)
class GateSignals:
    """The normalized assessment values the ordered gates read."""

    manipulation_band: str
    affordability_status: str
    coverage_score: int
    pd: float | None
    policy: PolicyRules


@dataclass(frozen=True)
class Gate:
    number: int
    name: str
    requires_pd: bool
    predicate: Callable[[GateSignals], bool]
    outcome: PolicyOutcome


# The ordered gate predicates. Each reads only the normalized signals + the policy. Gate 9 is
# the catch-all, which is what makes the decision total.
def _g1(s: GateSignals) -> bool:
    return s.manipulation_band == "HIGH"


def _g2(s: GateSignals) -> bool:
    return s.affordability_status == "FAIL"


def _g3(s: GateSignals) -> bool:
    return s.affordability_status == "INDETERMINATE"


def _g4(s: GateSignals) -> bool:
    return s.coverage_score < s.policy.min_coverage


def _g5(s: GateSignals) -> bool:
    return s.manipulation_band == "ELEVATED"


def _g6(s: GateSignals) -> bool:
    return s.pd is not None and s.pd > s.policy.pd_decline_threshold


def _g7(s: GateSignals) -> bool:
    return (
        s.pd is not None and s.pd <= s.policy.pd_enhanced and s.coverage_score >= s.policy.cov_high
    )


def _g8(s: GateSignals) -> bool:
    return (
        s.pd is not None and s.pd <= s.policy.pd_standard and s.coverage_score >= s.policy.cov_mid
    )


def _g9(s: GateSignals) -> bool:
    return True


# This ONE list is the single source of truth: the engine walks it and the validator reasons
# about it (reachability/ordering), so they can never drift.
GATES: tuple[Gate, ...] = (
    Gate(1, "manipulation_high", False, _g1, PolicyOutcome.FRAUD_REVIEW),
    Gate(2, "affordability_fail", False, _g2, PolicyOutcome.DECLINE_AFFORDABILITY),
    Gate(3, "affordability_indeterminate", False, _g3, PolicyOutcome.REVIEW_EVIDENCE),
    Gate(4, "coverage_below_min", False, _g4, PolicyOutcome.REVIEW_EVIDENCE),
    Gate(5, "manipulation_elevated", False, _g5, PolicyOutcome.REVIEW_FRAUD),
    Gate(6, "pd_decline", True, _g6, PolicyOutcome.DECLINE_RISK),
    Gate(7, "approve_enhanced", True, _g7, PolicyOutcome.APPROVE_ENHANCED),
    Gate(8, "approve_standard", True, _g8, PolicyOutcome.APPROVE_STANDARD),
    Gate(9, "approve_starter", True, _g9, PolicyOutcome.APPROVE_STARTER),
)

# Rule numbers for the modifiers that are not part of the ordered gate ladder.
RULE_MANDATORY_REVIEW = 10
RULE_EXPLORATION = 11

_HUMAN_OUTCOMES: frozenset[PolicyOutcome] = frozenset(
    {
        PolicyOutcome.FRAUD_REVIEW,
        PolicyOutcome.REVIEW_EVIDENCE,
        PolicyOutcome.REVIEW_FRAUD,
    }
)


def _routing_for(outcome: PolicyOutcome) -> Routing:
    if outcome == PolicyOutcome.SYSTEM_UNAVAILABLE:
        return Routing.SYSTEM_UNAVAILABLE
    if outcome in _HUMAN_OUTCOMES:
        return Routing.HUMAN
    return Routing.AUTOMATED  # approvals and automated declines


def exploration_draw(application_id: str, policy_version: str, budget: float) -> bool:
    """Seeded, reproducible draw in [0, 1). NEVER uses unseeded randomness - a random draw
    would break determinism, which is the whole point of this stage."""
    if budget <= 0.0:
        return False
    digest = hashlib.sha256(f"{application_id}:{policy_version}".encode()).hexdigest()
    fraction = int(digest[:16], 16) / float(1 << 64)
    return fraction < budget


def _require(assessments: FourAssessments) -> None:
    missing = [
        name
        for name in ("manipulation", "affordability", "coverage", "risk")
        if getattr(assessments, name) is None
    ]
    if missing:
        raise MissingAssessmentError(
            f"cannot decide without all four assessments; missing: {sorted(missing)}"
        )


def _unavailable(policy: PolicyRules) -> PolicyDecision:
    return PolicyDecision(
        outcome=PolicyOutcome.SYSTEM_UNAVAILABLE.value,
        routing=Routing.SYSTEM_UNAVAILABLE.value,
        terms=None,
        approved_limit_paise=None,
        fired_rules=(FiredRule(0, "pd_unavailable", PolicyOutcome.SYSTEM_UNAVAILABLE.value),),
        reasons=(),
        exploration_cohort=False,
        policy_version=policy.policy_version,
        reasons_catalogue_version=REASONS_CATALOGUE_VERSION,
    )


def evaluate(
    assessments: FourAssessments,
    request: LoanRequest,
    policy: PolicyRules,
) -> PolicyDecision:
    _require(assessments)
    # After _require, all four are present; bind non-None locals for the type-checker.
    manipulation = assessments.manipulation
    affordability = assessments.affordability
    coverage = assessments.coverage
    risk = assessments.risk
    assert manipulation and affordability and coverage and risk

    signals = GateSignals(
        manipulation_band=manipulation.band,
        affordability_status=affordability.status,
        coverage_score=coverage.score,
        pd=risk.pd,
        policy=policy,
    )

    fired: list[FiredRule] = []
    fired_gate: Gate | None = None
    for gate in GATES:
        # Reached a pd-dependent gate with no pd: the risk score is unavailable. Route
        # SYSTEM_UNAVAILABLE and produce no decision outcome (invariant 2).
        if gate.requires_pd and signals.pd is None:
            return _unavailable(policy)
        if gate.predicate(signals):
            fired_gate = gate
            fired.append(FiredRule(gate.number, gate.name, gate.outcome.value))
            break
    assert fired_gate is not None  # gate 9 is a catch-all; the ladder is total.

    outcome = fired_gate.outcome
    exploration_cohort = False

    # Exploration cohort: a near-miss DECLINE_RISK with a CLEAR/PASS profile may be drawn
    # into APPROVE_STARTER. Reaching gate 6 already implies manipulation CLEAR + affordability
    # PASS + coverage >= min, but the conditions are re-checked explicitly for the audit.
    if (
        outcome == PolicyOutcome.DECLINE_RISK
        and _exploration_eligible(signals, manipulation.band, affordability.status)
        and exploration_draw(
            str(request.application_id), policy.policy_version, policy.exploration_budget
        )
    ):
        outcome = PolicyOutcome.APPROVE_STARTER
        exploration_cohort = True
        fired.append(FiredRule(RULE_EXPLORATION, "exploration_cohort", outcome.value))

    # Terms only for approvals (affordability always binds the principal).
    terms: Terms | None = None
    approved_limit: int | None = None
    if outcome in APPROVAL_OUTCOMES:
        terms = build_terms(outcome.value, policy, affordability, request)
        approved_limit = terms.approved_principal_paise

    # Rule 10: an approval above the mandatory-review ceiling is forced to a human.
    routing = _routing_for(outcome)
    mandatory_review = False
    over_ceiling = request.amount_paise > policy.mandatory_review_ceiling_paise
    if outcome in APPROVAL_OUTCOMES and over_ceiling:
        routing = Routing.HUMAN
        mandatory_review = True
        fired.append(FiredRule(RULE_MANDATORY_REVIEW, "mandatory_review", outcome.value))

    reasons = assemble_reasons(
        outcome,
        assessments,
        exploration_cohort=exploration_cohort,
        mandatory_review=mandatory_review,
    )

    return PolicyDecision(
        outcome=outcome.value,
        routing=routing.value,
        terms=terms,
        approved_limit_paise=approved_limit,
        fired_rules=tuple(fired),
        reasons=reasons,
        exploration_cohort=exploration_cohort,
        policy_version=policy.policy_version,
        reasons_catalogue_version=REASONS_CATALOGUE_VERSION,
    )


def _exploration_eligible(
    signals: GateSignals, manipulation_band: str, affordability_status: str
) -> bool:
    policy = signals.policy
    if manipulation_band != "CLEAR" or affordability_status != "PASS":
        return False
    if signals.pd is None:
        return False
    # Within the margin above the decline threshold.
    return signals.pd <= policy.pd_decline_threshold + policy.exploration_margin
