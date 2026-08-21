"""Outcome — observed repayment behaviour for a decided application (monitoring)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import OUTCOME_LABEL, OutcomeLabel


class Outcome(TenantScopedBase, TimestampMixin):
    __tablename__ = "outcomes"
    __table_args__ = (
        # Query: outcomes by decision (calibration/monitoring) and by application.
        Index("ix_outcomes_decision_id", "decision_id"),
        Index("ix_outcomes_application_id", "application_id"),
        UniqueConstraint(
            "tenant_id",
            "decision_id",
            "label",
            "observed_at",
            name="uq_outcomes_idempotency",
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id"), nullable=False
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("decisions.id"), nullable=True
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    label: Mapped[OutcomeLabel] = mapped_column(OUTCOME_LABEL, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    principal_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    outstanding_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    loss_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
