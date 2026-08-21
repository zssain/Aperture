"""Orchestration + weighted-severity banding for the manipulation engine.

``assess`` runs every detector, aggregates their citation-backed findings into an
independent band, and records - separately - which detectors were skipped (UNAVAILABLE, a
detector that raised) and which lacked data (INSUFFICIENT_DATA). A skipped detector is
NEVER treated as a clean one: the band is computed from the remainder and the skips are on
the payload so nobody mistakes a partial run for a clean result.

Banding is by WEIGHTED SEVERITY, not count: any High -> HIGH; two or more Medium ->
ELEVATED; a lone Medium -> ELEVATED only if confident enough, else CLEAR; nothing -> CLEAR.

This service imports no risk / coverage / affordability code, and its only input type,
``ManipulationContext``, cannot carry a PD. HIGH routes to a fraud reviewer - nothing here
declines anyone.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, ManipulationFinding
from app.models.enums import (
    AssessmentKind,
    CalibrationStatus,
    FindingSeverity,
)
from app.schemas.assessment import ManipulationFindingModel, ManipulationPayload
from app.services.classification.rules import INCOME_CATEGORIES
from app.services.classification.service import TxnEvent, classify
from app.services.manipulation.base import Detector, DetectorStatus, Finding
from app.services.manipulation.config import (
    MANIPULATION_CONFIG_VERSION,
    MANIPULATION_ENGINE,
    get_manipulation_config,
)
from app.services.manipulation.context import (
    CrossApplicantSignal,
    DeclaredApplication,
    LedgerEventView,
    ManipulationContext,
    SourceMetadataView,
)
from app.services.manipulation.detectors import (
    d1_circular_flow,
    d2_inflow_burst,
    d3_counterparty_concentration,
    d4_round_number_salary,
    d5_balance_arithmetic,
    d6_document_provenance,
    d7_account_age_mismatch,
    d8_cross_applicant_reuse,
)

# The eight detectors, in a fixed order (determinism, invariant 4).
DETECTORS: tuple[Detector, ...] = (
    d1_circular_flow.DETECTOR,
    d2_inflow_burst.DETECTOR,
    d3_counterparty_concentration.DETECTOR,
    d4_round_number_salary.DETECTOR,
    d5_balance_arithmetic.DETECTOR,
    d6_document_provenance.DETECTOR,
    d7_account_age_mismatch.DETECTOR,
    d8_cross_applicant_reuse.DETECTOR,
)


@dataclass(frozen=True)
class ManipulationAssessment:
    band: str  # HIGH | ELEVATED | CLEAR
    findings: tuple[Finding, ...]
    detector_statuses: dict[str, str]
    skipped: tuple[str, ...]  # detectors that raised -> UNAVAILABLE
    insufficient: tuple[str, ...]  # detectors that lacked data
    trigger_counts: dict[str, int]  # per-detector finding counts (Prompt 17 monitoring)
    config_version: str
    engine_version: str


def band_findings(findings: list[Finding], config_version: str) -> str:
    """Weighted severity: one High outranks any number of Mediums."""
    cfg = get_manipulation_config(config_version)["banding"]
    threshold = float(cfg["single_medium_confidence_threshold"])

    highs = [f for f in findings if f.severity == "HIGH"]
    mediums = [f for f in findings if f.severity == "MEDIUM"]

    if highs:
        return "HIGH"
    if len(mediums) >= 2:
        return "ELEVATED"
    if len(mediums) == 1:
        return "ELEVATED" if mediums[0].confidence > threshold else "CLEAR"
    return "CLEAR"


def build_context(
    *,
    as_of: Any,
    events: list[LedgerEventView],
    declared: DeclaredApplication,
    sources: list[SourceMetadataView],
    cross_applicant: list[CrossApplicantSignal],
    config_version: str = MANIPULATION_CONFIG_VERSION,
) -> ManipulationContext:
    """Assemble the context. Income-event ids come from the deterministic classifier -
    which reads no risk score - so D4 can identify income credits without the service
    depending on the risk engine."""
    txns = [
        TxnEvent(
            event_id=e.event_id,
            occurred_at=e.occurred_at,
            direction=e.direction,
            amount_paise=e.amount_paise,
            balance_paise=e.balance_paise,
            description=e.description,
            counterparty_hash=e.counterparty_hash,
            source_connection_id=None,
        )
        for e in events
    ]
    classified = classify(txns)
    income_ids = frozenset(
        ce.event.event_id for ce in classified.events if ce.category in INCOME_CATEGORIES
    )
    ordered = tuple(sorted(events, key=lambda e: (e.occurred_at, str(e.event_id))))
    return ManipulationContext(
        as_of=as_of,
        events=ordered,
        declared=declared,
        sources=tuple(sources),
        cross_applicant=tuple(cross_applicant),
        income_event_ids=income_ids,
        config_version=config_version,
    )


def assess(
    context: ManipulationContext,
    detectors: tuple[Detector, ...] = DETECTORS,
) -> ManipulationAssessment:
    statuses: dict[str, str] = {}
    counts: dict[str, int] = {}
    skipped: list[str] = []
    insufficient: list[str] = []
    findings: list[Finding] = []

    for detector in detectors:
        detector_id = detector.detector_id
        try:
            result = detector.run(context)
        except Exception:
            statuses[detector_id] = DetectorStatus.UNAVAILABLE.value
            counts[detector_id] = 0
            skipped.append(detector_id)
            continue

        statuses[detector_id] = result.status.value
        counts[detector_id] = len(result.findings)
        if result.status == DetectorStatus.INSUFFICIENT_DATA:
            insufficient.append(detector_id)
        findings.extend(result.findings)

    findings.sort(key=lambda f: (f.detector_id, tuple(str(i) for i in f.cited_event_ids)))
    band = band_findings(findings, context.config_version)

    return ManipulationAssessment(
        band=band,
        findings=tuple(findings),
        detector_statuses=statuses,
        skipped=tuple(skipped),
        insufficient=tuple(insufficient),
        trigger_counts=counts,
        config_version=context.config_version,
        engine_version=f"{MANIPULATION_ENGINE}+{context.config_version}",
    )


_SEVERITY_ENUM = {
    "LOW": FindingSeverity.LOW,
    "MEDIUM": FindingSeverity.MEDIUM,
    "HIGH": FindingSeverity.HIGH,
}


def manipulation_payload(assessment: ManipulationAssessment) -> ManipulationPayload:
    return ManipulationPayload(
        band=assessment.band,
        config_version=assessment.config_version,
        detector_statuses=assessment.detector_statuses,
        skipped=list(assessment.skipped),
        insufficient=list(assessment.insufficient),
        trigger_counts=assessment.trigger_counts,
        findings=[
            ManipulationFindingModel(
                detector_id=f.detector_id,
                severity=f.severity,
                statement=f.statement,
                cited_event_ids=[str(i) for i in f.cited_event_ids],
                confidence=f.confidence,
                values=f.values,
            )
            for f in assessment.findings
        ],
    )


async def persist_manipulation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    applicant_id: uuid.UUID,
    feature_snapshot_id: uuid.UUID,
    assessment: ManipulationAssessment,
) -> Assessment:
    """Store the band as an immutable assessment row plus one manipulation_finding row per
    finding (citation-backed, for the fraud reviewer). No risk score is read or written."""
    row = Assessment(
        tenant_id=tenant_id,
        applicant_id=applicant_id,
        feature_snapshot_id=feature_snapshot_id,
        kind=AssessmentKind.MANIPULATION,
        payload=manipulation_payload(assessment).model_dump(mode="json"),
        engine_version=assessment.engine_version,
        calibration_status=CalibrationStatus.NOT_APPLICABLE,
    )
    session.add(row)
    await session.flush()

    for finding in assessment.findings:
        session.add(
            ManipulationFinding(
                tenant_id=tenant_id,
                assessment_id=row.id,
                applicant_id=applicant_id,
                code=finding.detector_id,
                severity=_SEVERITY_ENUM[finding.severity],
                detail={
                    "statement": finding.statement,
                    "cited_event_ids": [str(i) for i in finding.cited_event_ids],
                    "confidence": finding.confidence,
                    "values": finding.values,
                },
            )
        )
    await session.commit()
    return row


__all__ = [
    "DETECTORS",
    "ManipulationAssessment",
    "assess",
    "band_findings",
    "build_context",
    "manipulation_payload",
    "persist_manipulation",
]
