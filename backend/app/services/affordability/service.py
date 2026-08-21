"""Affordability arithmetic — transparent, deterministic, model-free.

Every intermediate value is returned so the UI can render the calculation as a worked
sum. Money is integer paise; the EMI is computed with :class:`decimal.Decimal` (never
floating point). Null income yields ``INDETERMINATE`` — never ``FAIL``.
"""

import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, getcontext
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.models.enums import AssessmentKind, CalibrationStatus
from app.models.feature import FeatureSnapshot
from app.schemas.assessment import AffordabilityPayload

getcontext().prec = 50

AFFORDABILITY_POLICY_VERSION = "afford-policy-v1"
AFFORDABILITY_ENGINE = "affordability-v1"

AFFORDABILITY_POLICY: dict[str, Any] = {
    "version": AFFORDABILITY_POLICY_VERSION,
    "dsr_ceiling": 0.5,  # (existing + new EMI) / net monthly income
    "irregular_income_cv_threshold": 0.25,  # above this, use the 25th percentile
    "stress_income_factor": 0.85,  # -15% income
    "stress_expense_factor": 1.20,  # +20% obligations
}

# Status / reason codes.
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_INDETERMINATE = "INDETERMINATE"
REASON_INCOME_NOT_OBSERVABLE = "income_not_observable"
REASON_PASS = "within_dsr_ceiling"
REASON_DSR_EXCEEDS = "dsr_exceeds_ceiling"
REASON_PRINCIPAL_EXCEEDS = "principal_exceeds_max"


@dataclass(frozen=True)
class RequestedTerms:
    amount_paise: int
    tenor_months: int
    annual_rate_bps: int  # basis points, e.g. 1800 = 18.00% p.a.


@dataclass(frozen=True)
class AffordabilityAssessment:
    status: str
    reason: str
    income_basis: str
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
    engine_version: str
    policy_version: str


def compute_emi_paise(principal_paise: int, tenor_months: int, annual_rate_bps: int) -> int:
    """Standard reducing-balance EMI in integer paise (Decimal arithmetic)."""
    if tenor_months <= 0:
        raise ValueError("tenor_months must be positive")
    principal = Decimal(principal_paise)
    if annual_rate_bps == 0:
        return int((principal / Decimal(tenor_months)).quantize(Decimal(1), ROUND_HALF_UP))
    monthly_rate = Decimal(annual_rate_bps) / Decimal(120_000)  # bps → monthly fraction
    factor = (Decimal(1) + monthly_rate) ** tenor_months
    emi = principal * monthly_rate * factor / (factor - Decimal(1))
    return int(emi.quantize(Decimal(1), ROUND_HALF_UP))


def principal_from_emi_paise(emi_paise: int, tenor_months: int, annual_rate_bps: int) -> int:
    """Inverse of the EMI formula — the principal an EMI can support (floored)."""
    if emi_paise <= 0 or tenor_months <= 0:
        return 0
    emi = Decimal(emi_paise)
    if annual_rate_bps == 0:
        return int((emi * Decimal(tenor_months)).quantize(Decimal(1), ROUND_DOWN))
    monthly_rate = Decimal(annual_rate_bps) / Decimal(120_000)
    factor = (Decimal(1) + monthly_rate) ** tenor_months
    principal = emi * (factor - Decimal(1)) / (monthly_rate * factor)
    return int(principal.quantize(Decimal(1), ROUND_DOWN))


def _select_income(values: dict[str, Any], policy: dict[str, Any]) -> tuple[int | None, str, bool]:
    median = values.get("median_monthly_inflow_paise")
    p25 = values.get("p25_monthly_inflow_paise")
    cv = values.get("monthly_inflow_cv")
    irregular = cv is not None and cv > policy["irregular_income_cv_threshold"]
    if irregular:
        return (p25, "p25", True) if p25 is not None else (None, "none", True)
    return (median, "median", False) if median is not None else (None, "none", False)


