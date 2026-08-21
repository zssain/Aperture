"""Consent — the applicant's authorisation to collect evidence from named sources."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import CONSENT_STATUS, ConsentStatus


class Consent(TenantScopedBase, TimestampMixin):
    __tablename__ = "consents"
    # Query: list consents for a given applicant.
    __table_args__ = (Index("ix_consents_applicant_id", "applicant_id"),)

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    status: Mapped[ConsentStatus] = mapped_column(
        CONSENT_STATUS, nullable=False, default=ConsentStatus.GRANTED
    )
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # Hash of the immutable consent artefact (purpose, scope, validity, version).
    artefact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
