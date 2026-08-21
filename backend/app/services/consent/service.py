"""Consent lifecycle: grant an artefact + register a connection per scope entry, and
revoke (which blocks all future ingestion for the linked connections)."""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.models.applicant import Applicant
from app.models.consent import Consent
from app.models.enums import (
    ConsentStatus,
    SourceConnectionStatus,
    SourceTier,
    SourceType,
)
from app.models.source import SourceConnection
from app.services.audit.canonical import canonical_json
from app.services.audit.ledger import append

# The tier a freshly-registered connection can produce, by source type.
_TIER_BY_SOURCE: dict[SourceType, SourceTier] = {
    SourceType.BANK: SourceTier.AA_VERIFIED,
    SourceType.UPI: SourceTier.AA_VERIFIED,
    SourceType.BUREAU: SourceTier.BANK_VERIFIED,
    SourceType.UTILITY: SourceTier.DECLARED_DOCUMENT,
    SourceType.TELECOM: SourceTier.DECLARED_DOCUMENT,
}


class ConsentNotFoundError(Exception):
    pass


def _artefact_hash(
    *,
    applicant_id: uuid.UUID,
    purpose: str,
    scope: list[SourceType],
    granted_at: datetime,
    expires_at: datetime | None,
    version: int,
) -> str:
    artefact = {
        "applicant_id": str(applicant_id),
        "purpose": purpose,
        "scope": [s.value for s in scope],
        "granted_at": granted_at,
        "expires_at": expires_at,
        "version": version,
    }
    return hashlib.sha256(canonical_json(artefact).encode("utf-8")).hexdigest()


async def create_consent(
    session: AsyncSession,
    context: RequestContext,
    *,
    applicant_id: uuid.UUID,
    purpose: str,
    scope: list[SourceType],
    expires_at: datetime | None,
) -> tuple[Consent, list[SourceConnection]]:
    applicant = await session.get(Applicant, applicant_id)
    if applicant is None or applicant.tenant_id != context.tenant_id:
        raise ConsentNotFoundError("applicant not found")

    granted_at = datetime.now(UTC)
    version = (
        await session.scalar(
            select(func.count())
            .select_from(Consent)
            .where(
                Consent.tenant_id == context.tenant_id,
                Consent.applicant_id == applicant_id,
            )
        )
        or 0
    ) + 1

    artefact_hash = _artefact_hash(
        applicant_id=applicant_id,
        purpose=purpose,
        scope=scope,
        granted_at=granted_at,
        expires_at=expires_at,
        version=version,
    )

    consent = Consent(
        tenant_id=context.tenant_id,
        applicant_id=applicant_id,
        status=ConsentStatus.GRANTED,
        purpose=purpose,
        scope={"sources": [s.value for s in scope]},
        version=version,
        artefact_hash=artefact_hash,
        granted_at=granted_at,
        expires_at=expires_at,
    )
    session.add(consent)
    await session.flush()

    connections: list[SourceConnection] = []
    for source_type in scope:
        tier = _TIER_BY_SOURCE.get(source_type, SourceTier.DECLARED_DOCUMENT)
        connection = SourceConnection(
            tenant_id=context.tenant_id,
            applicant_id=applicant_id,
            consent_id=consent.id,
            source_type=source_type,
            tier=tier,
            provider="MockAA" if tier == SourceTier.AA_VERIFIED else None,
            status=SourceConnectionStatus.CONNECTED,
        )
        session.add(connection)
        connections.append(connection)
    await session.flush()

    await append(
        session,
        context,
        event_type="CONSENT_GRANTED",
        subject_type="consent",
        subject_id=consent.id,
        payload={
            "consent_id": str(consent.id),
            "applicant_id": str(applicant_id),
            "purpose": purpose,
            "scope": [s.value for s in scope],
            "version": version,
            "artefact_hash": artefact_hash,
        },
    )
    await session.commit()
    return consent, connections


async def revoke_consent(
    session: AsyncSession, context: RequestContext, *, consent_id: uuid.UUID
) -> Consent:
    consent = await session.get(Consent, consent_id)
    if consent is None or consent.tenant_id != context.tenant_id:
        raise ConsentNotFoundError("consent not found")

    if consent.revoked_at is None:
        consent.revoked_at = datetime.now(UTC)
        consent.status = ConsentStatus.REVOKED

        connections = (
            await session.scalars(
                select(SourceConnection).where(
                    SourceConnection.tenant_id == context.tenant_id,
                    SourceConnection.consent_id == consent_id,
                )
            )
        ).all()
        for connection in connections:
            connection.status = SourceConnectionStatus.REVOKED

        from app.services.consent.revocation import propagate_revocation

        purge_count = await propagate_revocation(
            session,
            tenant_id=context.tenant_id,
            applicant_id=consent.applicant_id,
        )

        await append(
            session,
            context,
            event_type="CONSENT_REVOKED",
            subject_type="consent",
            subject_id=consent.id,
            payload={"consent_id": str(consent.id), "raw_purges_scheduled": purge_count},
        )
        await session.commit()
    return consent
