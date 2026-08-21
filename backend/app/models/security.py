"""Security and retention state shared across API replicas."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase


class RateLimitEvent(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "rate_limit_events"
    __table_args__ = (Index("ix_rate_limit_events_bucket_created", "bucket", "created_at"),)
    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    principal_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class RetentionItem(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "retention_items"
    __table_args__ = (Index("ix_retention_items_class_expires", "retention_class", "expires_at"),)
    retention_class: Mapped[str] = mapped_column(String(32), nullable=False)
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=True
    )
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
