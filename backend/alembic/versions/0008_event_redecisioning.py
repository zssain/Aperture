"""event redecisioning and immutable change history

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _immutable(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION aperture_forbid_mutation()"
    )


def upgrade() -> None:
    op.create_table(
        "decision_changes",
        sa.Column("applicant_id", sa.Uuid(), sa.ForeignKey("applicants.id"), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("previous_decision_id", sa.Uuid(), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("new_decision_id", sa.Uuid(), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("previous_band", sa.String(32), nullable=False),
        sa.Column("new_band", sa.String(32), nullable=False),
        sa.Column("previous_outcome", sa.String(64), nullable=False),
        sa.Column("new_outcome", sa.String(64), nullable=False),
        sa.Column("pd_delta_ppb", sa.BigInteger()),
        sa.Column("coverage_delta", sa.BigInteger()),
        sa.Column("feature_changes", postgresql.JSONB(), nullable=False),
        sa.Column("human_action_protected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_decision_changes_new_decision_id", "decision_changes", ["new_decision_id"], unique=True)
    op.create_index("ix_decision_changes_tenant_direction_detected", "decision_changes", ["tenant_id", "direction", "detected_at"])
    op.create_index("ix_decision_changes_application_id", "decision_changes", ["application_id"])
    op.create_index("ix_decision_changes_tenant_id", "decision_changes", ["tenant_id"])

    op.create_table(
        "redecision_alerts",
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("previous_decision_id", sa.Uuid(), sa.ForeignKey("decisions.id")),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_redecision_alerts_application_id", "redecision_alerts", ["application_id"])
    op.create_index("ix_redecision_alerts_tenant_id", "redecision_alerts", ["tenant_id"])

    # Enforces the burst-coalescing invariant even under concurrent requests.
    op.execute(
        "CREATE UNIQUE INDEX uq_jobs_pending_redecision_application ON jobs "
        "(tenant_id, (payload->>'application_id')) "
        "WHERE job_type = 'REDECISION' AND status = 'PENDING'"
    )
    _immutable("decision_changes")
    _immutable("redecision_alerts")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_redecision_alerts_immutable ON redecision_alerts")
    op.execute("DROP TRIGGER IF EXISTS trg_decision_changes_immutable ON decision_changes")
    op.execute("DROP INDEX IF EXISTS uq_jobs_pending_redecision_application")
    op.drop_table("redecision_alerts")
    op.drop_table("decision_changes")
