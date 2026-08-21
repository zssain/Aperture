"""Authentication routes: login, logout, me.

Login validates with Argon2id, records a server-side session, and sets an HttpOnly +
Secure + SameSite=Strict cookie. Unknown user and wrong password are indistinguishable
in body, status and timing. Logout revokes the server-side session.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import clear_session_cookie, get_context, set_session_cookie
from app.core.config import settings
from app.core.context import RequestContext
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    RateLimitExceededError,
    generate_session_token,
    hash_token,
    login_rate_limiter,
    verify_password,
)
from app.db.session import get_session
from app.models.session import UserSession
from app.models.tenant import Tenant
from app.models.user import User
from app.services.rate_limit import PostgresRateLimitExceededError, hit_many

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: uuid.UUID
    tenant_name: str


def _invalid_credentials() -> HTTPException:
    # Identical for unknown user and wrong password.
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"},
    )


def _me(user: User, tenant: Tenant) -> MeResponse:
    return MeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    email = payload.email.strip().lower()
    try:
        login_rate_limiter.hit(email)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Too many login attempts"},
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not user.is_active or user.hashed_password is None:
        # Burn equivalent Argon2 time so unknown user ≈ wrong password.
        verify_password(DUMMY_PASSWORD_HASH, payload.password)
        raise _invalid_credentials()
    # Count valid-account attempts before checking the password. Otherwise a fleet of
    # workers would only share limits for successful logins while bad-password attacks
    # remained protected by the process-local compatibility limiter above.
    try:
        await hit_many(
            session,
            tenant_id=user.tenant_id,
            bucket="login",
            principals=(
                f"user:{email}",
                f"ip:{request.client.host if request.client else 'unknown'}",
            ),
        )
    except PostgresRateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Too many login attempts"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    if not verify_password(user.hashed_password, payload.password):
        raise _invalid_credentials()

    login_rate_limiter.reset(email)
    now = datetime.now(UTC)
    token = generate_session_token()
    user_session = UserSession(
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=hash_token(token),
        last_seen_at=now,
        expires_at=now + timedelta(seconds=settings.session_idle_ttl_seconds),
    )
    session.add(user_session)
    await session.commit()
    set_session_cookie(response, token)

    tenant = await session.get(Tenant, user.tenant_id)
    assert tenant is not None
    return _me(user, tenant)


@router.post("/logout")
async def logout(
    response: Response,
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    user_session = await session.get(UserSession, context.session_id)
    if user_session is not None and user_session.revoked_at is None:
        user_session.revoked_at = datetime.now(UTC)
        await session.commit()
    clear_session_cookie(response)
    return {"status": "logged_out"}


@router.get("/me")
async def me(
    context: RequestContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    user = await session.get(User, context.user_id)
    tenant = await session.get(Tenant, context.tenant_id)
    assert user is not None and tenant is not None
    return _me(user, tenant)
