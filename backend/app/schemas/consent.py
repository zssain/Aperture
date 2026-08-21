"""Consent API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ConsentStatus,
    SourceConnectionStatus,
    SourceTier,
    SourceType,
)


class ConsentCreateRequest(BaseModel):
    purpose: str = Field(min_length=1, max_length=200)
    scope: list[SourceType] = Field(min_length=1)
    expires_at: datetime | None = None


class SourceConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: SourceType
    tier: SourceTier | None
    status: SourceConnectionStatus


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    applicant_id: uuid.UUID
    purpose: str
    version: int
    artefact_hash: str | None
    status: ConsentStatus
    granted_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class ConsentCreatedResponse(BaseModel):
    consent: ConsentOut
    connections: list[SourceConnectionOut]
