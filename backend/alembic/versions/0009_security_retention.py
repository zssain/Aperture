"""security rate-limit and retention records

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enforce outcome idempotency under concurrent service deliveries, not only in
    # application code.
    op.create_unique_constraint(
        "uq_outcomes_idempotency",
        "outcomes",
        ["tenant_id", "decision_id", "label", "observed_at"],
    )
    op.create_table(
        "rate_limit_events",
        sa.Column("bucket", sa.String(64), nullable=False),
        sa.Column("principal_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_events_bucket_created", "rate_limit_events", ["bucket", "created_at"])
    op.create_index("ix_rate_limit_events_tenant_id", "rate_limit_events", ["tenant_id"])
    op.create_table(
        "retention_items",
        sa.Column("retention_class", sa.String(32), nullable=False),
        sa.Column("applicant_id", sa.Uuid(), sa.ForeignKey("applicants.id")),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.Uuid()),
        sa.Column("storage_path", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("legal_hold", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_items_class_expires", "retention_items", ["retention_class", "expires_at"])
    op.create_index("ix_retention_items_tenant_id", "retention_items", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("retention_items")
    op.drop_table("rate_limit_events")
    # IF EXISTS keeps downgrade safe for environments that briefly ran an earlier
    # development build of revision 0009 before this concurrency constraint landed.
    op.execute("ALTER TABLE outcomes DROP CONSTRAINT IF EXISTS uq_outcomes_idempotency")
