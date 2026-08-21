"""human review finality: one resolved review per decision

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-21

A decision row is immutable (the supersede-once guard freezes every substantive field), so a
human decision cannot be recorded by flipping a flag on the decision. Instead finality is a
``RESOLVED`` row in ``human_reviews``. This partial unique index makes that finality atomic:
at most one resolved review may exist per decision, so two reviewers submitting at the same time
resolve to a single winner and the loser gets a clean 409 - the database guarantee behind the
concurrency edge case, mirroring the idempotency index on ``decisions``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_human_reviews_one_resolved_per_decision"


def upgrade() -> None:
    op.create_index(
        _INDEX,
        "human_reviews",
        ["decision_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RESOLVED' AND decision_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="human_reviews")
