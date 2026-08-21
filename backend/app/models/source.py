"""Source connections and their fetched raw snapshots."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase, TimestampMixin
from app.models.enums import (
    SOURCE_CONNECTION_STATUS,
    SOURCE_TIER,
    SOURCE_TYPE,
    SourceConnectionStatus,
    SourceTier,
    SourceType,
)


class SourceConnection(TenantScopedBase, TimestampMixin):
    __tablename__ = "source_connections"
    # Query: list source connections for a given applicant.
    __table_args__ = (Index("ix_source_connections_applicant_id", "applicant_id"),)

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    consent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("consents.id"), nullable=True
    )
    source_type: Mapped[SourceType] = mapped_column(SOURCE_TYPE, nullable=False)
    # The evidential tier this connection can produce (AA_VERIFIED is strongest).
    tier: Mapped[SourceTier | None] = mapped_column(SOURCE_TIER, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[SourceConnectionStatus] = mapped_column(
        SOURCE_CONNECTION_STATUS,
        nullable=False,
        default=SourceConnectionStatus.PENDING,
    )
    external_account_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)


class SourceSnapshot(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "source_snapshots"
    __table_args__ = (
        # Query: list snapshots for a given source connection.
        Index("ix_source_snapshots_source_connection_id", "source_connection_id"),
        # File-level idempotency: the same content on a connection ingests once, even
        # under a concurrency race (the second insert conflicts → already_ingested).
        UniqueConstraint(
            "tenant_id",
            "source_connection_id",
            "content_hash",
            name="uq_source_snapshots_connection_content",
        ),
    )

    source_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("source_connections.id"), nullable=False
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    tier: Mapped[SourceTier | None] = mapped_column(SOURCE_TIER, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Row accounting — nothing is silently dropped.
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ingested_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deduplicated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    rejected_reasons: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    # Provenance findings for the manipulation engine (Prompt 08).
    provenance: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    raw_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
