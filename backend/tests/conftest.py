"""Test configuration and shared database fixtures.

Environment is set *before* the application (settings singleton + async engine) is
imported. When ``TEST_DATABASE_URL`` is present it also becomes ``DATABASE_URL`` so the
application engine used by the TestClient talks to the throwaway test database.
"""

import argparse
import os
import pathlib
import sys

# The `ml/` package (scorecard + pipelines) lives at the repo root; make it importable.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if _TEST_DATABASE_URL:
    # Force the app engine onto the throwaway DB for the duration of the test run.
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
else:
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://aperture:aperture@localhost:5432/aperture",
    )
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")

# Imports below intentionally follow the environment setup above.
from collections.abc import AsyncIterator, Iterator  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.security import login_rate_limiter  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import app  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

requires_db = pytest.mark.skipif(
    _TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL not set — integration tests need a throwaway PostgreSQL",
)


def _alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.cmd_opts = argparse.Namespace(x=[f"db_url={url}"])
    return cfg


@pytest.fixture(scope="module")
def migrated_db() -> Iterator[str]:
    """Migrate the throwaway database forward for the module; reverse on teardown."""
    if _TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL not set")
    cfg = _alembic_config(_TEST_DATABASE_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield _TEST_DATABASE_URL
    command.downgrade(cfg, "base")


@pytest_asyncio.fixture
async def db_engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_db, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine: AsyncEngine, migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    # Route DB access through the per-test engine (created in this test's event loop)
    # so asyncpg connections never cross event loops. https base_url → Secure cookies
    # are stored and resent by the client.
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="https://testserver"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture(autouse=True)
def _reset_login_rate_limiter() -> None:
    login_rate_limiter.clear()
