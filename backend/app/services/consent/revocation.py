"""Consent revocation propagation across cases and retained raw uploads."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.source import SourceConnection, SourceSnapshot
from app.services.retention.purge import schedule_raw_purge


async def propagate_revocation(
    session: AsyncSession, *, tenant_id: uuid.UUID, applicant_id: uuid.UUID
) -> int:
    applications = list(
        await session.scalars(
            select(Application).where(
                Application.tenant_id == tenant_id,
                Application.applicant_id == applicant_id,
                Application.status.not_in([ApplicationStatus.CLOSED]),
            )
        )
    )
    for application in applications:
        application.status = ApplicationStatus.CLOSED
    snapshots = list(
        await session.scalars(
            select(SourceSnapshot)
            .join(SourceConnection, SourceSnapshot.source_connection_id == SourceConnection.id)
            .where(
                SourceSnapshot.tenant_id == tenant_id, SourceSnapshot.applicant_id == applicant_id
            )
        )
    )
    for snapshot in snapshots:
        await schedule_raw_purge(
            session,
            tenant_id=tenant_id,
            applicant_id=applicant_id,
            storage_path=snapshot.raw_ref,
            subject_id=snapshot.id,
            expires_at=datetime.now(UTC),
        )
    await session.flush()
    return len(snapshots)
