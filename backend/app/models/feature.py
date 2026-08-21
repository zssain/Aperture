"""FeatureSnapshot — an immutable, point-in-time feature vector computed ``as_of``.

``values`` holds computed features; ``null_map`` records which features are null
(missing evidence, never a fabricated zero). ``input_hash`` fingerprints the exact
inputs so a decision can be replayed deterministically. Rows are immutable.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase


class FeatureSnapshot(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        # Query: latest snapshot for an applicant at/of a point in time.
        Index("ix_feature_snapshots_applicant_id_as_of", "applicant_id", "as_of"),
        # Query: replay lookup by exact input fingerprint.
        Index("ix_feature_snapshots_input_hash", "input_hash"),
    )

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("applications.id"), nullable=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    null_map: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Contributing event ids (and clamp metadata) per feature — full traceability.
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    classifier_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    catalog_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("merchant_catalog_versions.id"), nullable=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
