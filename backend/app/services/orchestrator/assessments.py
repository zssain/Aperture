"""Run all four assessments over a stored snapshot and adapt them to the policy inputs.

Shared by ``decide`` (fresh run) and ``replay`` (recompute over the stored snapshot). The
four assessments run purely in memory here; the orchestrator persists them only inside its
single decision transaction, so a failure leaves nothing behind (invariant 2).

Fraud reads no risk and risk reads no fraud (invariant 5); this module simply collects both
independent results for the policy engine, which is the only component allowed to see all four.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import AssessmentKind, CalibrationStatus, SourceTier, SourceType
from app.models.feature import FeatureSnapshot
from app.models.ledger import LedgerEvent
from app.models.source import SourceConnection, SourceSnapshot
from app.services.affordability.service import (
    AffordabilityAssessment,
    RequestedTerms,
    affordability_payload,
    assess_affordability,
)
from app.services.coverage.service import (
    CoverageAssessment,
    SourceEvidence,
    assess_coverage,
    coverage_payload,
)
from app.services.coverage.weights import COVERAGE_WEIGHTS_VERSION
from app.services.manipulation.context import (
    DeclaredApplication,
    LedgerEventView,
    ProvenanceView,
    SourceMetadataView,
)
from app.services.manipulation.service import (
    ManipulationAssessment,
    manipulation_payload,
)
from app.services.manipulation.service import (
    assess as assess_manipulation,
)
from app.services.manipulation.service import (
    build_context as build_manipulation_context,
)
from app.services.policy.schema import (
    AffordabilityInput,
    ContributorInput,
    CoverageInput,
    FourAssessments,
    LoanRequest,
    ManipulationInput,
    MissingSourceInput,
    RiskInput,
)
from app.services.risk.service import RiskAssessment, assess_risk

# A sane default when an application does not record terms (kept out of the policy).
_DEFAULT_TENOR_MONTHS = 12
_DEFAULT_RATE_BPS = 1800


class AssessmentFailureError(Exception):
    """An assessment raised: persist nothing, route SYSTEM_UNAVAILABLE (invariant 2)."""

    def __init__(self, which: str, cause: Exception) -> None:
        super().__init__(f"{which} assessment failed: {cause!r}")
        self.which = which
        self.cause = cause


@dataclass(frozen=True)
class AssessmentBundle:
    risk: RiskAssessment
    coverage: CoverageAssessment
    affordability: AffordabilityAssessment
    manipulation: ManipulationAssessment


async def _load_source_evidence(
    session: AsyncSession, tenant_id: uuid.UUID, applicant_id: uuid.UUID
) -> list[SourceEvidence]:
    stmt = (
        select(SourceSnapshot, SourceConnection)
        .join(SourceConnection, SourceSnapshot.source_connection_id == SourceConnection.id)
        .where(
            SourceSnapshot.tenant_id == tenant_id,
            SourceSnapshot.applicant_id == applicant_id,
        )
    )
    evidence: list[SourceEvidence] = []
    for snapshot, connection in await session.execute(stmt):
        latest = snapshot.period_end or snapshot.fetched_at
        evidence.append(
            SourceEvidence(
                source_type=connection.source_type or SourceType.BANK,
                tier=snapshot.tier or connection.tier or SourceTier.DECLARED_DOCUMENT,
                latest_event_at=latest,
            )
        )
    return evidence


async def _load_manipulation_sources(
    session: AsyncSession, tenant_id: uuid.UUID, applicant_id: uuid.UUID
) -> list[SourceMetadataView]:
    stmt = select(SourceSnapshot).where(
        SourceSnapshot.tenant_id == tenant_id,
        SourceSnapshot.applicant_id == applicant_id,
    )
    views: list[SourceMetadataView] = []
    for snapshot in await session.scalars(stmt):
        raw = snapshot.provenance or []
        provenance = tuple(
            ProvenanceView(code=p["code"], severity=p["severity"], detail=p.get("detail", ""))
            for p in raw
            if isinstance(p, dict) and "code" in p and "severity" in p
        )
        views.append(
            SourceMetadataView(
                source_snapshot_id=snapshot.id,
                tier=snapshot.tier.value if snapshot.tier else None,
                provenance=provenance,
                event_ids=(),  # linkage populated when snapshots stamp their events
            )
        )
    return views


def _risk_input(risk: RiskAssessment) -> RiskInput:
    ranked = sorted(risk.contributions, key=lambda c: -abs(float(c.get("contribution", 0.0))))
    contributors = tuple(
        ContributorInput(
            feature=str(c["feature"]),
            contribution=float(c["contribution"]),
            direction="increases_risk" if float(c["contribution"]) > 0 else "decreases_risk",
        )
        for c in ranked[:5]
        if "feature" in c and "contribution" in c
    )
    return RiskInput(
        pd=risk.pd,
        calibration_status=risk.calibration_status,
        top_contributors=contributors,
        reason_codes=tuple(risk.reason_codes),
    )


def to_four_assessments(bundle: AssessmentBundle) -> FourAssessments:
    return FourAssessments(
        manipulation=ManipulationInput(band=bundle.manipulation.band),
        affordability=AffordabilityInput(
            status=bundle.affordability.status,
            max_supportable_principal_paise=bundle.affordability.max_supportable_principal_paise,
            dsr=bundle.affordability.dsr,
            dsr_ceiling=bundle.affordability.dsr_ceiling,
        ),
        coverage=CoverageInput(
            score=bundle.coverage.score,
            band=bundle.coverage.band,
            missing_sources=tuple(
                MissingSourceInput(source_type=m.source_type, coverage_delta=m.coverage_delta)
                for m in bundle.coverage.missing_sources
            ),
        ),
        risk=_risk_input(bundle.risk),
    )


def loan_request(application: Application, snapshot: FeatureSnapshot) -> LoanRequest:
    return LoanRequest(
        application_id=snapshot.application_id or application.id,
        amount_paise=application.requested_amount_paise or 0,
        tenor_months=application.requested_tenor_months or _DEFAULT_TENOR_MONTHS,
        annual_rate_bps=_DEFAULT_RATE_BPS,
    )


async def run_assessments(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    snapshot: FeatureSnapshot,
    application: Application,
) -> AssessmentBundle:
    """Run all four. If ANY raises, raise :class:`AssessmentFailureError` - no partial result."""
    request = loan_request(application, snapshot)
    requested_terms = RequestedTerms(
        amount_paise=request.amount_paise,
        tenor_months=request.tenor_months,
        annual_rate_bps=request.annual_rate_bps,
    )

    source_evidence = await _load_source_evidence(session, tenant_id, snapshot.applicant_id)
    manipulation_sources = await _load_manipulation_sources(
        session, tenant_id, snapshot.applicant_id
    )
    events = list(
        await session.scalars(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.applicant_id == snapshot.applicant_id,
                LedgerEvent.occurred_at <= snapshot.as_of,
            )
        )
    )

    try:
        risk = assess_risk(snapshot)
    except Exception as exc:
        raise AssessmentFailureError("risk", exc) from exc
    try:
        coverage = assess_coverage(snapshot, source_evidence, COVERAGE_WEIGHTS_VERSION)
    except Exception as exc:
        raise AssessmentFailureError("coverage", exc) from exc
    try:
        affordability = assess_affordability(snapshot, requested_terms)
    except Exception as exc:
        raise AssessmentFailureError("affordability", exc) from exc
    try:
        manipulation = assess_manipulation(
            build_manipulation_context(
                as_of=snapshot.as_of,
                events=[
                    LedgerEventView(
                        event_id=e.id,
                        occurred_at=e.occurred_at,
                        direction=e.direction,
                        amount_paise=e.amount_paise,
                        balance_paise=e.balance_paise,
                        description=e.description,
                        counterparty_hash=e.counterparty_hash,
                        source_snapshot_id=e.source_snapshot_id,
                    )
                    for e in events
                    # A null amount is missing data, not a ₹0 transaction: excluding it
                    # keeps ghost zeros out of the fraud detectors (concentration, bursts).
                    if e.direction is not None and e.amount_paise is not None
                ],
                declared=DeclaredApplication(
                    application_id=application.id,
                    occupation=application.occupation,
                    claimed_period_start=None,
                    claimed_period_end=None,
                ),
                sources=manipulation_sources,
                cross_applicant=[],
            )
        )
    except Exception as exc:
        raise AssessmentFailureError("manipulation", exc) from exc

    return AssessmentBundle(
        risk=risk, coverage=coverage, affordability=affordability, manipulation=manipulation
    )


def build_assessment_rows(
    bundle: AssessmentBundle, *, tenant_id: uuid.UUID, snapshot: FeatureSnapshot
) -> list[object]:
    """Build (but do not add/commit) the four immutable Assessment rows + risk payload."""
    from app.models.assessment import Assessment

    applicant_id = snapshot.applicant_id
    snapshot_id = snapshot.id
    risk_payload = {
        "pd": bundle.risk.pd,
        "calibration_status": bundle.risk.calibration_status,
        "model_version": bundle.risk.model_version,
        "feature_schema_version": bundle.risk.feature_schema_version,
        "contributions": bundle.risk.contributions,
        "reason_codes": list(bundle.risk.reason_codes),
    }
    rows: list[object] = [
        Assessment(
            tenant_id=tenant_id,
            applicant_id=applicant_id,
            feature_snapshot_id=snapshot_id,
            kind=AssessmentKind.RISK,
            payload=risk_payload,
            engine_version=bundle.risk.model_version,
            calibration_status=(
                CalibrationStatus(bundle.risk.calibration_status)
                if bundle.risk.calibration_status in {c.value for c in CalibrationStatus}
                else CalibrationStatus.UNCALIBRATED
            ),
        ),
        Assessment(
            tenant_id=tenant_id,
            applicant_id=applicant_id,
            feature_snapshot_id=snapshot_id,
            kind=AssessmentKind.COVERAGE,
            payload=coverage_payload(bundle.coverage).model_dump(mode="json"),
            engine_version=bundle.coverage.engine_version,
            calibration_status=CalibrationStatus.NOT_APPLICABLE,
        ),
        Assessment(
            tenant_id=tenant_id,
            applicant_id=applicant_id,
            feature_snapshot_id=snapshot_id,
            kind=AssessmentKind.AFFORDABILITY,
            payload=affordability_payload(bundle.affordability).model_dump(mode="json"),
            engine_version=bundle.affordability.engine_version,
            calibration_status=CalibrationStatus.NOT_APPLICABLE,
        ),
        Assessment(
            tenant_id=tenant_id,
            applicant_id=applicant_id,
            feature_snapshot_id=snapshot_id,
            kind=AssessmentKind.MANIPULATION,
            payload=manipulation_payload(bundle.manipulation).model_dump(mode="json"),
            engine_version=bundle.manipulation.engine_version,
            calibration_status=CalibrationStatus.NOT_APPLICABLE,
        ),
    ]
    return rows
