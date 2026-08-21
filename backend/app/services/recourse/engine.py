"""Recourse search: verified, actionable paths from a non-approval to a better outcome.

Every option returned here was PROVEN to flip the decision by re-running the policy engine
with the perturbation applied - never a softened or hypothetical offer. The search is
time-boxed; if nothing flips (or the box expires) it returns an explicit empty result with
``no_viable_recourse`` rather than inventing an option. At most three options, easiest first.

Only the registered, actionable levers are searched (see levers.py), so recourse can never
suggest changing a protected or immutable attribute.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from app.models.feature import FeatureSnapshot
from app.services.affordability.service import RequestedTerms, assess_affordability
from app.services.coverage.service import CoverageAssessment
from app.services.policy.engine import evaluate
from app.services.policy.schema import (
    APPROVAL_OUTCOMES,
    AffordabilityInput,
    FourAssessments,
    LoanRequest,
    PolicyOutcome,
    PolicyRules,
)
from app.services.policy.terms import build_terms
from app.services.recourse import levers

# Desirability of each outcome; an option must strictly raise this to be offered.
_RANK: dict[str, int] = {
    PolicyOutcome.SYSTEM_UNAVAILABLE.value: -1,
    PolicyOutcome.FRAUD_REVIEW.value: 0,
    PolicyOutcome.REVIEW_EVIDENCE.value: 0,
    PolicyOutcome.REVIEW_FRAUD.value: 0,
    PolicyOutcome.DECLINE_AFFORDABILITY.value: 0,
    PolicyOutcome.DECLINE_RISK.value: 0,
    PolicyOutcome.APPROVE_STARTER.value: 1,
    PolicyOutcome.APPROVE_STANDARD.value: 2,
    PolicyOutcome.APPROVE_ENHANCED.value: 3,
}

_MAX_OPTIONS = 3
_AMOUNT_QUANTUM_PAISE = 100_000  # quantise reduced amounts to whole rupees-thousands


@dataclass(frozen=True)
class RecourseOption:
    lever: str
    target: str
    params: dict[str, Any]
    projected_outcome: str
    projected_delta: dict[str, Any]
    projected_limit_paise: int | None
    effort_rank: int
    policy_version: str
    expires_at: datetime


@dataclass(frozen=True)
class RecourseResult:
    options: tuple[RecourseOption, ...]
    no_viable_recourse: bool
    timed_out: bool


def _improves(current: str, candidate: str) -> bool:
    return candidate in {o.value for o in APPROVAL_OUTCOMES} and _RANK.get(
        candidate, -1
    ) > _RANK.get(current, -1)


def _add_source_option(
    four: FourAssessments,
    coverage: CoverageAssessment,
    request: LoanRequest,
    policy: PolicyRules,
    current: str,
    expires_at: datetime,
) -> RecourseOption | None:
    assert four.coverage is not None
    for gap in sorted(coverage.missing_sources, key=lambda m: -m.coverage_delta):
        if gap.coverage_delta <= 0:
            continue
        new_score = min(100, four.coverage.score + gap.coverage_delta)
        perturbed = replace(four, coverage=replace(four.coverage, score=new_score))
        result = evaluate(perturbed, request, policy)
        if _improves(current, result.outcome):
            return RecourseOption(
                lever=levers.ADD_SOURCE.name,
                target=levers.ADD_SOURCE.target,
                params={"source_type": gap.source_type},
                projected_outcome=result.outcome,
                projected_delta={"coverage_score": gap.coverage_delta},
                projected_limit_paise=result.approved_limit_paise,
                effort_rank=levers.ADD_SOURCE.effort_rank,
                policy_version=policy.policy_version,
                expires_at=expires_at,
            )
    return None


def _extend_history_option(
    four: FourAssessments,
    coverage: CoverageAssessment,
    request: LoanRequest,
    policy: PolicyRules,
    current: str,
    expires_at: datetime,
) -> RecourseOption | None:
    assert four.coverage is not None
    depth = next((c for c in coverage.components if c.name == "history_depth"), None)
    if depth is None or depth.fraction >= 1.0:
        return None
    # Bringing history to the full required window lifts the depth component to its full weight.
    delta = round(depth.weight * (1.0 - depth.fraction))
    if delta <= 0:
        return None
    new_score = min(100, four.coverage.score + delta)
    perturbed = replace(four, coverage=replace(four.coverage, score=new_score))
    result = evaluate(perturbed, request, policy)
    if not _improves(current, result.outcome):
        return None
    return RecourseOption(
        lever=levers.EXTEND_HISTORY.name,
        target=levers.EXTEND_HISTORY.target,
        params={"to_full_window": True},
        projected_outcome=result.outcome,
        projected_delta={"coverage_score": delta},
        projected_limit_paise=result.approved_limit_paise,
        effort_rank=levers.EXTEND_HISTORY.effort_rank,
        policy_version=policy.policy_version,
        expires_at=expires_at,
    )


def _reduce_amount_option(
    four: FourAssessments,
    snapshot: FeatureSnapshot,
    request: LoanRequest,
    policy: PolicyRules,
    current: str,
    expires_at: datetime,
) -> RecourseOption | None:
    assert four.affordability is not None
    supportable = four.affordability.max_supportable_principal_paise
    if supportable is None or supportable <= 0 or supportable >= request.amount_paise:
        return None
    target_amount = (supportable // _AMOUNT_QUANTUM_PAISE) * _AMOUNT_QUANTUM_PAISE
    if target_amount <= 0:
        return None
    reassessed = assess_affordability(
        snapshot,
        RequestedTerms(
            amount_paise=target_amount,
            tenor_months=request.tenor_months,
            annual_rate_bps=request.annual_rate_bps,
        ),
    )
    perturbed = replace(
        four,
        affordability=AffordabilityInput(
            status=reassessed.status,
            max_supportable_principal_paise=reassessed.max_supportable_principal_paise,
            dsr=reassessed.dsr,
            dsr_ceiling=reassessed.dsr_ceiling,
        ),
    )
    reduced_request = replace(request, amount_paise=target_amount)
    result = evaluate(perturbed, reduced_request, policy)
    if not _improves(current, result.outcome):
        return None
    return RecourseOption(
        lever=levers.REDUCE_AMOUNT.name,
        target=levers.REDUCE_AMOUNT.target,
        params={"amount_paise": target_amount},
        projected_outcome=result.outcome,
        projected_delta={"requested_amount_paise": target_amount - request.amount_paise},
        projected_limit_paise=result.approved_limit_paise,
        effort_rank=levers.REDUCE_AMOUNT.effort_rank,
        policy_version=policy.policy_version,
        expires_at=expires_at,
    )


def _accept_starter_option(
    four: FourAssessments,
    request: LoanRequest,
    policy: PolicyRules,
    current: str,
    expires_at: datetime,
) -> RecourseOption | None:
    # Only offered on a near-boundary risk decline with a clean, affordable profile.
    if current != PolicyOutcome.DECLINE_RISK.value:
        return None
    assert four.risk is not None and four.affordability is not None
    pd = four.risk.pd
    if pd is None or four.affordability.status != "PASS":
        return None
    if pd > policy.pd_decline_threshold + policy.exploration_margin:
        return None
    terms = build_terms(PolicyOutcome.APPROVE_STARTER.value, policy, four.affordability, request)
    return RecourseOption(
        lever=levers.ACCEPT_STARTER.name,
        target=levers.ACCEPT_STARTER.target,
        params={"band": PolicyOutcome.APPROVE_STARTER.value},
        projected_outcome=PolicyOutcome.APPROVE_STARTER.value,
        projected_delta={"band": PolicyOutcome.APPROVE_STARTER.value},
        projected_limit_paise=terms.approved_principal_paise,
        effort_rank=levers.ACCEPT_STARTER.effort_rank,
        policy_version=policy.policy_version,
        expires_at=expires_at,
    )


def search_recourse(
    *,
    four: FourAssessments,
    coverage: CoverageAssessment,
    snapshot: FeatureSnapshot,
    request: LoanRequest,
    policy: PolicyRules,
    now: datetime,
    deadline_seconds: float = 1.0,
    ttl_days: int = 30,
) -> RecourseResult:
    baseline = evaluate(four, request, policy)
    current = baseline.outcome
    expires_at = now + timedelta(days=ttl_days)

    # A full approval needs no recourse.
    if current == PolicyOutcome.APPROVE_ENHANCED.value:
        return RecourseResult(options=(), no_viable_recourse=False, timed_out=False)

    start = time.monotonic()
    options: list[RecourseOption] = []
    timed_out = False

    # Ordered easiest-first; the search is time-boxed between candidates.
    candidates: tuple[Callable[[], RecourseOption | None], ...] = (
        lambda: _accept_starter_option(four, request, policy, current, expires_at),
        lambda: _reduce_amount_option(four, snapshot, request, policy, current, expires_at),
        lambda: _add_source_option(four, coverage, request, policy, current, expires_at),
        lambda: _extend_history_option(four, coverage, request, policy, current, expires_at),
    )
    for candidate in candidates:
        if time.monotonic() - start >= deadline_seconds:
            timed_out = True
            break
        option = candidate()
        if option is not None:
            options.append(option)

    options.sort(key=lambda o: o.effort_rank)
    capped = tuple(options[:_MAX_OPTIONS])
    return RecourseResult(
        options=capped,
        no_viable_recourse=not capped and not timed_out,
        timed_out=timed_out,
    )
