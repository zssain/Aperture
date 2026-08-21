"""Typed assessment payloads (schema-validated before persistence)."""

from typing import Any

from pydantic import BaseModel


class CoverageComponentModel(BaseModel):
    name: str
    weight: int
    fraction: float
    contribution: float
    detail: str


class MissingSourceModel(BaseModel):
    source_type: str
    why: str
    coverage_delta: int


class CoveragePayload(BaseModel):
    score: int
    band: str
    weights_version: str
    components: list[CoverageComponentModel]
    missing_sources: list[MissingSourceModel]


class AffordabilityPayload(BaseModel):
    status: str
    reason: str
    income_basis: str  # "median" | "p25" | "none"
    irregular_income: bool
    net_monthly_income_paise: int | None
    recurring_obligations_paise: int
    essential_expenses_paise: int
    disposable_income_paise: int | None
    requested_amount_paise: int
    tenor_months: int
    annual_rate_bps: int
    new_emi_paise: int | None
    existing_emi_paise: int
    dsr: float | None
    dsr_ceiling: float
    stressed_dsr: float | None
    stress_pass: bool | None
    max_supportable_emi_paise: int | None
    max_supportable_principal_paise: int | None
    policy_version: str


class ManipulationFindingModel(BaseModel):
    detector_id: str
    severity: str
    statement: str
    cited_event_ids: list[str]
    confidence: float
    values: dict[str, Any]


class ManipulationPayload(BaseModel):
    band: str  # HIGH | ELEVATED | CLEAR
    config_version: str
    detector_statuses: dict[str, str]
    skipped: list[str]
    insufficient: list[str]
    trigger_counts: dict[str, int]
    findings: list[ManipulationFindingModel]
