"""Request dependencies: authentication context and authorization guards.

``get_context`` resolves the session cookie into a :class:`RequestContext`, slides the
idle expiry forward, and refreshes the cookie. ``require_role`` / ``require_writer``
enforce role access (403). ``require_authority`` enforces per-role approval ceilings.
Every 401 carries a machine-readable ``code`` the frontend can act on.
"""

import hmac
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import RequestContext
from app.core.security import hash_token
from app.db.session import get_session
from app.models.enums import UserRole
from app.models.session import UserSession
from app.models.tenant import Tenant
from app.models.user import User


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": code, "message": message})


def _forbidden(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": code, "message": message})


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_idle_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


async def get_context(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> RequestContext:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _unauthorized("NOT_AUTHENTICATED", "Authentication required")

    user_session = await session.scalar(
        select(UserSession).where(UserSession.token_hash == hash_token(token))
    )
    if user_session is None or user_session.revoked_at is not None:
        raise _unauthorized("SESSION_INVALID", "Session is invalid")

    now = datetime.now(UTC)
    if user_session.expires_at <= now:
        raise _unauthorized("SESSION_EXPIRED", "Session has expired")

    user = await session.get(User, user_session.user_id)
    if user is None or not user.is_active:
        raise _unauthorized("USER_INACTIVE", "User is not active")

    tenant = await session.get(Tenant, user_session.tenant_id)
    if tenant is None:
        raise _unauthorized("SESSION_INVALID", "Session is invalid")

    # Slide the idle expiry forward and refresh the cookie.
    user_session.last_seen_at = now
    user_session.expires_at = now + timedelta(seconds=settings.session_idle_ttl_seconds)
    await session.commit()
    set_session_cookie(response, token)

    ceilings_raw = tenant.config.get("approval_ceilings_paise", {})
    ceilings = {str(key): int(val) for key, val in ceilings_raw.items()}
    return RequestContext(
        user_id=user.id,
        tenant_id=tenant.id,
        role=user.role.value,
        email=user.email,
        session_id=user_session.id,
        approval_ceilings_paise=ceilings,
    )


def require_role(
    *roles: UserRole,
) -> Callable[[RequestContext], Awaitable[RequestContext]]:
    """Dependency factory: allow only the given roles, else 403."""
    allowed = {role.value for role in roles}

    async def dependency(
        context: RequestContext = Depends(get_context),
    ) -> RequestContext:
        if context.role not in allowed:
            raise _forbidden("FORBIDDEN_ROLE", "Insufficient role for this action")
        return context

    return dependency


async def require_writer(
    context: RequestContext = Depends(get_context),
) -> RequestContext:
    """Deny the read-only auditor on mutating routes (403)."""
    if context.is_auditor:
        raise _forbidden("READ_ONLY_ROLE", "Auditor is read-only")
    return context


async def require_event_service(
    authorization: str | None = Header(default=None),
    x_tenant_id: uuid.UUID | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> RequestContext:
    """Authenticate the machine-to-machine event endpoint with a tenant token.

    Only a SHA-256 token digest is stored in tenant configuration. The configured
    user supplies a real audit actor for the decision triggered by the event.
    """
    if x_tenant_id is None or not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized("SERVICE_TOKEN_REQUIRED", "Service token authentication required")
    tenant = await session.get(Tenant, x_tenant_id)
    service = tenant.config.get("event_service", {}) if tenant is not None else {}
    expected = service.get("token_hash") if isinstance(service, dict) else None
    raw_user_id = service.get("user_id") if isinstance(service, dict) else None
    presented = authorization.removeprefix("Bearer ").strip()
    if not isinstance(expected, str) or not hmac.compare_digest(hash_token(presented), expected):
        raise _unauthorized("SERVICE_TOKEN_INVALID", "Service token is invalid")
    assert tenant is not None
    try:
        user_id = uuid.UUID(str(raw_user_id))
    except (TypeError, ValueError) as exc:
        raise _unauthorized("SERVICE_TOKEN_INVALID", "Service token is invalid") from exc
    user = await session.get(User, user_id)
    if user is None or user.tenant_id != tenant.id or not user.is_active:
        raise _unauthorized("SERVICE_TOKEN_INVALID", "Service token is invalid")
    ceilings_raw = tenant.config.get("approval_ceilings_paise", {})
    return RequestContext(
        user_id=user.id,
        tenant_id=tenant.id,
        role=user.role.value,
        email=user.email,
        session_id=uuid.UUID(int=0),
        approval_ceilings_paise={str(key): int(value) for key, value in ceilings_raw.items()},
    )


def require_authority(context: RequestContext, amount_paise: int) -> None:
    """Raise 403 if ``amount_paise`` exceeds the role's approval ceiling."""
    ceiling = context.ceiling_for_role()
    if ceiling is None or amount_paise > ceiling:
        raise _forbidden("INSUFFICIENT_AUTHORITY", "Amount exceeds your approval authority")
