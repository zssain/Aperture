"""ModelVersion — the registry of trained risk model artifacts.

Tenant-scoped (invariant 9: every table is tenant-scoped). A model's calibration
status is recorded here and mirrors onto any assessment that uses it.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedBase, TimestampMixin
from app.models.enums import (
    CALIBRATION_STATUS,
    MODEL_STATUS,
    CalibrationStatus,
    ModelStatus,
)


class ModelVersion(TenantScopedBase, TimestampMixin):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "name",
            "version",
            name="uq_model_versions_tenant_id_name_version",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ModelStatus] = mapped_column(
        MODEL_STATUS, nullable=False, default=ModelStatus.REGISTERED
    )
    calibration_status: Mapped[CalibrationStatus] = mapped_column(
        CALIBRATION_STATUS,
        nullable=False,
        default=CalibrationStatus.UNCALIBRATED,
    )
    artifact_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
