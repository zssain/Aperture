"""ingestion

Adds ingestion columns: source tier + provider on connections; normalised fields and
snapshot linkage on ledger events; period/tier/counts/provenance on snapshots; version +
artefact hash on consents. Introduces the ``source_tier`` and ``event_direction`` enum
types and a ``UNAVAILABLE`` connection status.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

source_tier = postgresql.ENUM(
    "AA_VERIFIED", "BANK_VERIFIED", "DECLARED_DOCUMENT", name="source_tier"
)
event_direction = postgresql.ENUM("CREDIT", "DEBIT", name="event_direction")


def upgrade() -> None:
    bind = op.get_bind()
    source_tier.create(bind, checkfirst=True)
    event_direction.create(bind, checkfirst=True)

    # New connection status value (kept even on downgrade; removed only at base).
    op.execute(
        "ALTER TYPE source_connection_status ADD VALUE IF NOT EXISTS 'UNAVAILABLE'"
    )

    # --- consents ---
    op.add_column(
        "consents",
        sa.Column(
            "version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
    )
    op.add_column(
        "consents", sa.Column("artefact_hash", sa.String(length=64), nullable=True)
    )

    # --- source_connections ---
    op.add_column(
        "source_connections",
        sa.Column("tier", source_tier, nullable=True),
    )
    op.add_column(
        "source_connections",
        sa.Column("provider", sa.String(length=64), nullable=True),
    )

    # --- source_snapshots ---
    op.add_column(
        "source_snapshots", sa.Column("tier", source_tier, nullable=True)
    )
    op.add_column(
        "source_snapshots",
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_snapshots",
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("ingested_count", "deduplicated_count", "rejected_count"):
        op.add_column(
            "source_snapshots",
            sa.Column(col, sa.Integer(), server_default=sa.text("0"), nullable=False),
        )
    op.add_column(
        "source_snapshots",
        sa.Column("rejected_reasons", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "source_snapshots",
        sa.Column("provenance", postgresql.JSONB(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_source_snapshots_connection_content",
        "source_snapshots",
        ["tenant_id", "source_connection_id", "content_hash"],
    )

    # --- ledger_events (append-only; ADD COLUMN is not blocked by the trigger) ---
    op.add_column(
        "ledger_events", sa.Column("source_snapshot_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_ledger_events_source_snapshot_id_source_snapshots"),
        "ledger_events",
        "source_snapshots",
        ["source_snapshot_id"],
        ["id"],
    )
    op.add_column(
        "ledger_events", sa.Column("direction", event_direction, nullable=True)
    )
    op.add_column(
        "ledger_events", sa.Column("balance_paise", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "ledger_events", sa.Column("description", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "ledger_events",
        sa.Column("counterparty_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ledger_events", sa.Column("external_id", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ledger_events", "external_id")
    op.drop_column("ledger_events", "counterparty_hash")
    op.drop_column("ledger_events", "description")
    op.drop_column("ledger_events", "balance_paise")
    op.drop_column("ledger_events", "direction")
    op.drop_constraint(
        op.f("fk_ledger_events_source_snapshot_id_source_snapshots"),
        "ledger_events",
        type_="foreignkey",
    )
    op.drop_column("ledger_events", "source_snapshot_id")

    op.drop_constraint(
        "uq_source_snapshots_connection_content", "source_snapshots", type_="unique"
    )
    op.drop_column("source_snapshots", "provenance")
    op.drop_column("source_snapshots", "rejected_reasons")
    op.drop_column("source_snapshots", "rejected_count")
    op.drop_column("source_snapshots", "deduplicated_count")
    op.drop_column("source_snapshots", "ingested_count")
    op.drop_column("source_snapshots", "period_end")
    op.drop_column("source_snapshots", "period_start")
    op.drop_column("source_snapshots", "tier")

    op.drop_column("source_connections", "provider")
    op.drop_column("source_connections", "tier")

    op.drop_column("consents", "artefact_hash")
    op.drop_column("consents", "version")

    bind = op.get_bind()
    event_direction.drop(bind, checkfirst=True)
    source_tier.drop(bind, checkfirst=True)
    # Note: the 'UNAVAILABLE' enum value is not removed (PostgreSQL cannot drop enum
    # values); it is cleaned up when the type itself is dropped at `downgrade base`.
