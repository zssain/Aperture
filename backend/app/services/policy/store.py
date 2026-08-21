"""Persistence for policy versions: publish (validated) and fetch the live policy.

The engine and validator are pure; this is the only policy module that touches the database.
Publishing runs the full validator first - a policy that fails validation cannot be saved as
LIVE (invariant 1: the live policy is always a decidable, diffable artifact).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PolicyStatus
from app.models.policy import PolicyVersion
from app.services.policy.schema import PolicyRules
from app.services.policy.validator import validate


class NoLivePolicyError(Exception):
    """No LIVE policy exists for this tenant - the system cannot decide."""


class PolicyValidationError(Exception):
    """A policy failed validation and must not be published."""

    def __init__(self, errors: tuple[str, ...]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class LivePolicy:
    row: PolicyVersion
    rules: PolicyRules


async def get_live_policy(session: AsyncSession, tenant_id: uuid.UUID) -> LivePolicy:
    row = await session.scalar(
        select(PolicyVersion).where(
            PolicyVersion.tenant_id == tenant_id,
            PolicyVersion.status == PolicyStatus.LIVE,
        )
    )
    if row is None:
        raise NoLivePolicyError(f"no live policy for tenant {tenant_id}")
    return LivePolicy(row=row, rules=PolicyRules(**row.rules))


async def publish_policy(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    version: int,
    rules: PolicyRules,
    created_by: uuid.UUID | None = None,
) -> PolicyVersion:
    """Validate, archive any current live policy, and publish this one as LIVE."""
    result = validate(rules)
    if not result.ok:
        raise PolicyValidationError(result.errors)

    current = await session.scalar(
        select(PolicyVersion).where(
            PolicyVersion.tenant_id == tenant_id,
            PolicyVersion.status == PolicyStatus.LIVE,
        )
    )
    if current is not None:
        current.status = PolicyStatus.ARCHIVED

    row = PolicyVersion(
        tenant_id=tenant_id,
        version=version,
        status=PolicyStatus.LIVE,
        rules=rules.model_dump(mode="json"),
        published_at=datetime.now(UTC),
        created_by=created_by,
    )
    session.add(row)
    await session.commit()
    return row
