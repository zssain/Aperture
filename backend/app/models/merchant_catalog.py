"""System-global, versioned merchant catalogue used only to classify text.

The catalogue is intentionally not tenant-scoped: merchant strings are reference data,
not applicant data. Published entries are database-immutable and exempt from retention.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import MERCHANT_CATALOG_STATUS, MerchantCatalogStatus


class MerchantCatalogVersion(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "merchant_catalog_versions"
    __table_args__ = (
        Index(
            "uq_merchant_catalog_one_live",
            "status",
            unique=True,
            postgresql_where=text("status = 'live'"),
        ),
    )

    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[MerchantCatalogStatus] = mapped_column(
        MERCHANT_CATALOG_STATUS, nullable=False, default=MerchantCatalogStatus.DRAFT
    )
    embedding_model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class MerchantCatalogEntry(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "merchant_catalog_entries"
    __table_args__ = (
        UniqueConstraint(
            "catalog_version_id", "canonical_name", name="uq_catalog_entry_version_name"
        ),
        Index(
            "ix_catalog_entries_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    catalog_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("merchant_catalog_versions.id"), nullable=False, index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimension))
    source_note: Mapped[str] = mapped_column(Text, nullable=False)


class EmbeddingCache(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "embedding_cache"
    __table_args__ = (
        UniqueConstraint(
            "embedding_model_id", "normalized_text_hash", name="uq_embedding_cache_model_text"
        ),
    )

    embedding_model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimension))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
