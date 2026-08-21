"""Decision, replay and job API payloads."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DecideRequest(BaseModel):
    # Point-in-time cut-off for the evidence; defaults to now if omitted.
    as_of: datetime | None = None
    idempotency_key: str


class ReasonOut(BaseModel):
    code: str
    polarity: str
    template_params: dict[str, Any]


class RecourseOptionOut(BaseModel):
    lever: str
    target: str
    params: dict[str, Any]
    projected_action: str | None
    projected_limit_paise: int | None
    projected_delta: dict[str, Any]
    expires_at: str | None
    rank: int


class RecourseOut(BaseModel):
    options: list[RecourseOptionOut]
    no_viable_recourse: bool
    timed_out: bool


class DecisionOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    applicant_id: uuid.UUID
    action: str
    routing: str
    outcome: str
    approved_limit_paise: int | None
    terms: dict[str, Any]
    fired_rules: list[dict[str, Any]]
    exploration_cohort: bool
    is_final: bool
    superseded_by: uuid.UUID | None
    reasons: list[ReasonOut]
    recourse: RecourseOut | None
    created: bool


class ReplayRequest(BaseModel):
    policy_version_id: uuid.UUID | None = None


class ReplayOut(BaseModel):
    status: str
    diff: dict[str, dict[str, Any]]
    recomputed_outcome: str
    recomputed_action: str
    stored_action: str
    policy_version_id: uuid.UUID
    counterfactual: bool
    reused_risk: bool


class JobOut(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    error: str | None


class RetryJobRequest(BaseModel):
    stage: str
