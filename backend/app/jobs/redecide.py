"""Idempotent event-driven re-decision job handler."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.models.application import Application
from app.models.change import RedecisionAlert
from app.models.consent import Consent
from app.models.decision import Decision, HumanReview
from app.models.enums import ApplicationStatus, ConsentStatus, ReviewStatus
from app.models.feature import FeatureSnapshot
from app.models.job import Job
from app.services.decisions.change_detector import detect_change
from app.services.orchestrator.idempotency import find_existing_decision
from app.services.orchestrator.service import decide


def _uuid(value: object) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def handle_redecide(
    session: AsyncSession, job: Job, context: RequestContext
) -> dict[str, Any]:
    application_id = _uuid(job.payload["application_id"])
    application = await session.get(Application, application_id)
    if application is None or application.tenant_id != context.tenant_id:
        return {"status": "NOT_FOUND"}
    revoked_consent = await session.scalar(
        select(Consent.id).where(
            Consent.tenant_id == context.tenant_id,
            Consent.applicant_id == application.applicant_id,
            Consent.status == ConsentStatus.REVOKED,
        )
    )
    if revoked_consent is not None:
        return {"status": "CONSENT_REVOKED", "application_id": str(application_id)}
    key = f"redecide:{job.id}"
    previous = await session.scalar(
        select(Decision)
        .where(
            Decision.tenant_id == context.tenant_id,
            Decision.application_id == application_id,
            Decision.superseded_by.is_(None),
        )
        .order_by(Decision.decided_at.desc())
        .limit(1)
    )
    if previous is None:
        return {"status": "NO_PRIOR_DECISION", "application_id": str(application_id)}
    previous_id = previous.id
    job_id = job.id
    existing = await find_existing_decision(
        session, tenant_id=context.tenant_id, idempotency_key=key
    )
    if existing is not None:
        return {"status": "ALREADY_REDECIDED", "decision_id": str(existing.id)}

    as_of = datetime.fromisoformat(str(job.payload["as_of"]))
    prior_snapshot = await session.get(FeatureSnapshot, previous.feature_snapshot_id)
    if prior_snapshot is not None and as_of <= prior_snapshot.as_of:
        as_of = prior_snapshot.as_of + timedelta(microseconds=1)
    try:
        result = await decide(
            session,
            context,
            application_id=application_id,
            as_of=as_of,
            idempotency_key=key,
            supersedes_decision_id=previous.id,
            generate_recourse=False,
        )
    except Exception as exc:
        await session.rollback()
        session.add(
            RedecisionAlert(
                tenant_id=context.tenant_id,
                application_id=application_id,
                previous_decision_id=previous_id,
                job_id=job_id,
                code="REDECISION_FAILED",
                message=str(exc)[:1000],
            )
        )
        await session.commit()
        return {
            "status": "FAILED_SAFE",
            "previous_decision_id": str(previous_id),
            "alert": "REDECISION_FAILED",
        }

    protected = (
        await session.scalar(
            select(HumanReview.id).where(
                HumanReview.tenant_id == context.tenant_id,
                HumanReview.decision_id == previous.id,
                HumanReview.status == ReviewStatus.RESOLVED,
            )
        )
    ) is not None
    change = await detect_change(
        session, context, previous=previous, new=result.decision, human_action_protected=protected
    )
    application = await session.get(Application, application_id)
    if application is not None and not protected:
        application.status = (
            ApplicationStatus.REFERRED
            if result.decision.routing == "HUMAN"
            else ApplicationStatus.DECIDED
        )
        await session.commit()
    return {
        "status": "CHANGED" if change.direction != "UNCHANGED" else "UNCHANGED",
        "previous_decision_id": str(previous.id),
        "decision_id": str(result.decision.id),
        "change_id": str(change.id),
        "direction": change.direction,
        "human_action_protected": protected,
    }
