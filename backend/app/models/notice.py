"""Notice — the decision / recourse-request communication sent to the applicant."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import (
    NOTICE_CHANNEL,
    NOTICE_STATUS,
    NOTICE_TYPE,
    NoticeChannel,
    NoticeStatus,
    NoticeType,
)


class Notice(TenantScopedBase, TimestampMixin):
    __tablename__ = "notices"
    # Query: notices generated for a decision.
    __table_args__ = (Index("ix_notices_decision_id", "decision_id"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id"), nullable=False
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("decisions.id"), nullable=True
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    notice_type: Mapped[NoticeType] = mapped_column(NOTICE_TYPE, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'en'"))
    channel: Mapped[NoticeChannel | None] = mapped_column(NOTICE_CHANNEL, nullable=True)
    status: Mapped[NoticeStatus] = mapped_column(
        NOTICE_STATUS, nullable=False, default=NoticeStatus.RENDERED
    )
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    rendered_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Optional LLM rendering must be validated before it is trusted (Prompt 18).
    llm_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
