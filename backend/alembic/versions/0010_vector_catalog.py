"""pgvector catalogue and classification trace

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    catalog_status_create = postgresql.ENUM(
        "draft", "live", "retired", name="merchant_catalog_status"
    )
    classification_create = postgresql.ENUM(
        "RULE", "VECTOR_KNN", "UNCLASSIFIED", name="classification_method"
    )
    catalog_status_create.create(op.get_bind(), checkfirst=True)
    classification_create.create(op.get_bind(), checkfirst=True)
    catalog_status = postgresql.ENUM(
        "draft", "live", "retired", name="merchant_catalog_status", create_type=False
    )
    classification = postgresql.ENUM(
        "RULE", "VECTOR_KNN", "UNCLASSIFIED", name="classification_method", create_type=False
    )
    op.create_table(
        "merchant_catalog_versions",
        sa.Column("version", sa.String(64), nullable=False, unique=True),
        sa.Column("status", catalog_status, nullable=False),
        sa.Column("embedding_model_id", sa.String(200), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_merchant_catalog_one_live",
        "merchant_catalog_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'live'"),
    )
    op.create_table(
        "merchant_catalog_entries",
        sa.Column("catalog_version_id", sa.Uuid(), sa.ForeignKey("merchant_catalog_versions.id"), nullable=False),
        sa.Column("canonical_name", sa.String(240), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_version_id", "canonical_name", name="uq_catalog_entry_version_name"),
    )
    op.create_index("ix_catalog_entries_catalog_version", "merchant_catalog_entries", ["catalog_version_id"])
    op.create_index(
        "ix_catalog_entries_embedding_hnsw",
        "merchant_catalog_entries",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "embedding_cache",
        sa.Column("embedding_model_id", sa.String(200), nullable=False),
        sa.Column("normalized_text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("embedding_model_id", "normalized_text_hash", name="uq_embedding_cache_model_text"),
    )
    op.add_column("ledger_events", sa.Column("normalized_narration", sa.String(512)))
    op.add_column("ledger_events", sa.Column("category", sa.String(32)))
    op.add_column("ledger_events", sa.Column("classification_method", classification, server_default="UNCLASSIFIED", nullable=False))
    op.add_column("ledger_events", sa.Column("classifier_version", sa.String(32), server_default="clf-v2", nullable=False))
    op.add_column("ledger_events", sa.Column("catalog_version_id", sa.Uuid(), sa.ForeignKey("merchant_catalog_versions.id")))
    op.add_column("ledger_events", sa.Column("match_similarity", sa.Float()))
    op.add_column("ledger_events", sa.Column("matched_entry_id", sa.Uuid(), sa.ForeignKey("merchant_catalog_entries.id")))
    op.add_column("feature_snapshots", sa.Column("catalog_version_id", sa.Uuid(), sa.ForeignKey("merchant_catalog_versions.id")))
    op.execute(
        """CREATE OR REPLACE FUNCTION aperture_forbid_live_catalog_mutation() RETURNS trigger AS $$
        BEGIN
          IF EXISTS (SELECT 1 FROM merchant_catalog_versions v WHERE v.id = OLD.catalog_version_id AND v.status = 'live') THEN
            RAISE EXCEPTION 'merchant_catalog_entries is immutable when its version is live';
          END IF;
          RETURN OLD;
        END; $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_merchant_catalog_entries_immutable BEFORE UPDATE OR DELETE
        ON merchant_catalog_entries FOR EACH ROW EXECUTE FUNCTION aperture_forbid_live_catalog_mutation()"""
    )


def downgrade() -> None:
    op.drop_column("feature_snapshots", "catalog_version_id")
    for column in ("matched_entry_id", "match_similarity", "catalog_version_id", "classifier_version", "classification_method", "category", "normalized_narration"):
        op.drop_column("ledger_events", column)
    op.drop_table("embedding_cache")
    op.drop_table("merchant_catalog_entries")
    op.drop_table("merchant_catalog_versions")
    op.execute("DROP FUNCTION IF EXISTS aperture_forbid_live_catalog_mutation")
    sa.Enum(name="classification_method").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="merchant_catalog_status").drop(op.get_bind(), checkfirst=True)
