"""Deterministic replay - the permanent release gate.

``replay`` loads the STORED feature snapshot (never recomputes it - recomputation would test
the wrong thing), reuses the stored risk payload when the recorded model version still matches
(re-running the deterministic assessments otherwise), re-evaluates the policy, and compares the
result to the stored decision field by field.

Replaying under the recorded policy must be IDENTICAL. Replaying under a *different* policy
version returns the counterfactual outcome - the primitive Prompt 16's simulation reuses.
"""

import uuid
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.assessment import Assessment
from app.models.decision import Decision
from app.models.enums import AssessmentKind
from app.models.feature import FeatureSnapshot
from app.models.policy import PolicyVersion
from app.services.orchestrator.assessments import (
    loan_request,
    run_assessments,
    to_four_assessments,
)
from app.services.orchestrator.service import OUTCOME_TO_ACTION, _terms_dict
from app.services.policy.engine import evaluate
from app.services.policy.schema import (
    ContributorInput,
    PolicyOutcome,
    PolicyRules,
    RiskInput,
)

IDENTICAL = "IDENTICAL"
DIVERGED = "DIVERGED"


class ReplayError(Exception):
    pass


@dataclass(frozen=True)
class ReplayResult:
    status: str  # IDENTICAL | DIVERGED
    diff: dict[str, dict[str, Any]]
    recomputed_outcome: str
    recomputed_action: str
    stored_action: str
    policy_version_id: uuid.UUID
    counterfactual: bool
    reused_risk: bool


def _risk_from_stored(payload: dict[str, Any]) -> RiskInput:
    contributions = payload.get("contributions") or []
    ranked = sorted(contributions, key=lambda c: -abs(float(c.get("contribution", 0.0))))
    contributors = tuple(
        ContributorInput(
            feature=str(c["feature"]),
            contribution=float(c["contribution"]),
            direction="increases_risk" if float(c["contribution"]) > 0 else "decreases_risk",
        )
        for c in ranked[:5]
        if "feature" in c and "contribution" in c
    )
    return RiskInput(
        pd=payload.get("pd"),
        calibration_status=str(payload.get("calibration_status", "UNCALIBRATED")),
        top_contributors=contributors,
        reason_codes=tuple(payload.get("reason_codes") or ()),
    )


async def _load_policy_rules(
    session: AsyncSession, tenant_id: uuid.UUID, policy_version_id: uuid.UUID
) -> PolicyRules:
    row = await session.get(PolicyVersion, policy_version_id)
    if row is None or row.tenant_id != tenant_id:
        raise ReplayError("policy version not found")
    return PolicyRules(**row.rules)


async def replay(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    decision_id: uuid.UUID,
    policy_version_id: uuid.UUID | None = None,
) -> ReplayResult:
    decision = await session.get(Decision, decision_id)
    if decision is None or decision.tenant_id != tenant_id:
        raise ReplayError("decision not found")

    # The STORED snapshot - never recomputed.
    snapshot = await session.get(FeatureSnapshot, decision.feature_snapshot_id)
    application = await session.get(Application, decision.application_id)
    if snapshot is None or application is None:
        raise ReplayError("stored snapshot or application missing")

    counterfactual = (
        policy_version_id is not None and policy_version_id != decision.policy_version_id
    )
    effective_policy_id = policy_version_id or decision.policy_version_id
    rules = await _load_policy_rules(session, tenant_id, effective_policy_id)

    # Re-run the deterministic assessments over the stored snapshot.
    bundle = await run_assessments(
        session, tenant_id=tenant_id, snapshot=snapshot, application=application
    )
    four = to_four_assessments(bundle)

    # Reuse the stored risk payload when its recorded model version still matches.
    stored_risk = await session.scalar(
        select(Assessment).where(
            Assessment.feature_snapshot_id == snapshot.id,
            Assessment.kind == AssessmentKind.RISK,
        )
    )
    reused_risk = False
    if stored_risk is not None and stored_risk.payload.get("model_version") == (
        bundle.risk.model_version
    ):
        reused_risk = True
        four = replace(four, risk=_risk_from_stored(stored_risk.payload))

    recomputed = evaluate(four, loan_request(application, snapshot), rules)
    recomputed_action = OUTCOME_TO_ACTION.get(PolicyOutcome(recomputed.outcome))
    recomputed_action_value = recomputed_action.value if recomputed_action else recomputed.outcome

    diff = _diff(decision, recomputed, recomputed_action_value)
    status = IDENTICAL if not diff else DIVERGED
    return ReplayResult(
        status=status,
        diff=diff,
        recomputed_outcome=recomputed.outcome,
        recomputed_action=recomputed_action_value,
        stored_action=decision.action.value,
        policy_version_id=effective_policy_id,
        counterfactual=counterfactual,
        reused_risk=reused_risk,
    )


def _diff(decision: Decision, recomputed: Any, recomputed_action: str) -> dict[str, dict[str, Any]]:
    fields: dict[str, tuple[Any, Any]] = {
        "action": (decision.action.value, recomputed_action),
        "routing": (decision.routing, recomputed.routing),
        "approved_limit_paise": (decision.approved_limit_paise, recomputed.approved_limit_paise),
        "exploration_cohort": (decision.exploration_cohort, recomputed.exploration_cohort),
        "terms": (decision.terms or {}, _terms_dict(recomputed)),
        "fired_rules": (
            [(r.get("number"), r.get("outcome")) for r in (decision.fired_rules or [])],
            [(r.number, r.outcome) for r in recomputed.fired_rules],
        ),
    }
    return {
        name: {"stored": stored, "recomputed": got}
        for name, (stored, got) in fields.items()
        if stored != got
    }
