"""Tenant-scoped applicant data export and legally safe deletion requests."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.context import RequestContext
from app.db.session import get_session
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.consent import Consent
from app.models.decision import Decision
from app.models.enums import ApplicationStatus, DecisionAction, UserRole
from app.models.ledger import LedgerEvent
from app.models.notice import Notice
from app.models.outcome import Outcome
from app.models.source import SourceConnection, SourceSnapshot
from app.services.audit.ledger import append
from app.services.consent.revocation import propagate_revocation

router = APIRouter(prefix="/applicants", tags=["privacy"])
privacy_role = require_role(UserRole.CREDIT_POLICY_OWNER)


async def _applicant(
    session: AsyncSession, context: RequestContext, applicant_id: uuid.UUID
) -> Applicant:
    applicant = await session.get(Applicant, applicant_id)
    if applicant is None or applicant.tenant_id != context.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    return applicant


@router.post("/{applicant_id}/export")
async def export_data(
    applicant_id: uuid.UUID,
    context: RequestContext = Depends(privacy_role),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    applicant = await _applicant(session, context, applicant_id)
    applications = list(
        await session.scalars(
            select(Application).where(
                Application.tenant_id == context.tenant_id, Application.applicant_id == applicant_id
            )
        )
    )
    application_ids = [row.id for row in applications]
    decisions = list(
        await session.scalars(
            select(Decision).where(
                Decision.tenant_id == context.tenant_id, Decision.applicant_id == applicant_id
            )
        )
    )
    consents = list(
        await session.scalars(
            select(Consent).where(
                Consent.tenant_id == context.tenant_id, Consent.applicant_id == applicant_id
            )
        )
    )
    sources = list(
        await session.scalars(
            select(SourceConnection).where(
                SourceConnection.tenant_id == context.tenant_id,
                SourceConnection.applicant_id == applicant_id,
            )
        )
    )
    outcomes = list(
        await session.scalars(
            select(Outcome).where(
                Outcome.tenant_id == context.tenant_id, Outcome.applicant_id == applicant_id
            )
        )
    )
    notices = list(
        await session.scalars(
            select(Notice).where(
                Notice.tenant_id == context.tenant_id, Notice.applicant_id == applicant_id
            )
        )
    )
    classifications = list(
        await session.scalars(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == context.tenant_id,
                LedgerEvent.applicant_id == applicant_id,
            )
        )
    )

    def dump(row: object) -> dict[str, object]:
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}  # type: ignore[attr-defined]

    await append(
        session,
        context,
        "DATA_SUBJECT_EXPORT",
        "applicant",
        applicant.id,
        {"application_count": len(application_ids)},
    )
    await session.commit()
    return {
        "applicant": dump(applicant),
        "applications": [dump(row) for row in applications],
        "decisions": [dump(row) for row in decisions],
        "consents": [dump(row) for row in consents],
        "source_connections": [dump(row) for row in sources],
        "outcomes": [dump(row) for row in outcomes],
        "communications": [dump(row) for row in notices],
        "transaction_classifications": [
            {
                "event_id": row.id,
                "classification_method": row.classification_method,
                "category": row.category,
                "classifier_version": row.classifier_version,
                "catalog_version_id": row.catalog_version_id,
                "match_similarity": row.match_similarity,
                "matched_entry_id": row.matched_entry_id,
            }
            for row in classifications
        ],
    }


@router.post("/{applicant_id}/delete")
async def delete_data(
    applicant_id: uuid.UUID,
    context: RequestContext = Depends(privacy_role),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    applicant = await _applicant(session, context, applicant_id)
    active_approved = await session.scalar(
        select(Decision.id)
        .join(Application, Decision.application_id == Application.id)
        .where(
            Decision.tenant_id == context.tenant_id,
            Decision.applicant_id == applicant_id,
            Decision.action.in_([DecisionAction.APPROVE, DecisionAction.APPROVE_STARTER]),
            Application.status != ApplicationStatus.CLOSED,
        )
        .limit(1)
    )
    if active_approved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "LEGAL_HOLD",
                "message": "Deletion is unavailable while an active loan is under legal hold.",
            },
        )
    await propagate_revocation(session, tenant_id=context.tenant_id, applicant_id=applicant_id)
    applicant.display_name = None
    applicant.phone = None
    applicant.external_ref = f"deleted-{applicant.id}"
    snapshots = list(
        await session.scalars(
            select(SourceSnapshot).where(
                SourceSnapshot.tenant_id == context.tenant_id,
                SourceSnapshot.applicant_id == applicant_id,
            )
        )
    )
    for snapshot in snapshots:
        snapshot.raw_ref = None
        snapshot.payload = None
    await append(
        session,
        context,
        "DATA_SUBJECT_DELETED",
        "applicant",
        applicant.id,
        {"identity_pseudonymised": True, "decision_records_preserved": True},
    )
    await session.commit()
    return {
        "status": "PSEUDONYMISED",
        "decision_records_preserved": True,
        "raw_purges_scheduled": len(snapshots),
    }
