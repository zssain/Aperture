"""Authentication, RBAC and tenant-isolation tests."""

import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.api.deps import require_authority, require_role, require_writer
from app.core.context import RequestContext
from app.core.security import hash_token, login_rate_limiter
from app.models.enums import UserRole
from app.models.session import UserSession
from app.services.audit.ledger import append
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import DEFAULT_PASSWORD, create_user

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"
VERIFY = "/api/v1/audit/verify"
NOTES = "/api/v1/audit/notes"


async def _login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post(LOGIN, json={"email": email, "password": password})


# --------------------------------------------------------------------------- #
# Login / logout / me and cookie attributes
# --------------------------------------------------------------------------- #
async def test_login_sets_secure_cookie_then_me_then_logout_revokes(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)

    resp = await _login(client, user.email, DEFAULT_PASSWORD)
    assert resp.status_code == 200
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=strict" in set_cookie

    token = client.cookies.get("aperture_session")
    assert token

    me = await client.get(ME)
    assert me.status_code == 200
    assert me.json()["email"] == user.email
    assert me.json()["role"] == UserRole.CREDIT_ANALYST.value
    assert me.json()["tenant_id"] == str(tenant.id)

    logout = await client.post(LOGOUT)
    assert logout.status_code == 200

    # Server-side revocation: re-presenting the same token is rejected.
    client.cookies.set("aperture_session", token)
    me_after = await client.get(ME)
    assert me_after.status_code == 401
    assert me_after.json()["detail"]["code"] == "SESSION_INVALID"


# --------------------------------------------------------------------------- #
# Unknown user vs wrong password: indistinguishable in body, status and timing
# --------------------------------------------------------------------------- #
async def test_unknown_user_and_wrong_password_are_indistinguishable(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user, _ = await create_user(db_session, role=UserRole.CREDIT_ANALYST)

    wrong = await _login(client, user.email, "not-the-password")
    login_rate_limiter.clear()
    unknown = await _login(client, f"ghost-{uuid.uuid4().hex}@example.com", "whatever")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    # Both paths run exactly one Argon2 verification, so timing is comparable.
    async def _timed(email: str, password: str) -> float:
        samples: list[float] = []
        for _ in range(5):
            login_rate_limiter.clear()
            start = time.perf_counter()
            await _login(client, email, password)
            samples.append(time.perf_counter() - start)
        return statistics.median(samples)

    wrong_ms = await _timed(user.email, "still-wrong")
    unknown_ms = await _timed(f"ghost-{uuid.uuid4().hex}@example.com", "whatever")
    ratio = wrong_ms / unknown_ms if unknown_ms else 1.0
    # Both paths run exactly one Argon2 verification. The ratio is ~1; the wide bound
    # tolerates CPU contention under the full suite while still catching a fast-return
    # (an unknown-user shortcut would be orders of magnitude faster, not ~1x).
    assert 0.2 <= ratio <= 5.0, f"timing distinguishable: {wrong_ms=} {unknown_ms=}"


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
async def test_login_rate_limited_after_five_attempts(
    client: httpx.AsyncClient,
) -> None:
    email = f"ratelimit-{uuid.uuid4().hex}@example.com"
    statuses = [(await _login(client, email, "x")).status_code for _ in range(5)]
    assert statuses == [401, 401, 401, 401, 401]

    sixth = await _login(client, email, "x")
    assert sixth.status_code == 429
    assert sixth.headers.get("Retry-After") is not None
    assert sixth.json()["detail"]["code"] == "RATE_LIMITED"


# --------------------------------------------------------------------------- #
# Role matrix: each role against a permitted and a forbidden route
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("role", "permitted", "forbidden", "permitted_status"),
    [
        (UserRole.AUDITOR, "verify", "notes", 200),
        (UserRole.CREDIT_ANALYST, "notes", "verify", 201),
        (UserRole.FRAUD_REVIEWER, "notes", "verify", 201),
        (UserRole.CREDIT_POLICY_OWNER, "notes", "verify", 201),
    ],
)
async def test_role_matrix(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    role: UserRole,
    permitted: str,
    forbidden: str,
    permitted_status: int,
) -> None:
    user, _ = await create_user(db_session, role=role)
    await _login(client, user.email, DEFAULT_PASSWORD)

    async def call(which: str) -> httpx.Response:
        if which == "verify":
            return await client.get(VERIFY)
        return await client.post(NOTES, json={"text": "a note"})

    assert (await call(permitted)).status_code == permitted_status
    assert (await call(forbidden)).status_code == 403


