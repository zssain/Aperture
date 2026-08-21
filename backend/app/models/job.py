"""Job — a unit of work for the Postgres-backed queue.

The queue uses ``SELECT ... FOR UPDATE SKIP LOCKED`` (Prompt 10); the
``(status, run_after)`` index supports fetching the next runnable pending job.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import JOB_STATUS, JOB_TYPE, JobStatus, JobType


class Job(TenantScopedBase, TimestampMixin):
    __tablename__ = "jobs"
    # Query: claim the next pending job ordered by run_after (SKIP LOCKED).
    __table_args__ = (Index("ix_jobs_status_run_after", "status", "run_after"),)

    job_type: Mapped[JobType] = mapped_column(JOB_TYPE, nullable=False)
    status: Mapped[JobStatus] = mapped_column(JOB_STATUS, nullable=False, default=JobStatus.PENDING)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
