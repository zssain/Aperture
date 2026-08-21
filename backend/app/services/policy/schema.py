"""Policy types: the versioned rule model and the pure engine's inputs/outputs.

Everything the engine reads and returns is defined here as a frozen structure. ``PolicyRules``
is the ONLY place a threshold may live (invariant 1: the decision is diffable, not hidden in
a model). The four assessment inputs are lightweight, model-free views so ``evaluate`` stays
a pure function with no dependency on the ML stack.
"""

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict


# --------------------------------------------------------------------------- #
# Outcomes and routing.
# --------------------------------------------------------------------------- #
class PolicyOutcome(enum.StrEnum):
    FRAUD_REVIEW = "FRAUD_REVIEW"
    DECLINE_AFFORDABILITY = "DECLINE_AFFORDABILITY"
    REVIEW_EVIDENCE = "REVIEW_EVIDENCE"
    REVIEW_FRAUD = "REVIEW_FRAUD"
    DECLINE_RISK = "DECLINE_RISK"
    APPROVE_ENHANCED = "APPROVE_ENHANCED"
    APPROVE_STANDARD = "APPROVE_STANDARD"
    APPROVE_STARTER = "APPROVE_STARTER"
    SYSTEM_UNAVAILABLE = "SYSTEM_UNAVAILABLE"


APPROVAL_OUTCOMES: frozenset[PolicyOutcome] = frozenset(
    {
        PolicyOutcome.APPROVE_ENHANCED,
        PolicyOutcome.APPROVE_STANDARD,
        PolicyOutcome.APPROVE_STARTER,
    }
)


class Routing(enum.StrEnum):
    AUTOMATED = "AUTOMATED"
    HUMAN = "HUMAN"
    SYSTEM_UNAVAILABLE = "SYSTEM_UNAVAILABLE"


class Polarity(enum.StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


# --------------------------------------------------------------------------- #
# The versioned policy (thresholds + terms ladder). Frozen: a policy is a fact.
# --------------------------------------------------------------------------- #
class Graduation(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_months: int
    on_time_emis_required: int
    next_band: str  # a PolicyOutcome approval band to step up to


class TermsBand(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_principal_paise: int
    max_tenor_months: int
    rate_band: str
    annual_rate_bps: int
    graduation: Graduation | None = None


class PolicyRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str
    # Gate thresholds.
    min_coverage: int
    pd_decline_threshold: float
    pd_enhanced: float
    pd_standard: float
    cov_high: int
    cov_mid: int
    mandatory_review_ceiling_paise: int
    # Exploration cohort.
    exploration_margin: float
    exploration_budget: float
    # Terms ladder, keyed by approval-band outcome value.
    terms: dict[str, TermsBand]


# --------------------------------------------------------------------------- #
# Engine inputs: four assessments + the loan request.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ManipulationInput:
    band: str  # CLEAR | ELEVATED | HIGH


@dataclass(frozen=True)
class AffordabilityInput:
    status: str  # PASS | FAIL | INDETERMINATE
    max_supportable_principal_paise: int | None
    dsr: float | None = None
    dsr_ceiling: float | None = None


@dataclass(frozen=True)
class MissingSourceInput:
    source_type: str
    coverage_delta: int


@dataclass(frozen=True)
class CoverageInput:
    score: int
    band: str
    missing_sources: tuple[MissingSourceInput, ...] = ()


@dataclass(frozen=True)
class ContributorInput:
    feature: str
    contribution: float
    direction: str  # increases_risk | decreases_risk


@dataclass(frozen=True)
class RiskInput:
    # ``pd`` is None when risk could not be scored (invariant 2): route SYSTEM_UNAVAILABLE.
    pd: float | None
    calibration_status: str = "UNCALIBRATED"
    top_contributors: tuple[ContributorInput, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoanRequest:
    application_id: uuid.UUID
    amount_paise: int
    tenor_months: int
    annual_rate_bps: int


@dataclass(frozen=True)
class FourAssessments:
    """All four must be present. A decision from three of four is not a decision, so any
    ``None`` here makes the engine raise :class:`MissingAssessmentError`."""

    manipulation: ManipulationInput | None = None
    affordability: AffordabilityInput | None = None
    coverage: CoverageInput | None = None
    risk: RiskInput | None = None


# --------------------------------------------------------------------------- #
# Engine output.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FiredRule:
    number: int
    name: str
    outcome: str  # the outcome this rule selected, or "" for a modifier


@dataclass(frozen=True)
class Reason:
    code: str
    polarity: str
    template_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Terms:
    band: str
    max_principal_paise: int
    approved_principal_paise: int
    max_tenor_months: int
    approved_tenor_months: int
    rate_band: str
    annual_rate_bps: int
    graduation: dict[str, Any] | None


@dataclass(frozen=True)
class PolicyDecision:
    outcome: str
    routing: str
    terms: Terms | None
    approved_limit_paise: int | None
    fired_rules: tuple[FiredRule, ...]
    reasons: tuple[Reason, ...]
    exploration_cohort: bool
    policy_version: str
    reasons_catalogue_version: str


class MissingAssessmentError(Exception):
    """One of the four assessments was not supplied. The engine never decides without all
    four (invariant 1 + invariant 2)."""
