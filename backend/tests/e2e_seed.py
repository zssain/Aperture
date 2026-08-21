"""Idempotent local seed for the Playwright ingest-to-decision release test."""

import asyncio
from datetime import UTC, datetime

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import PolicyStatus, UserRole
from app.models.policy import PolicyVersion
from app.models.tenant import Tenant
from app.models.user import User
from app.services.policy.defaults import seed_policy_v1
from sqlalchemy import select

EMAIL = "e2e-analyst@aperture.test"
PASSWORD = "E2e-Strong-Passw0rd!"


async def seed() -> None:
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "aperture-e2e"))
        if tenant is None:
            tenant = Tenant(name="Aperture E2E", slug="aperture-e2e", config={})
            session.add(tenant)
            await session.flush()

        user = await session.scalar(
            select(User).where(User.tenant_id == tenant.id, User.email == EMAIL)
        )
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=EMAIL,
                full_name="E2E Analyst",
                role=UserRole.CREDIT_ANALYST,
                is_active=True,
                hashed_password=hash_password(PASSWORD),
            )
            session.add(user)
            await session.flush()

        live = await session.scalar(
            select(PolicyVersion).where(
                PolicyVersion.tenant_id == tenant.id,
                PolicyVersion.status == PolicyStatus.LIVE,
            )
        )
        if live is None:
            session.add(
                PolicyVersion(
                    tenant_id=tenant.id,
                    version=1,
                    status=PolicyStatus.LIVE,
                    rules=seed_policy_v1().model_dump(mode="json"),
                    published_at=datetime.now(UTC),
                    created_by=user.id,
                )
            )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
