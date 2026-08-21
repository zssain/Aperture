"""Validated boundaries for starting a case from the ingest screen."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ApplicationStatus, SourceType
from app.schemas.source import IngestionResultOut

MIN_AMOUNT_PAISE = 100_000
MAX_AMOUNT_PAISE = 500_000_000
MIN_INCOME_PAISE = 1
MAX_INCOME_PAISE = 1_000_000_000
MIN_TENOR_MONTHS = 3
MAX_TENOR_MONTHS = 60


class ApplicationFields(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    external_ref: str = Field(min_length=1, max_length=128)
    declared_income_paise: int = Field(ge=MIN_INCOME_PAISE, le=MAX_INCOME_PAISE)
    occupation: str = Field(min_length=1, max_length=64)
    requested_amount_paise: int = Field(ge=MIN_AMOUNT_PAISE, le=MAX_AMOUNT_PAISE)
    requested_tenor_months: int = Field(ge=MIN_TENOR_MONTHS, le=MAX_TENOR_MONTHS)
    product: str = Field(default="PERSONAL_LOAN", min_length=1, max_length=64)


class ConnectCaseRequest(ApplicationFields):
    consent_granted: bool
    purpose: str = Field(default="Credit underwriting", min_length=1, max_length=200)
    scope: list[SourceType] = Field(default_factory=list)
    expires_at: datetime | None = None
    failure_modes: dict[SourceType, Literal["timeout", "error", "partial"]] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_consent(self) -> "ConnectCaseRequest":
        if self.consent_granted and not self.scope:
            raise ValueError("Select at least one consent scope")
        if not self.consent_granted and self.scope:
            raise ValueError("Consent scopes cannot be selected when consent is declined")
        return self


class CaseIntakeOut(BaseModel):
    status: str
    already_ingested: bool = False
    application_id: uuid.UUID
    applicant_id: uuid.UUID
    application_status: ApplicationStatus
    job_id: uuid.UUID | None = None
    ingestion: IngestionResultOut | None = None
    existing_case_url: str | None = None
