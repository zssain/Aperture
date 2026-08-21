"""Applicant — the borrower being assessed."""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin


class Applicant(TenantScopedBase, TimestampMixin):
    __tablename__ = "applicants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_ref", name="uq_applicants_tenant_id_external_ref"),
    )

    external_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
