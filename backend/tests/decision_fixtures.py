"""Shared builders for the orchestrator/replay/job tests: a fully decidable application.

Inserts ~7 months of steady salaried evidence (with a consistent running balance so the
balance-arithmetic detector stays clean) plus one AA-verified bank source, and publishes the
seed policy LIVE. The result is an application ``decide`` can turn into a real decision.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.context import RequestContext
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.enums import (
    EventDirection,
    EvidenceEventType,
    SourceConnectionStatus,
    SourceTier,
    SourceType,
    UserRole,
)
from app.models.ledger import LedgerEvent
from app.models.source import SourceConnection, SourceSnapshot
from app.services.policy.defaults import seed_policy_v1
from app.services.policy.schema import PolicyRules
from app.services.policy.store import publish_policy
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_user

AS_OF = datetime(2026, 8, 1, tzinfo=UTC)

_SALARY_PAISE = 5_000_000  # Rs 50,000, a multiple of Rs 5,000 but paid on a regular date
_RENT_PAISE = 1_500_000
_EMI_PAISE = 500_000


@dataclass(frozen=True)
class Decidable:
    context: RequestContext
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    applicant: Applicant
    application: Application


def _context(user_id: uuid.UUID, tenant_id: uuid.UUID, email: str) -> RequestContext:
    return RequestContext(
        user_id=user_id,
        tenant_id=tenant_id,
        role="CREDIT_ANALYST",
        email=email,
        session_id=uuid.uuid4(),
        approval_ceilings_paise={},
    )


async def build_decidable(
    session: AsyncSession,
    *,
    requested_amount_paise: int = 10_000_000,
    tenor_months: int = 12,
    months: int = 7,
    with_source: bool = True,
) -> Decidable:
    user, tenant = await create_user(session, role=UserRole.CREDIT_ANALYST)
    context = _context(user.id, tenant.id, user.email)

    applicant = Applicant(tenant_id=tenant.id, external_ref=f"app-{uuid.uuid4().hex[:8]}")
    session.add(applicant)
    await session.flush()

    application = Application(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        requested_amount_paise=requested_amount_paise,
        requested_tenor_months=tenor_months,
    )
    session.add(application)
    await session.flush()

    connection: SourceConnection | None = None
    if with_source:
        connection = SourceConnection(
            tenant_id=tenant.id,
            applicant_id=applicant.id,
            source_type=SourceType.BANK,
            tier=SourceTier.AA_VERIFIED,
            status=SourceConnectionStatus.CONNECTED,
        )
        session.add(connection)
        await session.flush()
        snapshot = SourceSnapshot(
            tenant_id=tenant.id,
            source_connection_id=connection.id,
            applicant_id=applicant.id,
            tier=SourceTier.AA_VERIFIED,
            fetched_at=AS_OF,
            period_start=AS_OF - timedelta(days=months * 30),
            period_end=AS_OF - timedelta(days=2),
            content_hash=uuid.uuid4().hex,
            record_count=months * 3,
            ingested_count=months * 3,
        )
        session.add(snapshot)
        await session.flush()

    # Build the monthly events in time order and thread a consistent running balance.
    entries: list[tuple[datetime, EventDirection, int, str]] = []
    for m in range(months):
        month_start = AS_OF - timedelta(days=(months - m) * 30)
        entries.append((month_start, EventDirection.CREDIT, _SALARY_PAISE, "salary credit"))
        entries.append((month_start + timedelta(days=2), EventDirection.DEBIT, _RENT_PAISE, "rent"))
        entries.append(
            (month_start + timedelta(days=3), EventDirection.DEBIT, _EMI_PAISE, "emi loan")
        )
    entries.sort(key=lambda e: e[0])

    balance = 2_000_000
    connection_id = connection.id if connection else None
    for occurred_at, direction, amount, description in entries:
        signed = amount if direction == EventDirection.CREDIT else -amount
        balance += signed
        session.add(
            LedgerEvent(
                tenant_id=tenant.id,
                applicant_id=applicant.id,
                source_connection_id=connection_id,
                event_type=EvidenceEventType.TRANSACTION,
                direction=direction,
                amount_paise=amount,
                balance_paise=balance,
                description=description,
                counterparty_hash="salary_cp"
                if direction == EventDirection.CREDIT
                else "expense_cp",
                occurred_at=occurred_at,
                received_at=occurred_at,
                idempotency_key=f"{applicant.id}:{occurred_at.isoformat()}:{description}",
            )
        )

    await session.commit()
    return Decidable(
        context=context,
        tenant_id=tenant.id,
        user_id=user.id,
        applicant=applicant,
        application=application,
    )


async def publish_seed(session: AsyncSession, decidable: Decidable, *, version: int = 1) -> None:
    await publish_policy(
        session,
        tenant_id=decidable.tenant_id,
        version=version,
        rules=seed_policy_v1(),
        created_by=decidable.user_id,
    )


async def publish_rules(
    session: AsyncSession, decidable: Decidable, rules: PolicyRules, *, version: int
) -> None:
    await publish_policy(
        session,
        tenant_id=decidable.tenant_id,
        version=version,
        rules=rules,
        created_by=decidable.user_id,
    )
