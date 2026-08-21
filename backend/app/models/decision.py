"""Decision, DecisionReason, RecourseOption and HumanReview.

A decision is the immutable output of the policy engine over one feature snapshot and
one policy version. It references (never cascades from) the snapshot, policy and
application. ``fired_rules`` and ``terms`` are JSONB; ``approved_limit_paise`` is the
queryable integer-paise limit. Decisions and their reasons are immutable.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase, TimestampMixin
from app.models.enums import (
    DECISION_ACTION,
    REVIEW_OUTCOME,
    REVIEW_STATUS,
    DecisionAction,
    ReviewOutcome,
    ReviewStatus,
)


class Decision(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "decisions"
    __table_args__ = (
        # Query: decisions for an application; decision history for an applicant.
        Index("ix_decisions_application_id", "application_id"),
        Index("ix_decisions_applicant_id_created_at", "applicant_id", "created_at"),
        # Idempotency: at most one decision per (tenant, idempotency_key). Partial so many
        # NULL-key decisions (e.g. replays never persisted) do not collide.
        Index(
            "uq_decisions_tenant_id_idempotency_key",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id"), nullable=False
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    feature_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("feature_snapshots.id"), nullable=False
    )
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("policy_versions.id"), nullable=False
    )
    action: Mapped[DecisionAction] = mapped_column(DECISION_ACTION, nullable=False)
    # The routing recorded by the policy engine (AUTOMATED | HUMAN); a HUMAN routing is not
    # final until a reviewer resolves it.
    routing: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'AUTOMATED'")
    )
    # Idempotency key supplied by the caller; unique per tenant (partial unique index).
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Set True when this decision was drawn into the exploration cohort.
    exploration_cohort: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    approved_limit_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    fired_rules: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # Self-reference; no cascade — a decision is never deleted with its successor.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("decisions.id"), nullable=True
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DecisionReason(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "decision_reasons"
    # Query: reasons attached to a decision.
    __table_args__ = (Index("ix_decision_reasons_decision_id", "decision_id"),)

    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("decisions.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class RecourseOption(TenantScopedBase, TimestampMixin):
    __tablename__ = "recourse_options"
    # Query: recourse options for a decision, ordered by rank.
    __table_args__ = (Index("ix_recourse_options_decision_id", "decision_id"),)

    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("decisions.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_change: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    projected_action: Mapped[DecisionAction | None] = mapped_column(DECISION_ACTION, nullable=True)
    projected_limit_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class HumanReview(TenantScopedBase, TimestampMixin):
    __tablename__ = "human_reviews"
    __table_args__ = (
        # Query: reviews for an application; work queue filtered by status.
        Index("ix_human_reviews_application_id", "application_id"),
        Index("ix_human_reviews_status", "status"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id"), nullable=False
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("decisions.id"), nullable=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    queue: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'default'"))
    status: Mapped[ReviewStatus] = mapped_column(
        REVIEW_STATUS, nullable=False, default=ReviewStatus.PENDING
    )
    outcome: Mapped[ReviewOutcome | None] = mapped_column(REVIEW_OUTCOME, nullable=True)
    # Invariant 10: overrides require a reason code AND free text (enforced in service).
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
