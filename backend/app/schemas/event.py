"""Schemas for the real-time event ingestion API."""

import uuid
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.models.enums import EventDirection, SourceType


class EventCreate(BaseModel):
    applicant_ref: str = Field(min_length=1, max_length=128)
    source_type: SourceType
    occurred_at: AwareDatetime
    amount_paise: int = Field(gt=0)
    direction: EventDirection
    description: str = Field(min_length=1, max_length=512)
    counterparty: str | None = Field(default=None, max_length=256)
    external_id: str = Field(min_length=1, max_length=200)

    @field_validator("occurred_at")
    @classmethod
    def not_in_future(cls, value: datetime) -> datetime:
        if value > datetime.now(UTC):
            raise ValueError("occurred_at must not be in the future")
        return value


class EventIngestionOut(BaseModel):
    event_id: uuid.UUID
    job_id: uuid.UUID | None
    status: str
    reason: str | None = None


class DemoEventResultOut(BaseModel):
    applicant_ref: str
    event_ids: list[uuid.UUID]
    job_id: uuid.UUID | None


class DemoIncomeConsistencyRequest(BaseModel):
    applicant_ref: str = Field(min_length=1, max_length=128)
    source_type: SourceType = SourceType.BANK
