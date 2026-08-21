"""Declarative base, shared mixins and the tenant-scoped abstract base.

Immutability and tenancy are enforced in the database (triggers, constraints, the
partial unique index). These classes provide only the structural scaffolding the
models share — no business logic lives here.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint/index names — required for clean, reproducible migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base carrying the shared metadata / naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """A UUID primary key generated client-side so objects have an id pre-flush."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """created_at / updated_at for mutable tables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CreatedAtMixin:
    """created_at only — for append-only / immutable tables that are never updated."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TenantScopedMixin:
    """A non-null, indexed ``tenant_id`` foreign key to ``tenants``."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False, index=True
    )


class TenantScopedBase(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    """Abstract base for every tenant-scoped table (id + tenant_id).

    This is the bound target for :class:`TenantScopedRepository`, which lets tenant
    scoping be enforced structurally rather than by remembering to add a filter.
    """

    __abstract__ = True
