"""feature_lineage

Adds ``lineage`` (contributing event ids + clamp metadata per feature) and
``classifier_version`` to feature_snapshots.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feature_snapshots", sa.Column("lineage", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "feature_snapshots",
        sa.Column("classifier_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feature_snapshots", "classifier_version")
    op.drop_column("feature_snapshots", "lineage")
