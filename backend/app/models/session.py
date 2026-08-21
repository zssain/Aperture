"""UserSession — a server-side session record so sessions can be revoked.

The session cookie carries an opaque random token; only the SHA-256 of that token is
stored here (``token_hash``), so a database leak does not reveal live cookies. Idle
expiry slides forward on each authenticated request; ``revoked_at`` supports logout and
administrative revocation.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin


class UserSession(TenantScopedBase, TimestampMixin):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    # SHA-256 hex of the session token; unique so lookup is O(1) and collisions fail.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
