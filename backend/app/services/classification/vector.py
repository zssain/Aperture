"""Tier-2 vector lookup. Similarity is classification metadata, never a risk input."""

import asyncio
import hashlib
import re
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.providers.base import (
    EmbeddingDimensionError,
    EmbeddingProvider,
    ProviderNotConfigured,
    ProviderUnavailable,
)
from app.core.providers.registry import configured_registry
from app.models.enums import MerchantCatalogStatus
from app.models.merchant_catalog import EmbeddingCache, MerchantCatalogEntry, MerchantCatalogVersion
from app.services.classification.rules import TxnCategory
from app.services.classification.service import (
    ClassificationResult,
    TxnEvent,
    VectorCandidate,
    classify,
)

NORMALIZER_VERSION = "narration-v1"
CLASSIFICATION_METRICS: Counter[str] = Counter()
_PREFIX = re.compile(r"^(?:upi|imps|neft|rtgs|ach|pos|atm)[/-]+", re.IGNORECASE)
_NOISE = re.compile(
    r"(?:\b(?:dr|cr|yesb|hdfc|icic|sbin|axis)\b|\b\d{4,}\b|\b\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b)",
    re.IGNORECASE,
)
_SPACE = re.compile(r"[^\w\u0900-\u097f\u0b80-\u0bff]+", re.UNICODE)


def normalize_narration(text: str) -> str:
    """Remove channel/reference noise while preserving Unicode merchant text."""
    cleaned = _PREFIX.sub("", text.strip())
    cleaned = _NOISE.sub(" ", cleaned)
    return _SPACE.sub(" ", cleaned).strip().casefold()


def normalized_text_hash(text: str) -> str:
    payload = f"{NORMALIZER_VERSION}\0{text}".encode()
    return hashlib.sha256(payload).hexdigest()


async def _cached_embedding(
    session: AsyncSession, provider: EmbeddingProvider, normalized: str
) -> list[float]:
    digest = normalized_text_hash(normalized)
    cached = await session.scalar(
        select(EmbeddingCache).where(
            EmbeddingCache.embedding_model_id == provider.model_id,
            EmbeddingCache.normalized_text_hash == digest,
        )
    )
    if cached is not None:
        return [float(value) for value in cached.embedding]
    vector = (await asyncio.to_thread(provider.embed, [normalized]))[0]
    if len(vector) != provider.dimension or provider.dimension != settings.embedding_dimension:
        raise EmbeddingDimensionError(
            "embedding dimension mismatch: "
            f"provider={len(vector)} configured={settings.embedding_dimension}"
        )
    rounded = [round(float(value), 8) for value in vector]
    session.add(
        EmbeddingCache(
            embedding_model_id=provider.model_id,
            normalized_text_hash=digest,
            embedding=rounded,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return rounded


async def vector_candidates(
    session: AsyncSession,
    events: list[TxnEvent],
    provider: EmbeddingProvider,
    *,
    replay: bool = False,
) -> dict[uuid.UUID, VectorCandidate]:
    live = await session.scalar(
        select(MerchantCatalogVersion).where(
            MerchantCatalogVersion.status == MerchantCatalogStatus.LIVE
        )
    )
    if live is None:
        return {}
    if live.embedding_dimension != provider.dimension:
        raise EmbeddingDimensionError(
            f"catalogue dimension {live.embedding_dimension} != "
            f"provider dimension {provider.dimension}"
        )
    result: dict[uuid.UUID, VectorCandidate] = {}
    for event in events:
        normalized = normalize_narration(event.description or "")
        if not normalized:
            continue
        if replay:
            cached = await session.scalar(
                select(EmbeddingCache).where(
                    EmbeddingCache.embedding_model_id == provider.model_id,
                    EmbeddingCache.normalized_text_hash == normalized_text_hash(normalized),
                )
            )
            if cached is None:
                continue
            embedding = [float(value) for value in cached.embedding]
        else:
            embedding = await _cached_embedding(session, provider, normalized)
        distance = MerchantCatalogEntry.embedding.cosine_distance(embedding)
        rows = list(
            await session.scalars(
                select(MerchantCatalogEntry)
                .where(MerchantCatalogEntry.catalog_version_id == live.id)
                .order_by(distance)
                .limit(5)
            )
        )
        if not rows:
            continue
        # Fetch distances in one typed projection so the recorded score is exact.
        scored = list(
            (
                await session.execute(
                    select(MerchantCatalogEntry, distance.label("distance"))
                    .where(MerchantCatalogEntry.catalog_version_id == live.id)
                    .order_by(distance)
                    .limit(5)
                )
            ).all()
        )
        top, top_distance = scored[0]
        categories = tuple(TxnCategory(row.category) for row, _ in scored[:3])
        result[event.event_id] = VectorCandidate(
            category=TxnCategory(top.category),
            similarity=round(1.0 - float(top_distance), 8),
            matched_entry_id=top.id,
            catalog_version_id=live.id,
            top_three_categories=categories,
            normalized_narration=normalized,
        )
    return result


async def classify_for_ingest(
    session: AsyncSession, events: list[TxnEvent]
) -> ClassificationResult:
    """Classify before immutable insertion; provider failure is an honest abstention."""
    tier_one = classify(events)
    misses = [
        row.event for row in tier_one.events if row.classification_method.value == "UNCLASSIFIED"
    ]
    if not misses or settings.embedding_provider == "noop":
        return tier_one
    try:
        provider = configured_registry().embedding(settings.embedding_provider)
        candidates = await vector_candidates(session, misses, provider)
        return classify(
            events,
            vector_candidates=candidates,
            similarity_floor=settings.vector_similarity_floor,
        )
    except EmbeddingDimensionError:
        raise
    except (ProviderNotConfigured, ProviderUnavailable, OSError, TimeoutError):
        CLASSIFICATION_METRICS["embedding_provider_unavailable"] += 1
        return tier_one