def assess_affordability(
    feature_snapshot: FeatureSnapshot,
    requested_terms: RequestedTerms,
    policy: dict[str, Any] = AFFORDABILITY_POLICY,
) -> AffordabilityAssessment:
    values = feature_snapshot.values
    dsr_ceiling = float(policy["dsr_ceiling"])
    existing_emi = int(values.get("monthly_emi_paise") or 0)
    essential = int(values.get("essential_expense_paise") or 0)

    net_income, income_basis, irregular = _select_income(values, policy)
    engine_version = f"{AFFORDABILITY_ENGINE}+{policy['version']}"

    def _build(
        status: str,
        reason: str,
        *,
        net: int | None,
        disposable: int | None,
        new_emi: int | None,
        dsr: float | None,
        stressed_dsr: float | None,
        stress_pass: bool | None,
        max_emi: int | None,
        max_principal: int | None,
    ) -> AffordabilityAssessment:
        return AffordabilityAssessment(
            status=status,
            reason=reason,
            income_basis=income_basis,
            irregular_income=irregular,
            net_monthly_income_paise=net,
            recurring_obligations_paise=existing_emi,
            essential_expenses_paise=essential,
            disposable_income_paise=disposable,
            requested_amount_paise=requested_terms.amount_paise,
            tenor_months=requested_terms.tenor_months,
            annual_rate_bps=requested_terms.annual_rate_bps,
            new_emi_paise=new_emi,
            existing_emi_paise=existing_emi,
            dsr=dsr,
            dsr_ceiling=dsr_ceiling,
            stressed_dsr=stressed_dsr,
            stress_pass=stress_pass,
            max_supportable_emi_paise=max_emi,
            max_supportable_principal_paise=max_principal,
            engine_version=engine_version,
            policy_version=policy["version"],
        )

    # Unobservable income is a COVERAGE problem — never a FAIL.
    if net_income is None:
        return _build(
            STATUS_INDETERMINATE,
            REASON_INCOME_NOT_OBSERVABLE,
            net=None,
            disposable=None,
            new_emi=None,
            dsr=None,
            stressed_dsr=None,
            stress_pass=None,
            max_emi=None,
            max_principal=None,
        )

    new_emi = compute_emi_paise(
        requested_terms.amount_paise,
        requested_terms.tenor_months,
        requested_terms.annual_rate_bps,
    )
    disposable = net_income - existing_emi - essential
    dsr = (existing_emi + new_emi) / net_income

    # Terms cap: max EMI under the DSR ceiling, and the principal it supports.
    allowed_total_emi = int(Decimal(net_income) * Decimal(str(dsr_ceiling)))
    max_emi = max(0, allowed_total_emi - existing_emi)
    max_principal = principal_from_emi_paise(
        max_emi, requested_terms.tenor_months, requested_terms.annual_rate_bps
    )

    # Stress: -15% income, +20% obligations.
    stressed_income = net_income * Decimal(str(policy["stress_income_factor"]))
    stressed_existing = Decimal(existing_emi) * Decimal(str(policy["stress_expense_factor"]))
    stressed_dsr = float((stressed_existing + Decimal(new_emi)) / stressed_income)
    stress_pass = stressed_dsr <= dsr_ceiling

    if requested_terms.amount_paise > max_principal:
        status, reason = STATUS_FAIL, REASON_PRINCIPAL_EXCEEDS
    elif dsr <= dsr_ceiling:
        status, reason = STATUS_PASS, REASON_PASS
    else:
        status, reason = STATUS_FAIL, REASON_DSR_EXCEEDS

    return _build(
        status,
        reason,
        net=net_income,
        disposable=disposable,
        new_emi=new_emi,
        dsr=dsr,
        stressed_dsr=stressed_dsr,
        stress_pass=stress_pass,
        max_emi=max_emi,
        max_principal=max_principal,
    )


def affordability_payload(assessment: AffordabilityAssessment) -> AffordabilityPayload:
    return AffordabilityPayload(
        status=assessment.status,
        reason=assessment.reason,
        income_basis=assessment.income_basis,
        irregular_income=assessment.irregular_income,
        net_monthly_income_paise=assessment.net_monthly_income_paise,
        recurring_obligations_paise=assessment.recurring_obligations_paise,
        essential_expenses_paise=assessment.essential_expenses_paise,
        disposable_income_paise=assessment.disposable_income_paise,
        requested_amount_paise=assessment.requested_amount_paise,
        tenor_months=assessment.tenor_months,
        annual_rate_bps=assessment.annual_rate_bps,
        new_emi_paise=assessment.new_emi_paise,
        existing_emi_paise=assessment.existing_emi_paise,
        dsr=assessment.dsr,
        dsr_ceiling=assessment.dsr_ceiling,
        stressed_dsr=assessment.stressed_dsr,
        stress_pass=assessment.stress_pass,
        max_supportable_emi_paise=assessment.max_supportable_emi_paise,
        max_supportable_principal_paise=assessment.max_supportable_principal_paise,
        policy_version=assessment.policy_version,
    )


async def persist_affordability(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    feature_snapshot: FeatureSnapshot,
    assessment: AffordabilityAssessment,
) -> Assessment:
    payload = affordability_payload(assessment)
    row = Assessment(
        tenant_id=tenant_id,
        applicant_id=feature_snapshot.applicant_id,
        feature_snapshot_id=feature_snapshot.id,
        kind=AssessmentKind.AFFORDABILITY,
        payload=payload.model_dump(mode="json"),
        engine_version=assessment.engine_version,
        calibration_status=CalibrationStatus.NOT_APPLICABLE,
    )
    session.add(row)
    await session.commit()
    return row
