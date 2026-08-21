"""LedgerEvent — the append-only, point-in-time evidence ledger.

``occurred_at`` (business time) and ``received_at`` (ingest time) are deliberately
distinct, non-null columns: point-in-time features filter on ``occurred_at`` while
``received_at`` records when the system learned the fact. Rows are immutable.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase
from app.models.enums import (
    CLASSIFICATION_METHOD,
    EVENT_DIRECTION,
    EVIDENCE_EVENT_TYPE,
    ClassificationMethod,
    EventDirection,
    EvidenceEventType,
)


class LedgerEvent(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "ledger_events"
    __table_args__ = (
        # Idempotent ingestion: a duplicate key is a no-op, not a second event.
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_ledger_events_tenant_id_idempotency_key",
        ),
        # Query: point-in-time feature reads (events for an applicant up to as_of).
        Index(
            "ix_ledger_events_applicant_id_occurred_at",
            "applicant_id",
            "occurred_at",
        ),
    )

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    source_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("source_connections.id"), nullable=True
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("source_snapshots.id"), nullable=True
    )
    event_type: Mapped[EvidenceEventType] = mapped_column(EVIDENCE_EVENT_TYPE, nullable=False)
    # Normalised, provider-agnostic fields.
    direction: Mapped[EventDirection | None] = mapped_column(EVENT_DIRECTION, nullable=True)
    amount_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    balance_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'INR'"))
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    normalized_narration: Mapped[str | None] = mapped_column(String(512), nullable=True)
    classification_method: Mapped[ClassificationMethod] = mapped_column(
        CLASSIFICATION_METHOD,
        nullable=False,
        default=ClassificationMethod.UNCLASSIFIED,
        server_default=text("'UNCLASSIFIED'"),
    )
    classifier_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="clf-v2", server_default=text("'clf-v2'")
    )
    catalog_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("merchant_catalog_versions.id"), nullable=True
    )
    match_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("merchant_catalog_entries.id"), nullable=True
    )
    # HMAC of the counterparty (per-tenant salt) — the raw name is never stored.
    counterparty_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Provider transaction id, when one exists (used for idempotency).
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
