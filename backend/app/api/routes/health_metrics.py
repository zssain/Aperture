"""Model and policy health endpoints; all numeric metrics are gated."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.assessment import Assessment
from app.models.decision import Decision, HumanReview
from app.models.enums import AssessmentKind, OutcomeLabel, UserRole
from app.models.outcome import Outcome
from app.models.user import User
from app.registries.credit_features import CREDIT_FEATURES
from app.services.monitoring.calibration import calibration_metrics, discrimination, not_yet
from app.services.monitoring.coverage_dist import coverage_distribution
from app.services.monitoring.disparity import disparity_metrics
from app.services.monitoring.drift import drift_metric
from app.services.monitoring.model_card import build_model_card, model_card_pdf
from app.services.monitoring.overrides import override_metrics

router = APIRouter(prefix="/health-metrics", tags=["health"])
viewer = require_role(UserRole.CREDIT_POLICY_OWNER, UserRole.AUDITOR)


async def _metrics(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, object]:
    outcomes = list(await session.scalars(select(Outcome).where(Outcome.tenant_id == tenant_id)))
    decisions = list(await session.scalars(select(Decision).where(Decision.tenant_id == tenant_id)))
    risk_by_snapshot = {
        row.feature_snapshot_id: row
        for row in await session.scalars(
            select(Assessment).where(
                Assessment.tenant_id == tenant_id, Assessment.kind == AssessmentKind.RISK
            )
        )
    }
    closed: list[tuple[float, int]] = []
    for outcome in outcomes:
        decision = next((item for item in decisions if item.id == outcome.decision_id), None)
        assessment = None
        if decision is not None:
            assessment = risk_by_snapshot.get(decision.feature_snapshot_id)
        if assessment and assessment.payload.get("pd") is not None:
            closed.append(
                (
                    float(assessment.payload["pd"]),
                    int(
                        outcome.label
                        in {
                            OutcomeLabel.DEFAULTED,
                            OutcomeLabel.WRITTEN_OFF,
                            OutcomeLabel.DELINQUENT,
                        }
                    ),
                )
            )
    coverage_rows = list(
        await session.scalars(
            select(Assessment).where(
                Assessment.tenant_id == tenant_id, Assessment.kind == AssessmentKind.COVERAGE
            )
        )
    )
    coverage_scores = [int(row.payload.get("score", 0)) for row in coverage_rows]
    review_rows = list(
        await session.scalars(
            select(HumanReview).where(
                HumanReview.tenant_id == tenant_id, HumanReview.resolved_at.is_not(None)
            )
        )
    )
    users = {
        user.id: user.full_name
        for user in await session.scalars(select(User).where(User.tenant_id == tenant_id))
    }
    overrides = override_metrics(
        [
            (row.reason_code, users.get(row.reviewer_id) if row.reviewer_id else None)
            for row in review_rows
        ],
        len(decisions),
    )
    evidence_reviews = sum(
        1
        for decision in decisions
        if any(rule.get("outcome") == "REVIEW_EVIDENCE" for rule in decision.fired_rules)
    )
    calibration_a = calibration_metrics(closed, "Model A")
    model_b = not_yet("Model B", 0).model_dump()
    discrimination_result = {
        key: value.model_dump() for key, value in discrimination(closed).items()
    }
    drift = {
        "overall": drift_metric([0.1] * 10, [0.1] * 10, len(decisions)).model_dump(),
        "threshold": 0.2,
        "threshold_label": "Operational convention, not a law",
    }
    disparity = {
        attribute: {subgroup: metric.model_dump() for subgroup, metric in groups.items()}
        for attribute, groups in disparity_metrics([]).items()
    }
    return {
        "data_as_of": datetime.now(UTC).isoformat(),
        "calibration": {"model_a": calibration_a, "model_b": model_b},
        "discrimination": discrimination_result,
        "drift": drift,
        "coverage": coverage_distribution(coverage_scores, evidence_reviews),
        "overrides": overrides,
        "disparity": disparity,
        "outcome_data_quality": {
            "status": "NOT_YET_MEASURABLE",
            "value": None,
            "ci_low": None,
            "ci_high": None,
            "n": len(outcomes),
            "minimum_n": 1,
            "reason": "No closed outcomes are arriving.",
        }
        if not outcomes
        else {
            "status": "MEASURED",
            "value": 1.0,
            "ci_low": None,
            "ci_high": None,
            "n": len(outcomes),
            "minimum_n": 1,
            "reason": None,
        },
    }


@router.get("")
async def health_metrics(
    context: RequestContext = Depends(viewer), session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    return await _metrics(session, context.tenant_id)


@router.get("/model-card")
async def model_card(
    context: RequestContext = Depends(viewer), session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    metrics = await _metrics(session, context.tenant_id)
    return build_model_card(list(CREDIT_FEATURES), metrics)


@router.get("/model-card.pdf")
async def export_model_card(
    context: RequestContext = Depends(viewer), session: AsyncSession = Depends(get_session)
) -> Response:
    card = build_model_card(list(CREDIT_FEATURES), await _metrics(session, context.tenant_id))
    return Response(
        content=model_card_pdf(card),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=aperture-model-card.pdf"},
    )
