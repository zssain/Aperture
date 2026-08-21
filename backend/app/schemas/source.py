"""Source / ingestion API schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import SourceTier
from app.services.ingestion.service import IngestionResult


class FetchRequest(BaseModel):
    period_start: datetime
    period_end: datetime
    # Test hook: inject a provider fault (timeout | error | partial).
    failure_mode: str | None = None


class IngestionResultOut(BaseModel):
    status: str
    snapshot_id: uuid.UUID | None
    tier: SourceTier | None
    already_ingested: bool
    ingested: int
    deduplicated: int
    rejected: int
    rejected_reasons: list[dict[str, Any]]
    provenance: list[dict[str, Any]]

    @classmethod
    def from_result(cls, result: IngestionResult) -> "IngestionResultOut":
        return cls(
            status=result.status,
            snapshot_id=result.snapshot_id,
            tier=result.tier,
            already_ingested=result.already_ingested,
            ingested=result.ingested,
            deduplicated=result.deduplicated,
            rejected=result.rejected,
            rejected_reasons=result.rejected_reasons,
            provenance=result.provenance,
        )
