"""Atomic draft-build and publish of an immutable catalogue version."""

import hashlib
import json

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.base import EmbeddingDimensionError, EmbeddingProvider
from app.models.enums import MerchantCatalogStatus
from app.models.merchant_catalog import MerchantCatalogEntry, MerchantCatalogVersion
from app.services.catalog.seed_entries import SEED_ENTRIES, SeedEntry


async def build_and_publish_catalog(
    session: AsyncSession,
    provider: EmbeddingProvider,
    *,
    version: str,
    entries: tuple[SeedEntry, ...] = SEED_ENTRIES,
) -> MerchantCatalogVersion:
    canonical = sorted(
        (
            {
                "name": row.canonical_name,
                "category": row.category,
                "aliases": row.aliases,
                "source": row.source_note,
            }
            for row in entries
        ),
        # Names are not globally unique (regional aliases can share a display name),
        # so hash ordering must include the complete row rather than rely on database
        # tie ordering for duplicate names.
        key=lambda row: json.dumps(row, sort_keys=True),
    )
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    vectors = provider.embed([row.canonical_name for row in entries])
    if len(vectors) != len(entries) or any(len(row) != provider.dimension for row in vectors):
        raise EmbeddingDimensionError("catalogue embedding output has the wrong shape")
    catalog = MerchantCatalogVersion(
        version=version,
        status=MerchantCatalogStatus.DRAFT,
        embedding_model_id=provider.model_id,
        embedding_dimension=provider.dimension,
        entry_count=len(entries),
        content_hash=digest,
    )
    session.add(catalog)
    await session.flush()
    session.add_all(
        MerchantCatalogEntry(
            catalog_version_id=catalog.id,
            canonical_name=row.canonical_name,
            category=row.category,
            aliases=list(row.aliases),
            embedding=[round(float(value), 8) for value in vector],
            source_note=row.source_note,
        )
        for row, vector in zip(entries, vectors, strict=True)
    )
    await session.execute(
        update(MerchantCatalogVersion)
        .where(MerchantCatalogVersion.status == MerchantCatalogStatus.LIVE)
        .values(status=MerchantCatalogStatus.RETIRED)
    )
    catalog.status = MerchantCatalogStatus.LIVE
    await session.commit()
    return catalog
