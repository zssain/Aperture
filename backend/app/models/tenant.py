"""Tenant — the root of every tenancy boundary (not itself tenant-scoped)."""

from typing import Any

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # Tenant configuration, e.g. per-role approval ceilings:
    #   {"approval_ceilings_paise": {"CREDIT_ANALYST": 5000000, ...}}
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
