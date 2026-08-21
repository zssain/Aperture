"""Cohort policy simulation using only persisted snapshots and assessments."""

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.assessment import Assessment
from app.models.decision import Decision
from app.models.enums import AssessmentKind
from app.models.feature import FeatureSnapshot
from app.models.policy import PolicyVersion
from app.services.orchestrator.assessments import loan_request
from app.services.orchestrator.service import OUTCOME_TO_ACTION
from app.services.policy.engine import evaluate
from app.services.policy.schema import (
    AffordabilityInput,
    CoverageInput,
    FourAssessments,
    ManipulationInput,
    MissingSourceInput,
    PolicyOutcome,
    PolicyRules,
    RiskInput,
)

UNCALIBRATED_CAVEAT = (
    "Loss estimates inherit the cash-flow scorecard's UNCALIBRATED status and are directional only."
)


def policy_hash(rules: dict[str, Any]) -> str:
    canonical = json.dumps(rules, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _four(rows: list[Assessment]) -> FourAssessments | None:
    by_kind = {row.kind: row.payload for row in rows}
    if set(by_kind) != set(AssessmentKind):
        return None
    risk = by_kind[AssessmentKind.RISK]
    coverage = by_kind[AssessmentKind.COVERAGE]
    affordability = by_kind[AssessmentKind.AFFORDABILITY]
    manipulation = by_kind[AssessmentKind.MANIPULATION]
    return FourAssessments(
        risk=RiskInput(
            pd=risk.get("pd"),
            calibration_status=str(risk.get("calibration_status", "UNCALIBRATED")),
            reason_codes=tuple(risk.get("reason_codes") or ()),
        ),
        coverage=CoverageInput(
            score=int(coverage.get("score", 0)),
            band=str(coverage.get("band", "LOW")),
            missing_sources=tuple(
                MissingSourceInput(
                    source_type=str(item.get("source_type", "unknown")),
                    coverage_delta=int(item.get("coverage_delta", 0)),
                )
                for item in coverage.get("missing_sources", [])
            ),
        ),
        affordability=AffordabilityInput(
            status=str(affordability.get("status", "INDETERMINATE")),
            max_supportable_principal_paise=affordability.get("max_supportable_principal_paise"),
            dsr=affordability.get("dsr"),
            dsr_ceiling=affordability.get("dsr_ceiling"),
        ),
        manipulation=ManipulationInput(band=str(manipulation.get("band", "HIGH"))),
    )


def _approved(action: str) -> bool:
    return action in {"APPROVE", "APPROVE_STARTER"}


def _cohorts(snapshot: FeatureSnapshot) -> tuple[str, ...]:
    values = snapshot.values
    result = ["all"]
    if values.get("bureau_score") is None:
        result.append("no_bureau_file")
    if int(values.get("history_depth_days") or 0) < 180:
        result.append("thin_file")
    return tuple(result)


async def simulate_policy(
    session: AsyncSession, *, tenant_id: uuid.UUID, policy_id: uuid.UUID
) -> dict[str, Any]:
    policy = await session.get(PolicyVersion, policy_id)
    if policy is None or policy.tenant_id != tenant_id:
        raise ValueError("policy version not found")
    rules = PolicyRules(**policy.rules)
    decisions = list(
        await session.scalars(
            select(Decision)
            .where(Decision.tenant_id == tenant_id)
            .order_by(Decision.created_at.desc())
        )
    )
    # Keep the newest decision for each immutable snapshot, then bulk-load every
    # dependency. This makes full-book simulation O(1) database round trips rather
    # than an N+1 query loop and keeps the 10,000-case path comfortably asynchronous.
    unique_decisions: list[Decision] = []
    seen_snapshots: set[uuid.UUID] = set()
    for decision in decisions:
        if decision.feature_snapshot_id not in seen_snapshots:
            unique_decisions.append(decision)
            seen_snapshots.add(decision.feature_snapshot_id)
    snapshot_ids = [row.feature_snapshot_id for row in unique_decisions]
    application_ids = [row.application_id for row in unique_decisions]
    snapshots = {
        row.id: row
        for row in await session.scalars(
            select(FeatureSnapshot).where(
                FeatureSnapshot.tenant_id == tenant_id, FeatureSnapshot.id.in_(snapshot_ids)
            )
        )
    }
    applications = {
        row.id: row
        for row in await session.scalars(
            select(Application).where(
                Application.tenant_id == tenant_id, Application.id.in_(application_ids)
            )
        )
    }
    assessments_by_snapshot: dict[uuid.UUID, list[Assessment]] = defaultdict(list)
    for assessment in await session.scalars(
        select(Assessment).where(
            Assessment.tenant_id == tenant_id,
            Assessment.feature_snapshot_id.in_(snapshot_ids),
        )
    ):
        assessments_by_snapshot[assessment.feature_snapshot_id].append(assessment)
    transition: Counter[str] = Counter()
    cohort_counts: dict[str, Counter[str]] = defaultdict(Counter)
    flips: list[dict[str, Any]] = []
    total_live_approved = total_draft_approved = 0
    processed = 0
    for decision in unique_decisions:
        snapshot = snapshots.get(decision.feature_snapshot_id)
        application = applications.get(decision.application_id)
        if snapshot is None or application is None:
            continue
        four = _four(assessments_by_snapshot[snapshot.id])
        if four is None:
            continue
        evaluated = evaluate(four, loan_request(application, snapshot), rules)
        mapped = OUTCOME_TO_ACTION.get(PolicyOutcome(evaluated.outcome))
        draft_action = mapped.value if mapped else evaluated.outcome
        live_action = decision.action.value
        processed += 1
        transition[f"{live_action}->{draft_action}"] += 1
        total_live_approved += int(_approved(live_action))
        total_draft_approved += int(_approved(draft_action))
        for cohort in _cohorts(snapshot):
            cohort_counts[cohort]["n"] += 1
            cohort_counts[cohort]["live"] += int(_approved(live_action))
            cohort_counts[cohort]["draft"] += int(_approved(draft_action))
        if live_action != draft_action:
            flips.append(
                {
                    "application_id": str(application.id),
                    "decision_id": str(decision.id),
                    "from": live_action,
                    "to": draft_action,
                    "pd": four.risk.pd if four.risk else None,
                    "coverage_score": four.coverage.score if four.coverage else None,
                }
            )
    cohort_deltas = {
        name: {
            "n": values["n"],
            "approval_delta": (
                (values["draft"] - values["live"]) / values["n"] if values["n"] else 0.0
            ),
        }
        for name, values in cohort_counts.items()
        if name != "all"
    }
    approval_delta = (total_draft_approved - total_live_approved) / processed if processed else 0.0
    # With an uncalibrated scorecard these are intentionally labelled directional.
    return {
        "draft_hash": policy_hash(policy.rules),
        "n_snapshots": processed,
        "approval_delta": approval_delta,
        "cohort_deltas": cohort_deltas,
        "transition_matrix": dict(sorted(transition.items())),
        "modelled_bad_rate_delta": -approval_delta * 0.15,
        "expected_loss_delta": -approval_delta * 0.10,
        "caveats": [UNCALIBRATED_CAVEAT],
        "largest_flips": flips[:10],
    }
