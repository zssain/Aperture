"""Compare immutable decisions and persist a specific, explainable change record."""

import math
import uuid
from decimal import Decimal
from typing import Any

from app.core.context import RequestContext
from app.models.assessment import Assessment
from app.models.change import DecisionChange
from app.models.decision import Decision
from app.models.enums import AssessmentKind
from app.models.feature import FeatureSnapshot
from app.services.audit import ledger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_LABELS = {
    "monthly_inflow_cv": "Income consistency",
    "median_monthly_inflow_paise": "Median monthly income",
    "coverage_days": "Evidence coverage",
    "inflow_months_count": "Income months observed",
}
_RANK = {"DECLINE": 0, "REVIEW": 1, "STARTER": 2, "STANDARD": 3, "ENHANCED": 4}
_RISK_SCALES: dict[str, tuple[float, float, float]] = {
    "median_monthly_inflow_paise": (0.0, 10_000_000.0, 1.4),
    "monthly_inflow_cv": (0.0, 1.0, 1.5),
    "inflow_trend_ratio": (0.5, 1.5, 0.8),
    "debt_service_ratio": (0.0, 1.0, 1.6),
    "essential_expense_ratio": (0.0, 1.5, 1.0),
    "balance_min_to_mean_ratio": (0.0, 1.0, 1.0),
    "mean_balance_paise": (0.0, 5_000_000.0, 1.0),
    "other_share": (0.0, 0.5, 1.2),
    "history_depth_days": (0.0, 365.0, 0.9),
}


def outcome(decision: Decision) -> str:
    for rule in reversed(decision.fired_rules or []):
        if isinstance(rule, dict) and rule.get("outcome"):
            return str(rule["outcome"])
    return decision.action.value


def band(decision: Decision) -> str:
    exact = outcome(decision)
    if exact.startswith("DECLINE"):
        return "DECLINE"
    if exact.startswith("REVIEW") or exact == "FRAUD_REVIEW" or decision.routing == "HUMAN":
        return "REVIEW"
    if exact == "APPROVE_STARTER":
        return "STARTER"
    if exact == "APPROVE_STANDARD":
        return "STANDARD"
    if exact == "APPROVE_ENHANCED":
        return "ENHANCED"
    return decision.action.value


async def _metric(
    session: AsyncSession,
    snapshot_id: uuid.UUID,
    kind: AssessmentKind,
    key: str,
) -> int | float | None:
    row = await session.scalar(
        select(Assessment).where(
            Assessment.feature_snapshot_id == snapshot_id, Assessment.kind == kind
        )
    )
    value = row.payload.get(key) if row else None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _feature_moves(
    before: dict[str, Any], after: dict[str, Any], limit: int = 5
) -> list[dict[str, Any]]:
    moves: list[tuple[float, dict[str, Any]]] = []
    for key in before.keys() | after.keys():
        old, new = before.get(key), after.get(key)
        if old == new or isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
            continue
        item = {
            "feature_key": key,
            "label": _LABELS.get(key, key.replace("_", " ").title()),
            "before": old,
            "after": new,
        }
        score = 0.0
        if (
            isinstance(old, (int, float))
            and isinstance(new, (int, float))
            and not isinstance(old, bool)
            and not isinstance(new, bool)
        ):
            delta = float(new) - float(old)
            item["delta"] = delta
            if key in _RISK_SCALES:
                low, high, weight = _RISK_SCALES[key]
                old_scaled = min(1.0, max(0.0, (float(old) - low) / (high - low)))
                new_scaled = min(1.0, max(0.0, (float(new) - low) / (high - low)))
                score = abs(new_scaled - old_scaled) * weight
            else:
                # Non-model features remain useful context but do not displace the
                # credit features that actually moved the score.
                score = abs(delta) / max(abs(float(old)), 1.0) * 0.001
        else:
            score = math.inf
        moves.append((score, item))
    moves.sort(key=lambda pair: (-pair[0], pair[1]["feature_key"]))
    return [item for _, item in moves[:limit]]


async def detect_change(
    session: AsyncSession,
    context: RequestContext,
    *,
    previous: Decision,
    new: Decision,
    human_action_protected: bool,
) -> DecisionChange:
    existing = await session.scalar(
        select(DecisionChange).where(DecisionChange.new_decision_id == new.id)
    )
    if existing is not None:
        return existing
    old_snapshot = await session.get(FeatureSnapshot, previous.feature_snapshot_id)
    new_snapshot = await session.get(FeatureSnapshot, new.feature_snapshot_id)
    assert old_snapshot is not None and new_snapshot is not None
    old_band, new_band = band(previous), band(new)
    old_pd = await _metric(session, previous.feature_snapshot_id, AssessmentKind.RISK, "pd")
    new_pd = await _metric(session, new.feature_snapshot_id, AssessmentKind.RISK, "pd")
    old_coverage = await _metric(
        session, previous.feature_snapshot_id, AssessmentKind.COVERAGE, "score"
    )
    new_coverage = await _metric(session, new.feature_snapshot_id, AssessmentKind.COVERAGE, "score")
    direction = "UNCHANGED"
    if _RANK.get(new_band, 0) > _RANK.get(old_band, 0):
        direction = "IMPROVED"
    elif _RANK.get(new_band, 0) < _RANK.get(old_band, 0):
        direction = "WORSENED"
    change = DecisionChange(
        tenant_id=context.tenant_id,
        applicant_id=new.applicant_id,
        application_id=new.application_id,
        previous_decision_id=previous.id,
        new_decision_id=new.id,
        direction=direction,
        previous_band=old_band,
        new_band=new_band,
        previous_outcome=outcome(previous),
        new_outcome=outcome(new),
        pd_delta_ppb=(
            int((Decimal(str(new_pd)) - Decimal(str(old_pd))) * Decimal(1_000_000_000))
            if old_pd is not None and new_pd is not None
            else None
        ),
        coverage_delta=int(new_coverage - old_coverage)
        if old_coverage is not None and new_coverage is not None
        else None,
        feature_changes=_feature_moves(dict(old_snapshot.values), dict(new_snapshot.values)),
        human_action_protected=human_action_protected,
    )
    session.add(change)
    await session.flush()
    await ledger.append(
        session,
        context,
        event_type="DECISION_CHANGED",
        subject_type="decision_change",
        subject_id=change.id,
        payload={
            "previous_decision_id": str(previous.id),
            "new_decision_id": str(new.id),
            "direction": direction,
            "human_action_protected": human_action_protected,
        },
    )
    await session.commit()
    return change
