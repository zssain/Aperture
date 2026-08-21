"""ingest intake metadata and awaiting-consent state

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'AWAITING_CONSENT'")
    op.add_column("applications", sa.Column("declared_income_paise", sa.BigInteger()))
    op.add_column("applications", sa.Column("occupation", sa.String(length=64)))


def downgrade() -> None:
    op.drop_column("applications", "occupation")
    op.drop_column("applications", "declared_income_paise")

    # PostgreSQL cannot remove an enum value in place. Rebuild the type so a full
    # upgrade/downgrade round-trip leaves the Prompt 13 schema byte-for-byte compatible.
    op.execute("UPDATE applications SET status = 'OPEN' WHERE status = 'AWAITING_CONSENT'")
    op.execute("ALTER TABLE applications ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE application_status RENAME TO application_status_with_awaiting")
    op.execute(
        "CREATE TYPE application_status AS ENUM "
        "('OPEN', 'PROCESSING', 'DECIDED', 'REFERRED', 'CLOSED')"
    )
    op.execute(
        "ALTER TABLE applications ALTER COLUMN status TYPE application_status "
        "USING status::text::application_status"
    )
    op.execute("ALTER TABLE applications ALTER COLUMN status SET DEFAULT 'OPEN'")
    op.execute("DROP TYPE application_status_with_awaiting")
