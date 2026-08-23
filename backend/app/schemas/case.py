"""Case-file API payloads.

The case file is where a human takes responsibility for a decision, so the contract is
deliberately complete: the application, every source, the decision with its reasons and fired
rules, all four assessments with their versions and calibration status, the manipulation
findings with cited events, recourse, review history, the ``blocking_tab`` the screen opens on,
and the bureau-only counterfactual. Every assessment number travels with a ``status`` so an
uncalibrated PD renders neutral/UNCAL identically wherever it appears (invariant 8).
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.queue import MetricOut


class ApplicantOut(BaseModel):
    id: uuid.UUID
    external_ref: str
    display_name: str | None
    phone: str | None


class ApplicationOut(BaseModel):
    id: uuid.UUID
    status: str
    product: str | None
    requested_amount_paise: int | None
    requested_tenor_months: int | None
    created_at: datetime


class SourceOut(BaseModel):
    id: uuid.UUID
    source_type: str
    tier: str | None
    status: str
    provider: str | None
    period_start: datetime | None
    period_end: datetime | None
    last_sync_at: datetime | None
    freshness_days: int | None


class ReasonOut(BaseModel):
    code: str
    message: str
    polarity: str
    template_params: dict[str, Any]
    order: int


class DecisionOut(BaseModel):
    id: uuid.UUID
    action: str
    routing: str
    outcome: str
    policy_version: str | None
    approved_limit_paise: int | None
    terms: dict[str, Any]
    fired_rules: list[dict[str, Any]]
    exploration_cohort: bool
    is_final: bool
    decided_at: datetime
    reasons: list[ReasonOut]
    resolved: bool


class AssessmentOut(BaseModel):
    kind: str
    engine_version: str
    model_version: str | None
    calibration_status: str
    payload: dict[str, Any]


class CitedEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    direction: str | None
    amount_paise: int | None
    balance_paise: int | None
    description: str | None


class ManipulationFindingOut(BaseModel):
    detector_id: str
    severity: str
    statement: str
    cited_event_ids: list[str]
    confidence: float
    values: dict[str, Any]
    # Resolved so the Verification tab can expand a finding to its cited rows inline.
    cited_events: list[CitedEventOut]


class RecourseOptionOut(BaseModel):
    rank: int
    description: str
    required_change: dict[str, Any]
    projected_action: str | None
    projected_limit_paise: int | None
    verified: bool


class ReviewOut(BaseModel):
    id: uuid.UUID
    queue: str
    status: str
    outcome: str | None
    reason_code: str | None
    reason_text: str | None
    assigned_at: datetime | None
    resolved_at: datetime | None


class CoverageChip(BaseModel):
    score: int | None
    band: str | None
    status: str


class AffordabilityChip(BaseModel):
    status: str
    headroom_paise: int | None


class AssessmentChipsOut(BaseModel):
    pd: MetricOut
    coverage: CoverageChip
    affordability: AffordabilityChip
    verification: str  # CLEAR | ELEVATED | HIGH | UNAVAILABLE


class BureauOut(BaseModel):
    """The applicant's credit-bureau signals, when a bureau file is present. Each is a
    MetricOut so the UI renders a real value or an honest "unavailable" — never a zero."""

    present: bool
    score: MetricOut
    active_loans: MetricOut
    delinquencies_12m: MetricOut


class CounterfactualOut(BaseModel):
    # What a bureau-only policy would have decided: the live policy evaluated with the
    # cash-flow features masked, leaving only the bureau signals.
    available: bool
    outcome: str
    action: str | None
    note: str


class StaleOut(BaseModel):
    is_stale: bool
    new_event_count: int


class CaseOut(BaseModel):
    application: ApplicationOut
    applicant: ApplicantOut
    case_age_seconds: int
    consent_status: str | None
    stale: StaleOut
    feature_snapshot_id: uuid.UUID | None
    sources: list[SourceOut]
    decision: DecisionOut | None
    assessments: dict[str, AssessmentOut]  # keyed by RISK/COVERAGE/AFFORDABILITY/MANIPULATION
    assessment_failed: bool
    chips: AssessmentChipsOut
    manipulation_findings: list[ManipulationFindingOut]
    recourse: list[RecourseOptionOut]
    reviews: list[ReviewOut]
    blocking_tab: str  # evidence | assessment | verification | recourse | decision
    bureau: BureauOut
    bureau_only: CounterfactualOut


# --------------------------------------------------------------------------- #
# Evidence pagination.
# --------------------------------------------------------------------------- #
class EvidenceEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    direction: str | None
    amount_paise: int | None
    balance_paise: int | None
    description: str | None
    category: str
    confidence: float
    classification_method: str
    classifier_version: str
    catalog_version_id: uuid.UUID | None
    matched_entry_id: uuid.UUID | None
    match_similarity: float | None


class EvidencePage(BaseModel):
    rows: list[EvidenceEventOut]
    next_cursor: str | None


# --------------------------------------------------------------------------- #
# Feature lineage — the endpoint that makes traceability enforceable.
# --------------------------------------------------------------------------- #
class LineageOut(BaseModel):
    feature_key: str
    version: str
    dtype: str
    window: str
    formula_doc: str
    null_policy: str
    monotonic_direction: str
    value: float | None
    null_reason: str | None
    contributing_event_ids: list[str]
    recomputed_value: float | None
    matches: bool
