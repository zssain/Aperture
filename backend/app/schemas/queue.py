"""Exception-queue API payloads.

The queue is the interface to the residue of automated decisions. Every row carries a
``routed_because`` phrase projected server-side from the decision's fired rules (so the
analyst sees *what kind of thinking a case needs* before opening it), and every assessment
number travels with a ``status`` so the client renders an uncalibrated PD as neutral/UNCAL
exactly as the case file does (invariant 8).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class MetricOut(BaseModel):
    """An assessment number plus the calibration status that governs how it renders."""

    value: float | None
    status: str  # measured | uncalibrated | unavailable


class RoutedBecauseOut(BaseModel):
    text: str
    rule_number: int


class RecommendationOut(BaseModel):
    action: str
    band: str | None
    approved_limit_paise: int | None
    tenor_months: int | None
    annual_rate_bps: int | None


class DecisionChangeOut(BaseModel):
    direction: str
    previous_band: str
    new_band: str
    previous_outcome: str
    new_outcome: str
    human_action_protected: bool


class QueueRowOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    applicant_name: str
    applicant_ref: str
    amount_paise: int | None
    routed_because: RoutedBecauseOut
    recommendation: RecommendationOut
    pd: MetricOut
    coverage: MetricOut
    verification: str  # CLEAR | ELEVATED | HIGH | UNKNOWN
    waiting_seconds: int
    decided_at: datetime
    superseded: bool = False
    change: DecisionChangeOut | None = None


class QueueResponse(BaseModel):
    # The active view is echoed back so a pasted URL round-trips to the identical view.
    view: str
    # Counts for every view the role can see; views the role cannot access are absent.
    counts: dict[str, int]
    rows: list[QueueRowOut]
    next_cursor: str | None
    # Powers the "nothing needs review" success state.
    auto_decided_24h: int
