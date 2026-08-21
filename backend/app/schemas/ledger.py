"""Ledger event API schema."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import EventDirection, EvidenceEventType


class LedgerEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    received_at: datetime
    event_type: EvidenceEventType
    direction: EventDirection | None
    amount_paise: int | None
    balance_paise: int | None
    description: str | None
    counterparty_hash: str | None
    idempotency_key: str
