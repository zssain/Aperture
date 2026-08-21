"""Publish-time policy validator: totality, reachability, ordering, bounds.

Run on save and again before publish. A policy that fails cannot be saved as valid nor
published. Totality is proven by EXHAUSTIVE ENUMERATION over a discretised state space (never
by inspection); reachability reuses the engine's own gate ladder so the two cannot drift.
"""

import uuid
from dataclasses import dataclass
from itertools import pairwise

from app.services.policy.engine import GATES, Gate, GateSignals, evaluate
from app.services.policy.schema import (
    APPROVAL_OUTCOMES,
    AffordabilityInput,
    CoverageInput,
    FourAssessments,
    LoanRequest,
    ManipulationInput,
    PolicyOutcome,
    PolicyRules,
    RiskInput,
)

# The exploration budget may never exceed this configured maximum (bounds check).
EXPLORATION_BUDGET_CEILING = 0.10

_APPROVAL_BAND_KEYS = tuple(o.value for o in APPROVAL_OUTCOMES)
_LADDER_ORDER = (
    PolicyOutcome.APPROVE_STARTER.value,
    PolicyOutcome.APPROVE_STANDARD.value,
    PolicyOutcome.APPROVE_ENHANCED.value,
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...]


# --------------------------------------------------------------------------- #
# Discretised state space.
# --------------------------------------------------------------------------- #
def _coverage_scores(policy: PolicyRules) -> list[int]:
    scores = {
        0,
        max(0, policy.min_coverage - 1),
        policy.min_coverage,
        policy.cov_mid,
        policy.cov_high,
        100,
    }
    return sorted(scores)


def _pd_values(policy: PolicyRules) -> list[float | None]:
    margin = policy.exploration_margin
    raw = [
        0.0,
        policy.pd_enhanced,
        (policy.pd_enhanced + policy.pd_standard) / 2,
        policy.pd_standard,
        (policy.pd_standard + policy.pd_decline_threshold) / 2,
        policy.pd_decline_threshold,
        min(1.0, policy.pd_decline_threshold + margin / 2),
        min(1.0, policy.pd_decline_threshold + margin + 0.01),
        1.0,
    ]
    values: list[float | None] = [None]
    values.extend(sorted(set(raw)))
    return values


def _materialize(
    manipulation: str,
    affordability_status: str,
    coverage_score: int,
    pd: float | None,
) -> tuple[FourAssessments, LoanRequest]:
    # PASS affordability always carries a real max_supportable principal.
    max_principal = 1_000_000_000 if affordability_status == "PASS" else None
    assessments = FourAssessments(
        manipulation=ManipulationInput(band=manipulation),
        affordability=AffordabilityInput(
            status=affordability_status,
            max_supportable_principal_paise=max_principal,
            dsr=0.3,
            dsr_ceiling=0.5,
        ),
        coverage=CoverageInput(score=coverage_score, band="MEDIUM"),
        risk=RiskInput(pd=pd),
    )
    request = LoanRequest(
        application_id=uuid.UUID(int=0),
        amount_paise=10_000_000,
        tenor_months=12,
        annual_rate_bps=1800,
    )
    return assessments, request


def _enumerate(policy: PolicyRules) -> list[tuple[str, str, int, float | None]]:
    states: list[tuple[str, str, int, float | None]] = []
    for manipulation in ("CLEAR", "ELEVATED", "HIGH"):
        for affordability in ("PASS", "FAIL", "INDETERMINATE"):
            for score in _coverage_scores(policy):
                for pd in _pd_values(policy):
                    states.append((manipulation, affordability, score, pd))
    return states


# --------------------------------------------------------------------------- #
# Totality: every discretised state reaches exactly one defined terminal outcome.
# --------------------------------------------------------------------------- #
def check_totality(policy: PolicyRules) -> list[str]:
    valid = {o.value for o in PolicyOutcome}
    errors: list[str] = []
    for state in _enumerate(policy):
        assessments, request = _materialize(*state)
        try:
            decision = evaluate(assessments, request, policy)
        except Exception as exc:
            errors.append(f"state {state} produced no terminal outcome: {exc!r}")
            continue
        if decision.outcome not in valid:
            errors.append(f"state {state} produced unknown outcome {decision.outcome!r}")
    return errors


# --------------------------------------------------------------------------- #
# Reachability: no gate is shadowed by an earlier gate.
# --------------------------------------------------------------------------- #
def _signals(policy: PolicyRules, state: tuple[str, str, int, float | None]) -> GateSignals:
    manipulation, affordability, score, pd = state
    return GateSignals(
        manipulation_band=manipulation,
        affordability_status=affordability,
        coverage_score=score,
        pd=pd,
        policy=policy,
    )


def _first_true_gate(policy: PolicyRules, state: tuple[str, str, int, float | None]) -> Gate | None:
    signals = _signals(policy, state)
    for gate in GATES:
        if gate.requires_pd and signals.pd is None:
            return None  # pd unavailable short-circuits to SYSTEM_UNAVAILABLE
        if gate.predicate(signals):
            return gate
    return None


# Gates 1-5 are the terminal/review gates; 6+ are the pd-scoring region.
_FIRST_SCORING_NUMBER = 6


def _in_scoring_region(policy: PolicyRules, state: tuple[str, str, int, float | None]) -> bool:
    """No terminal/review gate fires and pd is present - the region where scoring decides."""
    signals = _signals(policy, state)
    if signals.pd is None:
        return False
    return not any(g.predicate(signals) for g in GATES if g.number < _FIRST_SCORING_NUMBER)


