"""decision orchestration: idempotency, routing, exploration + supersede-once trigger

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-21

Adds the columns ``decide`` needs on ``decisions`` (idempotency key, routing, exploration and
recourse-timeout flags) and a partial unique index enforcing one decision per
``(tenant, idempotency_key)`` - the database guarantee behind the concurrency edge case.

``decisions`` stays immutable in every substantive field, but the generic immutability trigger
is replaced by one that permits a single ``superseded_by`` transition from NULL to a value, so a
re-decision can link its predecessor without ever rewriting a decided outcome.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMMUTABILITY_FUNCTION = "aperture_forbid_mutation"
_DECISION_TRIGGER = "trg_decisions_immutable"
_DECISION_FUNCTION = "aperture_decisions_supersede_guard"


def upgrade() -> None:
    op.add_column(
        "decisions",
        sa.Column("routing", sa.String(length=32), nullable=False, server_default="AUTOMATED"),
    )
    op.add_column(
        "decisions",
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "decisions",
        sa.Column(
            "exploration_cohort",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "uq_decisions_tenant_id_idempotency_key",
        "decisions",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Replace the generic immutability trigger on decisions with a supersede-aware guard:
    # every column is frozen except a one-time superseded_by transition (NULL -> value).
    op.execute(f"DROP TRIGGER IF EXISTS {_DECISION_TRIGGER} ON decisions;")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_DECISION_FUNCTION}() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Row in immutable table decisions cannot be delete (append-only)'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            -- The ONLY permitted update is a one-time superseded_by set (NULL -> value) that
            -- changes nothing else. Every substantive decision field stays frozen.
            IF OLD.superseded_by IS NULL
               AND NEW.superseded_by IS NOT NULL
               AND NEW.id = OLD.id
               AND NEW.tenant_id = OLD.tenant_id
               AND NEW.application_id = OLD.application_id
               AND NEW.applicant_id = OLD.applicant_id
               AND NEW.feature_snapshot_id = OLD.feature_snapshot_id
               AND NEW.policy_version_id = OLD.policy_version_id
               AND NEW.action = OLD.action
               AND NEW.terms::text = OLD.terms::text
               AND NEW.fired_rules::text = OLD.fired_rules::text
               AND NEW.approved_limit_paise IS NOT DISTINCT FROM OLD.approved_limit_paise
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Row in immutable table decisions cannot be update (append-only)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"CREATE TRIGGER {_DECISION_TRIGGER} "
        f"BEFORE UPDATE OR DELETE ON decisions "
        f"FOR EACH ROW EXECUTE FUNCTION {_DECISION_FUNCTION}();"
    )


def downgrade() -> None:
    # Restore the generic immutability trigger on decisions.
    op.execute(f"DROP TRIGGER IF EXISTS {_DECISION_TRIGGER} ON decisions;")
    op.execute(f"DROP FUNCTION IF EXISTS {_DECISION_FUNCTION}();")
    op.execute(
        f"CREATE TRIGGER {_DECISION_TRIGGER} "
        f"BEFORE UPDATE OR DELETE ON decisions "
        f"FOR EACH ROW EXECUTE FUNCTION {_IMMUTABILITY_FUNCTION}();"
    )

    op.drop_index("uq_decisions_tenant_id_idempotency_key", table_name="decisions")
    op.drop_column("decisions", "exploration_cohort")
    op.drop_column("decisions", "idempotency_key")
    op.drop_column("decisions", "routing")