# --------------------------------------------------------------------------- #
# Cross-tenant access returns 404, not 403
# --------------------------------------------------------------------------- #
async def test_cross_tenant_entry_returns_404(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # Tenant B has a ledger entry created out of band.
    user_b, tenant_b = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    ctx_b = RequestContext(
        user_id=user_b.id,
        tenant_id=tenant_b.id,
        role=UserRole.CREDIT_ANALYST.value,
        email=user_b.email,
        session_id=uuid.uuid4(),
        approval_ceilings_paise={},
    )
    entry_b = await append(
        db_session,
        ctx_b,
        event_type="X",
        subject_type=None,
        subject_id=None,
        payload={"t": "b"},
    )
    await db_session.commit()

    # Tenant A logs in and creates its own entry.
    user_a, _ = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    await _login(client, user_a.email, DEFAULT_PASSWORD)
    own = await client.post(NOTES, json={"text": "mine"})
    own_id = own.json()["id"]

    assert (await client.get(f"/api/v1/audit/entries/{own_id}")).status_code == 200
    # Tenant B's entry exists, but is invisible to Tenant A → 404, not 403.
    cross = await client.get(f"/api/v1/audit/entries/{entry_b.id}")
    assert cross.status_code == 404
    assert cross.json()["detail"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# Session expiry mid-request → 401 with a machine-readable code
# --------------------------------------------------------------------------- #
async def test_expired_session_returns_401_expired_code(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    past = datetime.now(UTC) - timedelta(hours=1)
    session_row = UserSession(
        tenant_id=tenant.id,
        user_id=user.id,
        token_hash=hash_token("expired-token"),
        last_seen_at=past,
        expires_at=past,
    )
    db_session.add(session_row)
    await db_session.commit()

    client.cookies.set("aperture_session", "expired-token")
    resp = await client.get(ME)
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SESSION_EXPIRED"


# --------------------------------------------------------------------------- #
# Authorization guards (unit-level, no DB) — full role matrix incl. authority
# --------------------------------------------------------------------------- #
def _ctx(role: UserRole, ceilings: dict[str, int] | None = None) -> RequestContext:
    return RequestContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role=role.value,
        email="x@example.com",
        session_id=uuid.uuid4(),
        approval_ceilings_paise=ceilings or {},
    )


async def test_require_role_allows_and_denies() -> None:
    guard = require_role(UserRole.CREDIT_POLICY_OWNER)
    ctx_ok = _ctx(UserRole.CREDIT_POLICY_OWNER)
    assert await guard(ctx_ok) is ctx_ok
    with pytest.raises(HTTPException) as excinfo:
        await guard(_ctx(UserRole.CREDIT_ANALYST))
    assert excinfo.value.status_code == 403


async def test_require_writer_denies_auditor() -> None:
    allowed = await require_writer(context=_ctx(UserRole.CREDIT_ANALYST))
    assert allowed.is_auditor is False
    with pytest.raises(HTTPException) as excinfo:
        await require_writer(context=_ctx(UserRole.AUDITOR))
    assert excinfo.value.status_code == 403


def test_require_authority_respects_ceiling() -> None:
    ctx = _ctx(UserRole.CREDIT_ANALYST, {"CREDIT_ANALYST": 5_000_00})
    require_authority(ctx, 4_000_00)  # under ceiling: allowed
    with pytest.raises(HTTPException) as excinfo:
        require_authority(ctx, 6_000_00)  # over ceiling: denied
    assert excinfo.value.status_code == 403

    with pytest.raises(HTTPException):
        # No ceiling configured for the role → denied.
        require_authority(_ctx(UserRole.AUDITOR), 1)
