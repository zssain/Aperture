"""User — an operator (policy owner, analyst, fraud reviewer, auditor)."""

from sqlalchemy import Boolean, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import USER_ROLE, UserRole


class User(TenantScopedBase, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(USER_ROLE, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Populated by the auth stage (Prompt 02); nullable here so no auth logic leaks in.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
