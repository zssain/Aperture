"""auth_and_audit

Adds the server-side ``sessions`` table, per-tenant ``config`` (approval ceilings),
and audit-ledger columns (``event_type`` rename, ``subject_type``/``subject_id``).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Server-side sessions (revocable) ---
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sessions_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_tenant_id"), "sessions", ["tenant_id"])
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])

    # --- Per-tenant config (approval ceilings, etc.) ---
    op.add_column(
        "tenants",
        sa.Column(
            "config",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    # --- Audit ledger: name the event column and record its subject ---
    op.alter_column("ledger_entries", "entry_type", new_column_name="event_type")
    op.add_column(
        "ledger_entries", sa.Column("subject_type", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "ledger_entries", sa.Column("subject_id", sa.Uuid(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ledger_entries", "subject_id")
    op.drop_column("ledger_entries", "subject_type")
    op.alter_column("ledger_entries", "event_type", new_column_name="entry_type")

    op.drop_column("tenants", "config")

    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_tenant_id"), table_name="sessions")
    op.drop_table("sessions")
