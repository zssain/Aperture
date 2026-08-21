"""Test data factories (clearly-named fixture helpers, not production code)."""

import uuid
from typing import Any

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PASSWORD = "Sup3r-Secret-Passw0rd!"


async def create_tenant(session: AsyncSession, *, config: dict[str, Any] | None = None) -> Tenant:
    tenant = Tenant(
        name="Acme Credit",
        slug=f"acme-{uuid.uuid4().hex[:12]}",
        config=config or {},
    )
    session.add(tenant)
    await session.commit()
    return tenant


async def create_user(
    session: AsyncSession,
    *,
    role: UserRole,
    tenant: Tenant | None = None,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
) -> tuple[User, Tenant]:
    if tenant is None:
        tenant = await create_tenant(session)
    user = User(
        tenant_id=tenant.id,
        email=email or f"user-{uuid.uuid4().hex[:12]}@example.com",
        full_name="Test User",
        role=role,
        is_active=True,
        hashed_password=hash_password(password),
    )
    session.add(user)
    await session.commit()
    return user, tenant
