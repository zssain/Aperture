"""Assessment and ManipulationFinding.

The four independent assessments (risk, affordability, coverage, manipulation) are all
stored as immutable ``assessments`` rows over a single feature snapshot. An
uncalibrated probability is labelled UNCALIBRATED here (``calibration_status``) so the
label travels with the data. ``model_version_id`` is nullable — deterministic
assessments (affordability, coverage) have no model.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CreatedAtMixin, TenantScopedBase
from app.models.enums import (
    ASSESSMENT_KIND,
    CALIBRATION_STATUS,
    FINDING_SEVERITY,
    AssessmentKind,
    CalibrationStatus,
    FindingSeverity,
)


class Assessment(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "assessments"
    # Query: fetch the assessments produced over a given feature snapshot.
    __table_args__ = (Index("ix_assessments_feature_snapshot_id", "feature_snapshot_id"),)

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    feature_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("feature_snapshots.id"), nullable=False
    )
    kind: Mapped[AssessmentKind] = mapped_column(ASSESSMENT_KIND, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_versions.id"), nullable=True
    )
    calibration_status: Mapped[CalibrationStatus] = mapped_column(
        CALIBRATION_STATUS,
        nullable=False,
        default=CalibrationStatus.NOT_APPLICABLE,
    )


class ManipulationFinding(TenantScopedBase, CreatedAtMixin):
    __tablename__ = "manipulation_findings"
    # Query: fetch findings attached to a manipulation assessment.
    __table_args__ = (Index("ix_manipulation_findings_assessment_id", "assessment_id"),)

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assessments.id"), nullable=False
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applicants.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(FINDING_SEVERITY, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
