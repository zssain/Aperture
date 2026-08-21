import uuid
from datetime import UTC, datetime

import pytest
from app.models.enums import MerchantCatalogStatus
from app.models.merchant_catalog import MerchantCatalogEntry, MerchantCatalogVersion
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.conftest import requires_db

pytestmark = requires_db


def version(name: str, status: MerchantCatalogStatus) -> MerchantCatalogVersion:
    return MerchantCatalogVersion(
        version=name,
        status=status,
        embedding_model_id="test-384",
        embedding_dimension=384,
        entry_count=1,
        content_hash=uuid.uuid4().hex.ljust(64, "0"),
    )


async def test_extension_and_hnsw_index_exist(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        assert await connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")
        )
        definition = await connection.scalar(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname='ix_catalog_entries_embedding_hnsw'"
            )
        )
        assert definition is not None
        assert "hnsw" in str(definition).casefold()
        assert "vector_cosine_ops" in str(definition)


async def test_only_one_live_catalogue(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            version("unique-live-a", MerchantCatalogStatus.LIVE),
            version("unique-live-b", MerchantCatalogStatus.LIVE),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_live_catalogue_entry_is_immutable(db_session: AsyncSession) -> None:
    catalog = version("immutable-live", MerchantCatalogStatus.LIVE)
    db_session.add(catalog)
    await db_session.flush()
    entry = MerchantCatalogEntry(
        catalog_version_id=catalog.id,
        canonical_name="BESCOM",
        category="UTILITY",
        aliases=["Bangalore electricity"],
        embedding=[0.0] * 384,
        source_note="synthetic test reference",
    )
    db_session.add(entry)
    await db_session.commit()
    entry.canonical_name = "mutated"
    with pytest.raises(DBAPIError):
        await db_session.commit()
    await db_session.rollback()


async def test_vector_knn_query_uses_hnsw(db_session: AsyncSession) -> None:
    catalog = version("explain-draft", MerchantCatalogStatus.DRAFT)
    db_session.add(catalog)
    await db_session.flush()
    for index in range(20):
        db_session.add(
            MerchantCatalogEntry(
                catalog_version_id=catalog.id,
                canonical_name=f"merchant-{index}",
                category="MERCHANT",
                aliases=[],
                embedding=[index / 100.0] * 384,
                source_note="synthetic test reference",
                created_at=datetime.now(UTC),
            )
        )
    await db_session.commit()
    await db_session.execute(text("SET enable_seqscan = off"))
    vector = "[" + ",".join(["0.1"] * 384) + "]"
    plan = "\n".join(
        str(row[0])
        for row in (
            await db_session.execute(
                text(
                    "EXPLAIN SELECT id FROM merchant_catalog_entries "
                    "ORDER BY embedding <=> CAST(:vector AS vector) LIMIT 5"
                ),
                {"vector": vector},
            )
        ).all()
    )
    assert "ix_catalog_entries_embedding_hnsw" in plan
