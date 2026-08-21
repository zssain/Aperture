"""Immutable records produced by event-driven re-decisioning."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase


class DecisionChange(TenantScopedBase, CreatedAtMixin):
    """A durable, queryable comparison between two immutable decisions."""

    __tablename__ = "decision_changes"
    __table_args__ = (
        Index("uq_decision_changes_new_decision_id", "new_decision_id", unique=True),
        Index(
            "ix_decision_changes_tenant_direction_detected", "tenant_id", "direction", "detected_at"
        ),
        Index("ix_decision_changes_application_id", "application_id"),
    )

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id"), nullable=False
    )
    previous_decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("decisions.id"), nullable=False
    )
    new_decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("decisions.id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_band: Mapped[str] = mapped_column(String(32), nullable=False)
    new_band: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    new_outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    # Probability delta in parts-per-billion: exact fixed-point persistence without
    # introducing forbidden floating/numeric database columns.
    pd_delta_ppb: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    coverage_delta: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    feature_changes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    human_action_protected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def pd_delta(self) -> Decimal | None:
        return (
            Decimal(self.pd_delta_ppb) / Decimal(1_000_000_000)
            if self.pd_delta_ppb is not None
            else None
        )


class RedecisionAlert(TenantScopedBase, CreatedAtMixin):
    """Append-only operational alert; failures never damage the prior decision."""

    __tablename__ = "redecision_alerts"
    __table_args__ = (Index("ix_redecision_alerts_application_id", "application_id"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id"), nullable=False
    )
    previous_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("decisions.id"), nullable=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
