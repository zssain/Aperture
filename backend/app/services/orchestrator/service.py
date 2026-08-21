"""``decide`` - the single transactional path from evidence to a durable decision.

Invariants enforced here and nowhere else:
- No partial decision: all four assessments run in memory first; if any raises, we persist
  nothing and surface SYSTEM_UNAVAILABLE (invariant 2).
- One transaction: the decision, its reasons and the ledger entry commit together or not at
  all (invariant 4). The ledger append runs in THIS session's transaction, never a separate one.
- Recourse runs OUTSIDE that transaction, so a slow or failed recourse search can never roll
  back a committed decision.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.models.application import Application
from app.models.decision import Decision, DecisionReason, RecourseOption
from app.models.enums import DecisionAction
from app.models.feature import FeatureSnapshot
from app.services.audit import ledger
from app.services.features.service import compute_snapshot
from app.services.orchestrator.assessments import (
    AssessmentBundle,
    AssessmentFailureError,
    build_assessment_rows,
    loan_request,
    run_assessments,
    to_four_assessments,
)
from app.services.orchestrator.idempotency import find_existing_decision
from app.services.policy import store
from app.services.policy.engine import evaluate
from app.services.policy.schema import (
    PolicyDecision,
    PolicyOutcome,
    PolicyRules,
    Routing,
)
from app.services.recourse.engine import RecourseResult, search_recourse

# The policy engine's fine-grained outcome mapped to the stored DecisionAction enum.
OUTCOME_TO_ACTION: dict[PolicyOutcome, DecisionAction] = {
    PolicyOutcome.FRAUD_REVIEW: DecisionAction.REFER,
    PolicyOutcome.REVIEW_EVIDENCE: DecisionAction.REFER,
    PolicyOutcome.REVIEW_FRAUD: DecisionAction.REFER,
    PolicyOutcome.DECLINE_AFFORDABILITY: DecisionAction.DECLINE,
    PolicyOutcome.DECLINE_RISK: DecisionAction.DECLINE,
    PolicyOutcome.APPROVE_ENHANCED: DecisionAction.APPROVE,
    PolicyOutcome.APPROVE_STANDARD: DecisionAction.APPROVE,
    PolicyOutcome.APPROVE_STARTER: DecisionAction.APPROVE_STARTER,
}


class SystemUnavailableError(Exception):
    """An assessment failed (or a required input is missing); the route returns 503 and the
    case is routed SYSTEM_UNAVAILABLE. No decision was persisted."""

    def __init__(self, which: str) -> None:
        super().__init__(f"system unavailable: {which} could not be assessed")
        self.which = which


class ApplicationNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    policy_decision: PolicyDecision
    created: bool  # False when returned from idempotency
    recourse: RecourseResult | None = None


def _decision_payload(policy_decision: PolicyDecision, snapshot_id: uuid.UUID) -> dict[str, object]:
    return {
        "outcome": policy_decision.outcome,
        "routing": policy_decision.routing,
        "approved_limit_paise": policy_decision.approved_limit_paise,
        "policy_version": policy_decision.policy_version,
        "exploration_cohort": policy_decision.exploration_cohort,
        "feature_snapshot_id": str(snapshot_id),
        "fired_rules": [
            {"number": r.number, "name": r.name, "outcome": r.outcome}
            for r in policy_decision.fired_rules
        ],
    }


async def _persist_decision(
    session: AsyncSession,
    context: RequestContext,
    *,
    application: Application,
    snapshot: FeatureSnapshot,
    policy_version_id: uuid.UUID,
    bundle: AssessmentBundle,
    policy_decision: PolicyDecision,
    idempotency_key: str,
    supersedes_decision_id: uuid.UUID | None = None,
) -> Decision:
    """Persist assessments + decision + reasons and append the ledger entry, in ONE tx."""
    snapshot_id = snapshot.id
    for row in build_assessment_rows(bundle, tenant_id=context.tenant_id, snapshot=snapshot):
        session.add(row)

    outcome = PolicyOutcome(policy_decision.outcome)
    routing = policy_decision.routing
    decision = Decision(
        tenant_id=context.tenant_id,
        application_id=application.id,
        applicant_id=application.applicant_id,
        feature_snapshot_id=snapshot_id,
        policy_version_id=policy_version_id,
        action=OUTCOME_TO_ACTION[outcome],
        routing=routing,
        idempotency_key=idempotency_key,
        exploration_cohort=policy_decision.exploration_cohort,
        approved_limit_paise=policy_decision.approved_limit_paise,
        terms=_terms_dict(policy_decision),
        fired_rules=[
            {"number": r.number, "name": r.name, "outcome": r.outcome}
            for r in policy_decision.fired_rules
        ],
        is_final=routing == Routing.AUTOMATED.value,
    )
    session.add(decision)
    await session.flush()  # allocate decision.id for reasons + the ledger subject_id

    if supersedes_decision_id is not None:
        previous = await session.get(Decision, supersedes_decision_id)
        if (
            previous is None
            or previous.tenant_id != context.tenant_id
            or previous.application_id != application.id
            or previous.superseded_by is not None
        ):
            raise ValueError("decision to supersede is not the current application decision")
        # The database's decision trigger permits only this one NULL -> UUID link.
        previous.superseded_by = decision.id

    for order, reason in enumerate(policy_decision.reasons):
        session.add(
            DecisionReason(
                tenant_id=context.tenant_id,
                decision_id=decision.id,
                code=reason.code,
                message=reason.code,  # the notice renderer formats from template_params
                detail={
                    "polarity": reason.polarity,
                    "template_params": reason.template_params,
                    "order": order,
                },
            )
        )

    await ledger.append(
        session,
        context,
        event_type="DECISION_MADE",
        subject_type="decision",
        subject_id=decision.id,
        payload=_decision_payload(policy_decision, snapshot_id),
    )
    await session.commit()
    return decision


def _terms_dict(policy_decision: PolicyDecision) -> dict[str, object]:
    terms = policy_decision.terms
    if terms is None:
        return {}
    return {
        "band": terms.band,
        "max_principal_paise": terms.max_principal_paise,
        "approved_principal_paise": terms.approved_principal_paise,
        "max_tenor_months": terms.max_tenor_months,
        "approved_tenor_months": terms.approved_tenor_months,
        "rate_band": terms.rate_band,
        "annual_rate_bps": terms.annual_rate_bps,
        "graduation": terms.graduation,
    }


async def decide(
    session: AsyncSession,
    context: RequestContext,
    *,
    application_id: uuid.UUID,
    as_of: datetime,
    idempotency_key: str,
    supersedes_decision_id: uuid.UUID | None = None,
    generate_recourse: bool = True,
) -> DecisionResult:
    tenant_id = context.tenant_id

    existing = await find_existing_decision(
        session, tenant_id=tenant_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        return DecisionResult(
            decision=existing, policy_decision=_rehydrate(existing), created=False
        )

    application = await session.get(Application, application_id)
    if application is None or application.tenant_id != tenant_id:
        raise ApplicationNotFoundError("application not found")

    snapshot = await compute_snapshot(
        session, tenant_id=tenant_id, application_id=application_id, as_of=as_of
    )

    try:
        bundle = await run_assessments(
            session, tenant_id=tenant_id, snapshot=snapshot, application=application
        )
    except AssessmentFailureError as failure:
        raise SystemUnavailableError(failure.which) from failure

    live = await store.get_live_policy(session, tenant_id)
    policy_decision = evaluate(
        to_four_assessments(bundle), loan_request(application, snapshot), live.rules
    )

    if policy_decision.outcome == PolicyOutcome.SYSTEM_UNAVAILABLE.value:
        raise SystemUnavailableError("risk")

    try:
        decision = await _persist_decision(
            session,
            context,
            application=application,
            snapshot=snapshot,
            policy_version_id=live.row.id,
            bundle=bundle,
            policy_decision=policy_decision,
            idempotency_key=idempotency_key,
            supersedes_decision_id=supersedes_decision_id,
        )
    except IntegrityError:
        # Lost the concurrent race on the unique idempotency index: return the winner.
        await session.rollback()
        winner = await find_existing_decision(
            session, tenant_id=tenant_id, idempotency_key=idempotency_key
        )
        if winner is None:
            raise
        return DecisionResult(decision=winner, policy_decision=_rehydrate(winner), created=False)

    # Step 6: recourse runs OUTSIDE the committed decision transaction. A failure or timeout
    # here can never roll back the decision that already stands.
    recourse = None
    if generate_recourse:
        recourse = await _run_recourse(
            session,
            context,
            decision=decision,
            bundle=bundle,
            snapshot=snapshot,
            application=application,
            policy=live.rules,
            outcome=policy_decision.outcome,
        )

    return DecisionResult(
        decision=decision, policy_decision=policy_decision, created=True, recourse=recourse
    )


async def _run_recourse(
    session: AsyncSession,
    context: RequestContext,
    *,
    decision: Decision,
    bundle: AssessmentBundle,
    snapshot: FeatureSnapshot,
    application: Application,
    policy: PolicyRules,
    outcome: str,
) -> RecourseResult | None:
    # Recourse runs for any non-full-approval outcome.
    if outcome == PolicyOutcome.APPROVE_ENHANCED.value:
        return None

    try:
        result = search_recourse(
            four=to_four_assessments(bundle),
            coverage=bundle.coverage,
            snapshot=snapshot,
            request=loan_request(application, snapshot),
            policy=policy,
            now=datetime.now(UTC),
        )
    except Exception:
        return RecourseResult(options=(), no_viable_recourse=False, timed_out=True)

    for rank, option in enumerate(result.options):
        session.add(
            RecourseOption(
                tenant_id=context.tenant_id,
                decision_id=decision.id,
                rank=rank,
                description=f"{option.lever}: {option.projected_outcome}",
                required_change={
                    "lever": option.lever,
                    "target": option.target,
                    "params": option.params,
                    "projected_delta": option.projected_delta,
                    "expires_at": option.expires_at.isoformat(),
                },
                projected_action=OUTCOME_TO_ACTION.get(PolicyOutcome(option.projected_outcome)),
                projected_limit_paise=option.projected_limit_paise,
                verified=True,
            )
        )
    if result.options:
        await session.commit()
    return result


def _rehydrate(decision: Decision) -> PolicyDecision:
    """Reconstruct a lightweight PolicyDecision view from a stored decision (for the response)."""
    from app.services.policy.schema import Terms

    terms_raw = decision.terms or {}
    terms = None
    if terms_raw:
        terms = Terms(
            band=str(terms_raw.get("band", "")),
            max_principal_paise=int(terms_raw.get("max_principal_paise", 0)),
            approved_principal_paise=int(terms_raw.get("approved_principal_paise", 0)),
            max_tenor_months=int(terms_raw.get("max_tenor_months", 0)),
            approved_tenor_months=int(terms_raw.get("approved_tenor_months", 0)),
            rate_band=str(terms_raw.get("rate_band", "")),
            annual_rate_bps=int(terms_raw.get("annual_rate_bps", 0)),
            graduation=terms_raw.get("graduation"),
        )
    return PolicyDecision(
        outcome=_action_outcome_hint(decision),
        routing=decision.routing,
        terms=terms,
        approved_limit_paise=decision.approved_limit_paise,
        fired_rules=(),
        reasons=(),
        exploration_cohort=decision.exploration_cohort,
        policy_version="",
        reasons_catalogue_version="",
    )


def _action_outcome_hint(decision: Decision) -> str:
    # The stored fired_rules carry the precise outcome; fall back to the coarse action.
    for rule in reversed(decision.fired_rules or []):
        if isinstance(rule, dict) and rule.get("outcome"):
            return str(rule["outcome"])
    return decision.action.value
