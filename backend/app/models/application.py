"""Application — a request for credit that flows through the decision pipeline."""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import APPLICATION_STATUS, ApplicationStatus


class Application(TenantScopedBase, TimestampMixin):
    __tablename__ = "applications"
    # Query: list applications for a given applicant.
    __table_args__ = (Index("ix_applications_applicant_id", "applicant_id"),)

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        APPLICATION_STATUS, nullable=False, default=ApplicationStatus.OPEN
    )
    product: Mapped[str | None] = mapped_column(String(64), nullable=True)
    declared_income_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_amount_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    requested_tenor_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
