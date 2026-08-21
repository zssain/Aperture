"""LedgerEntry — the hash-chained, append-only audit ledger.

Each entry carries a per-tenant monotonic ``seq`` (unique per tenant), the hash of its
own payload, and the hash of the previous entry, forming a tamper-evident chain. Rows
are immutable. The chaining/verification service is built in Prompt 02.
"""

import uuid
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase


class LedgerEntry(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "seq", name="uq_ledger_entries_tenant_id_seq"),)

    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # The entity this audit event concerns (e.g. "decision", <uuid>).
    subject_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
