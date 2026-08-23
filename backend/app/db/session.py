"""Async database engine and session factory.

This provides the Alembic-ready Postgres connection the rest of the system builds on.
No models are defined yet — only the engine, a session factory for future use, and a
readiness probe used by ``/ready``.
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# asyncpg connect args. statement_cache_size=0 is required behind a transaction-mode
# pooler (Supabase 6543) and harmless elsewhere; left unset for a direct/local URL.
_connect_args: dict[str, Any] = {}
if settings.db_statement_cache_size is not None:
    _connect_args["statement_cache_size"] = settings.db_statement_cache_size

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    connect_args=_connect_args,
    future=True,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session (FastAPI dependency for later stages)."""
    async with SessionLocal() as session:
        yield session


async def check_db_ready() -> None:
    """Execute ``SELECT 1`` to confirm the database is reachable.

    Raises the underlying driver exception if the connection cannot be established;
    callers translate that into a 503 readiness response.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            installed = await conn.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")
            )
        except Exception as exc:
            raise RuntimeError("pgvector extension check failed") from exc
        if not installed:
            raise RuntimeError("pgvector extension is unavailable")
        catalog_table = await conn.scalar(text("SELECT to_regclass('merchant_catalog_versions')"))
        if catalog_table:
            dimension = await conn.scalar(
                text(
                    "SELECT embedding_dimension FROM merchant_catalog_versions "
                    "WHERE status = 'live' LIMIT 1"
                )
            )
            if dimension is not None and int(dimension) != settings.embedding_dimension:
                raise RuntimeError(
                    "embedding dimension mismatch: "
                    f"catalogue={dimension}, configured={settings.embedding_dimension}"
                )
