"""PolicyVersion — a versioned, deterministic lending policy.

At most one row per tenant may be ``LIVE`` at a time; that is enforced by a partial
unique index, so two concurrent publishes cannot both win.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import POLICY_STATUS, PolicyStatus


class PolicyVersion(TenantScopedBase, TimestampMixin):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_policy_versions_tenant_id_version"),
        # At most one live policy per tenant (partial unique index).
        Index(
            "uq_policy_versions_one_live_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'LIVE'"),
        ),
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PolicyStatus] = mapped_column(
        POLICY_STATUS, nullable=False, default=PolicyStatus.DRAFT
    )
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