def check_reachability(policy: PolicyRules) -> list[str]:
    states = _enumerate(policy)
    errors: list[str] = []
    for gate in GATES:
        # States in which THIS gate's own predicate holds and pd (if needed) is present.
        own_states = [
            state
            for state in states
            for signals in [_signals(policy, state)]
            if not (gate.requires_pd and signals.pd is None) and gate.predicate(signals)
        ]
        if not own_states:
            errors.append(f"Rule {gate.number} ({gate.name}) has no satisfying state")
            continue
        # The gate is reachable if it is the FIRST firing gate in at least one such state.
        if any(_first_true_gate(policy, state) is gate for state in own_states):
            continue
        # Shadowed. A scoring gate is meaningfully shadowed only relative to other scoring
        # gates (a terminal legitimately taking precedence is not a shadow), so attribute the
        # cover from within the scoring region when this is a scoring gate.
        if gate.number >= _FIRST_SCORING_NUMBER:
            attributed = [s for s in own_states if _in_scoring_region(policy, s)]
        else:
            attributed = own_states
        pool = attributed or own_states
        coverers = {
            covering.number
            for state in pool
            if (covering := _first_true_gate(policy, state)) is not None
        }
        covering_rule = min(coverers) if coverers else 0
        errors.append(
            f"Rule {gate.number} unreachable: rule {covering_rule} covers "
            f"{gate.name} (all states where it holds fire an earlier rule)"
        )
    return errors


# --------------------------------------------------------------------------- #
# Ordering: terminal/review gates precede the pd-scoring approval gates.
# --------------------------------------------------------------------------- #
def check_ordering(gates: tuple[Gate, ...] = GATES) -> list[str]:
    errors: list[str] = []
    first_scoring = next((g.number for g in gates if g.outcome in APPROVAL_OUTCOMES), None)
    if first_scoring is None:
        return errors
    for gate in gates:
        is_gate_terminal = gate.outcome not in APPROVAL_OUTCOMES
        if is_gate_terminal and gate.number > first_scoring:
            errors.append(
                f"Rule {gate.number} ({gate.name}) is a terminal/review gate but is "
                f"ordered after scoring rule {first_scoring}"
            )
    return errors


# --------------------------------------------------------------------------- #
# Bounds: thresholds in sane ranges, terms ladder monotonic, budget under ceiling.
# --------------------------------------------------------------------------- #
def check_bounds(policy: PolicyRules) -> list[str]:
    errors: list[str] = []

    for name, value in (
        ("pd_enhanced", policy.pd_enhanced),
        ("pd_standard", policy.pd_standard),
        ("pd_decline_threshold", policy.pd_decline_threshold),
    ):
        if not (0.0 <= value <= 1.0):
            errors.append(f"{name}={value} outside [0, 1]")
    if not policy.pd_enhanced < policy.pd_standard < policy.pd_decline_threshold:
        errors.append(
            "pd thresholds must satisfy pd_enhanced < pd_standard < pd_decline_threshold "
            f"(got {policy.pd_enhanced}, {policy.pd_standard}, {policy.pd_decline_threshold})"
        )
    for name, value in (
        ("min_coverage", policy.min_coverage),
        ("cov_mid", policy.cov_mid),
        ("cov_high", policy.cov_high),
    ):
        if not (0 <= value <= 100):
            errors.append(f"{name}={value} outside [0, 100]")
    if not policy.cov_mid < policy.cov_high:
        errors.append(f"cov_mid ({policy.cov_mid}) must be < cov_high ({policy.cov_high})")

    if policy.exploration_margin < 0:
        errors.append(f"exploration_margin={policy.exploration_margin} must be >= 0")
    if not (0.0 <= policy.exploration_budget <= EXPLORATION_BUDGET_CEILING):
        errors.append(
            f"exploration_budget={policy.exploration_budget} must be in "
            f"[0, {EXPLORATION_BUDGET_CEILING}]"
        )
    if policy.mandatory_review_ceiling_paise < 0:
        errors.append("mandatory_review_ceiling_paise must be >= 0")

    # Terms ladder present and monotonic across bands (principal & tenor up, rate down).
    missing = [band for band in _APPROVAL_BAND_KEYS if band not in policy.terms]
    if missing:
        errors.append(f"terms ladder missing bands: {sorted(missing)}")
        return errors  # cannot check monotonicity without every band

    ladder = [policy.terms[name] for name in _LADDER_ORDER]
    for lower, higher in pairwise(ladder):
        if higher.max_principal_paise < lower.max_principal_paise:
            errors.append("terms ladder principal is not monotonic across bands")
        if higher.max_tenor_months < lower.max_tenor_months:
            errors.append("terms ladder tenor is not monotonic across bands")
        if higher.annual_rate_bps > lower.annual_rate_bps:
            errors.append("terms ladder rate must not increase for a higher band")
    return errors


# --------------------------------------------------------------------------- #
# The published entry point.
# --------------------------------------------------------------------------- #
def validate(policy: PolicyRules) -> ValidationResult:
    errors: list[str] = []
    errors.extend(check_bounds(policy))
    errors.extend(check_ordering())
    errors.extend(check_totality(policy))
    errors.extend(check_reachability(policy))
    return ValidationResult(ok=not errors, errors=tuple(errors))
