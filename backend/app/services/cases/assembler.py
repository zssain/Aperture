"""Assemble the case file from the durable record - plus the two things that make it a
workspace rather than a report: the ``blocking_tab`` the screen opens on, and the bureau-only
counterfactual.

- ``blocking_tab`` is derived from the FIRST gate that fired: the analyst opens on exactly the
  question the policy could not answer automatically.
- ``bureau_only`` evaluates the LIVE policy against the same snapshot with the cash-flow
  features masked, leaving only bureau signals - so the screen can show what a bureau-only
  lender would have done to this thin-file borrower.

Evidence and lineage live here too. Evidence pages are keyset-paginated in SQL (the client
never receives the whole ledger); lineage recomputes the feature from its cited events so
traceability is a fact the endpoint can prove, not a claim.
"""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.applicant import Applicant
from app.models.application import Application
from app.models.assessment import Assessment
from app.models.consent import Consent
from app.models.decision import Decision, DecisionReason, HumanReview, RecourseOption
from app.models.enums import AssessmentKind, ReviewStatus, SourceType
from app.models.feature import FeatureSnapshot
from app.models.ledger import LedgerEvent
from app.models.policy import PolicyVersion
from app.models.source import SourceConnection, SourceSnapshot
from app.schemas.case import (
    AffordabilityChip,
    ApplicantOut,
    ApplicationOut,
    AssessmentChipsOut,
    AssessmentOut,
    CaseOut,
    CitedEventOut,
    CounterfactualOut,
    CoverageChip,
    DecisionOut,
    EvidenceEventOut,
    EvidencePage,
    LineageOut,
    ManipulationFindingOut,
    ReasonOut,
    RecourseOptionOut,
    ReviewOut,
    SourceOut,
    StaleOut,
)
from app.schemas.queue import MetricOut
from app.services.affordability.service import RequestedTerms, assess_affordability
from app.services.classification.service import classify
from app.services.coverage.service import SourceEvidence, assess_coverage
from app.services.coverage.weights import COVERAGE_WEIGHTS_VERSION
from app.services.features.registry import REGISTRY, FeatureContext
from app.services.features.service import _to_txn
from app.services.orchestrator.assessments import loan_request
from app.services.policy.schema import (
    AffordabilityInput,
    CoverageInput,
    FourAssessments,
    ManipulationInput,
    MissingSourceInput,
    RiskInput,
)
from app.services.risk.service import RiskError, assess_risk

# The three bureau signals; everything else in features-v1 is cash-flow derived.
BUREAU_FEATURES: frozenset[str] = frozenset(
    {"bureau_score", "bureau_active_loans", "bureau_delinquencies_12m"}
)

_REGISTRY_BY_KEY = {spec.key: spec for spec in REGISTRY}

# Which tab answers each gate's question. The case opens here.
TAB_EVIDENCE = "evidence"
TAB_ASSESSMENT = "assessment"
TAB_VERIFICATION = "verification"
TAB_RECOURSE = "recourse"
TAB_DECISION = "decision"

_BLOCKING_TAB_BY_GATE: dict[str, str] = {
    "manipulation_high": TAB_VERIFICATION,
    "manipulation_elevated": TAB_VERIFICATION,
    "affordability_fail": TAB_ASSESSMENT,
    "affordability_indeterminate": TAB_ASSESSMENT,
    "coverage_below_min": TAB_EVIDENCE,
    "pd_decline": TAB_ASSESSMENT,
    "approve_enhanced": TAB_DECISION,
    "approve_standard": TAB_DECISION,
    "approve_starter": TAB_DECISION,
}

_DEFAULT_EVIDENCE_LIMIT = 50
_MAX_EVIDENCE_LIMIT = 200


class CaseNotFoundError(Exception):
    """The case does not exist for this tenant -> 404 (cross-tenant is a 404, never a 403)."""


# --------------------------------------------------------------------------- #
# blocking_tab
# --------------------------------------------------------------------------- #
def blocking_tab_for(fired_rules: list[dict[str, Any]], has_decision: bool) -> str:
    if not has_decision:
        # No decision (an assessment was unavailable) -> the work starts at the evidence.
        return TAB_EVIDENCE
    gate: dict[str, Any] | None = None
    mandatory = False
    for rule in fired_rules:
        number = int(rule.get("number", 0))
        if 1 <= number <= 9 and gate is None:
            gate = rule
        elif number == 10:
            mandatory = True
    if mandatory:
        return TAB_DECISION
    if gate is None:
        return TAB_EVIDENCE
    return _BLOCKING_TAB_BY_GATE.get(str(gate.get("name", "")), TAB_DECISION)


# --------------------------------------------------------------------------- #
# Case assembly
# --------------------------------------------------------------------------- #
async def _latest_decision(
    session: AsyncSession, tenant_id: uuid.UUID, application_id: uuid.UUID
) -> Decision | None:
    stmt = (
        select(Decision)
        .where(
            Decision.tenant_id == tenant_id,
            Decision.application_id == application_id,
            Decision.superseded_by.is_(None),
        )
        .order_by(Decision.decided_at.desc())
        .limit(1)
    )
    decision: Decision | None = await session.scalar(stmt)
    return decision


async def _assessments_for(
    session: AsyncSession, tenant_id: uuid.UUID, snapshot_id: uuid.UUID
) -> dict[str, Assessment]:
    stmt = select(Assessment).where(
        Assessment.tenant_id == tenant_id,
        Assessment.feature_snapshot_id == snapshot_id,
    )
    return {row.kind.value: row for row in await session.scalars(stmt)}


def _assessment_out(row: Assessment) -> AssessmentOut:
    payload = dict(row.payload or {})
    return AssessmentOut(
        kind=row.kind.value,
        engine_version=row.engine_version,
        model_version=payload.get("model_version"),
        calibration_status=row.calibration_status.value,
        payload=payload,
    )


def _pd_metric(payload: dict[str, Any] | None) -> MetricOut:
    if not payload or payload.get("pd") is None:
        return MetricOut(value=None, status="unavailable")
    calibration = str(payload.get("calibration_status", ""))
    status = "uncalibrated" if calibration == "UNCALIBRATED" else "measured"
    return MetricOut(value=float(payload["pd"]), status=status)


def _chips(assessments: dict[str, Assessment]) -> AssessmentChipsOut:
    risk = assessments.get(AssessmentKind.RISK.value)
    coverage = assessments.get(AssessmentKind.COVERAGE.value)
    afford = assessments.get(AssessmentKind.AFFORDABILITY.value)
    manip = assessments.get(AssessmentKind.MANIPULATION.value)

    cov_payload = dict(coverage.payload) if coverage else {}
    afford_payload = dict(afford.payload) if afford else {}
    return AssessmentChipsOut(
        pd=_pd_metric(dict(risk.payload) if risk else None),
        coverage=CoverageChip(
            score=cov_payload.get("score"),
            band=cov_payload.get("band"),
            status="measured" if coverage else "unavailable",
        ),
        affordability=AffordabilityChip(
            status=str(afford_payload.get("status", "UNAVAILABLE")) if afford else "UNAVAILABLE",
            headroom_paise=afford_payload.get("disposable_income_paise") if afford else None,
        ),
        verification=(
            str(dict(manip.payload).get("band", "UNAVAILABLE")) if manip else "UNAVAILABLE"
        ),
    )


async def _manipulation_findings(
    session: AsyncSession, tenant_id: uuid.UUID, manip: Assessment | None
) -> list[ManipulationFindingOut]:
    if manip is None:
        return []
    findings = dict(manip.payload).get("findings", [])

    # Resolve every cited event once, so a finding can expand to its rows inline in the UI.
    cited_ids: set[uuid.UUID] = set()
    for f in findings:
        for raw in f.get("cited_event_ids", []):
            try:
                cited_ids.add(uuid.UUID(str(raw)))
            except ValueError:
                continue
    events_by_id: dict[str, LedgerEvent] = {}
    if cited_ids:
        rows = await session.scalars(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.id.in_(cited_ids),
            )
        )
        events_by_id = {str(e.id): e for e in rows}

    out: list[ManipulationFindingOut] = []
    for f in findings:
        ids = [str(i) for i in f.get("cited_event_ids", [])]
        cited_events = [
            CitedEventOut(
                id=event.id,
                occurred_at=event.occurred_at,
                direction=event.direction.value if event.direction else None,
                amount_paise=event.amount_paise,
                balance_paise=event.balance_paise,
                description=event.description,
            )
            for event_id in ids
            if (event := events_by_id.get(event_id)) is not None
        ]
        out.append(
            ManipulationFindingOut(
                detector_id=str(f.get("detector_id", "")),
                severity=str(f.get("severity", "")),
                statement=str(f.get("statement", "")),
                cited_event_ids=ids,
                confidence=float(f.get("confidence", 0.0)),
                values=dict(f.get("values", {})),
                cited_events=cited_events,
            )
        )
    return out


async def _sources(
    session: AsyncSession, tenant_id: uuid.UUID, applicant_id: uuid.UUID, now: datetime
) -> list[SourceOut]:
    conn_stmt = select(SourceConnection).where(
        SourceConnection.tenant_id == tenant_id,
        SourceConnection.applicant_id == applicant_id,
    )
    connections = list(await session.scalars(conn_stmt))
    out: list[SourceOut] = []
    for conn in connections:
        latest = await session.scalar(
            select(SourceSnapshot)
            .where(
                SourceSnapshot.tenant_id == tenant_id,
                SourceSnapshot.source_connection_id == conn.id,
            )
            .order_by(SourceSnapshot.fetched_at.desc())
            .limit(1)
        )
        fetched_at = latest.fetched_at if latest else None
        freshness = (now - fetched_at).days if fetched_at else None
        effective_tier = (latest.tier if latest else None) or conn.tier
        out.append(
            SourceOut(
                id=conn.id,
                source_type=conn.source_type.value,
                tier=effective_tier.value if effective_tier is not None else None,
                status=conn.status.value,
                provider=conn.provider,
                period_start=latest.period_start if latest else None,
                period_end=latest.period_end if latest else None,
                last_sync_at=fetched_at,
                freshness_days=freshness,
            )
        )
    return out


async def _reviews(
    session: AsyncSession, tenant_id: uuid.UUID, application_id: uuid.UUID
) -> list[ReviewOut]:
    stmt = (
        select(HumanReview)
        .where(
            HumanReview.tenant_id == tenant_id,
            HumanReview.application_id == application_id,
        )
        .order_by(HumanReview.created_at.asc())
    )
    return [
        ReviewOut(
            id=r.id,
            queue=r.queue,
            status=r.status.value,
            outcome=r.outcome.value if r.outcome else None,
            reason_code=r.reason_code,
            reason_text=r.reason_text,
            assigned_at=r.assigned_at,
            resolved_at=r.resolved_at,
        )
        for r in await session.scalars(stmt)
    ]


async def _recourse(
    session: AsyncSession, tenant_id: uuid.UUID, decision_id: uuid.UUID
) -> list[RecourseOptionOut]:
    stmt = (
        select(RecourseOption)
        .where(
            RecourseOption.tenant_id == tenant_id,
            RecourseOption.decision_id == decision_id,
        )
        .order_by(RecourseOption.rank.asc())
    )
    return [
        RecourseOptionOut(
            rank=r.rank,
            description=r.description,
            required_change=dict(r.required_change or {}),
            projected_action=r.projected_action.value if r.projected_action else None,
            projected_limit_paise=r.projected_limit_paise,
            verified=r.verified,
        )
        for r in await session.scalars(stmt)
    ]


async def _decision_out(
    session: AsyncSession, tenant_id: uuid.UUID, decision: Decision
) -> DecisionOut:
    reasons = list(
        await session.scalars(
            select(DecisionReason).where(
                DecisionReason.tenant_id == tenant_id,
                DecisionReason.decision_id == decision.id,
            )
        )
    )
    reason_out = [
        ReasonOut(
            code=r.code,
            message=r.message,
            polarity=str((r.detail or {}).get("polarity", "NEUTRAL")),
            template_params=dict((r.detail or {}).get("template_params", {})),
            order=int((r.detail or {}).get("order", 0)),
        )
        for r in reasons
    ]
    reason_out.sort(key=lambda r: r.order)
    fired = [dict(rule) for rule in (decision.fired_rules or [])]
    outcome = _outcome_hint(fired, decision.action.value)
    policy = await session.get(PolicyVersion, decision.policy_version_id)
    resolved = await session.scalar(
        select(HumanReview.id).where(
            HumanReview.tenant_id == tenant_id,
            HumanReview.decision_id == decision.id,
            HumanReview.status == ReviewStatus.RESOLVED,
        )
    )
    return DecisionOut(
        id=decision.id,
        action=decision.action.value,
        routing=decision.routing,
        outcome=outcome,
        policy_version=str(policy.version) if policy else None,
        approved_limit_paise=decision.approved_limit_paise,
        terms=dict(decision.terms or {}),
        fired_rules=fired,
        exploration_cohort=decision.exploration_cohort,
        is_final=decision.is_final,
        decided_at=decision.decided_at,
        reasons=reason_out,
        resolved=resolved is not None,
    )


def _outcome_hint(fired_rules: list[dict[str, Any]], fallback: str) -> str:
    for rule in reversed(fired_rules):
        if rule.get("outcome"):
            return str(rule["outcome"])
    return fallback


async def _consent_status(
    session: AsyncSession, tenant_id: uuid.UUID, applicant_id: uuid.UUID
) -> str | None:
    consent = await session.scalar(
        select(Consent)
        .where(Consent.tenant_id == tenant_id, Consent.applicant_id == applicant_id)
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    return consent.status.value if consent else None


async def _stale(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    applicant_id: uuid.UUID,
    decision: Decision | None,
) -> StaleOut:
    if decision is None:
        return StaleOut(is_stale=False, new_event_count=0)
    # New evidence learned AFTER this decision was made (never silently mix vintages).
    new_ids = list(
        await session.scalars(
            select(LedgerEvent.id).where(
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.applicant_id == applicant_id,
                LedgerEvent.received_at > decision.decided_at,
            )
        )
    )
    return StaleOut(is_stale=bool(new_ids), new_event_count=len(new_ids))


async def assemble_case(
    session: AsyncSession, tenant_id: uuid.UUID, application_id: uuid.UUID
) -> CaseOut:
    application = await session.get(Application, application_id)
    if application is None or application.tenant_id != tenant_id:
        raise CaseNotFoundError(str(application_id))
    applicant = await session.get(Applicant, application.applicant_id)
    if applicant is None:
        raise CaseNotFoundError(str(application_id))

    now = datetime.now(UTC)
    decision = await _latest_decision(session, tenant_id, application_id)

    snapshot_id = decision.feature_snapshot_id if decision else None
    if snapshot_id is None:
        latest_snapshot = await session.scalar(
            select(FeatureSnapshot)
            .where(
                FeatureSnapshot.tenant_id == tenant_id,
                FeatureSnapshot.application_id == application_id,
            )
            .order_by(FeatureSnapshot.as_of.desc())
            .limit(1)
        )
        snapshot_id = latest_snapshot.id if latest_snapshot else None

    assessments = await _assessments_for(session, tenant_id, snapshot_id) if snapshot_id else {}
    assessment_failed = len(assessments) < 4

    manip = assessments.get(AssessmentKind.MANIPULATION.value)
    decision_out = await _decision_out(session, tenant_id, decision) if decision else None
    recourse = await _recourse(session, tenant_id, decision.id) if decision else []

    bureau_only = await _bureau_only(session, tenant_id, application, decision)

    return CaseOut(
        application=ApplicationOut(
            id=application.id,
            status=application.status.value,
            product=application.product,
            requested_amount_paise=application.requested_amount_paise,
            requested_tenor_months=application.requested_tenor_months,
            created_at=application.created_at,
        ),
        applicant=ApplicantOut(
            id=applicant.id,
            external_ref=applicant.external_ref,
            display_name=applicant.display_name,
            phone=applicant.phone,
        ),
        case_age_seconds=int((now - application.created_at).total_seconds()),
        consent_status=await _consent_status(session, tenant_id, applicant.id),
        stale=await _stale(session, tenant_id, applicant.id, decision),
        feature_snapshot_id=snapshot_id,
        sources=await _sources(session, tenant_id, applicant.id, now),
        decision=decision_out,
        assessments={k: _assessment_out(v) for k, v in assessments.items()},
        assessment_failed=assessment_failed,
        chips=_chips(assessments),
        manipulation_findings=await _manipulation_findings(session, tenant_id, manip),
        recourse=recourse,
        reviews=await _reviews(session, tenant_id, application_id),
        blocking_tab=blocking_tab_for(
            decision_out.fired_rules if decision_out else [], decision is not None
        ),
        bureau_only=bureau_only,
    )


# --------------------------------------------------------------------------- #
# Bureau-only counterfactual
# --------------------------------------------------------------------------- #
def _masked_snapshot(snapshot: FeatureSnapshot) -> FeatureSnapshot:
    kept = {k: v for k, v in (snapshot.values or {}).items() if k in BUREAU_FEATURES}
    masked_null = {
        k: (snapshot.null_map or {}).get(k) or "bureau_only_mask"
        for k in (snapshot.values or {})
        if k not in BUREAU_FEATURES
    }
    null_map = {**(snapshot.null_map or {}), **masked_null}
    return FeatureSnapshot(
        tenant_id=snapshot.tenant_id,
        applicant_id=snapshot.applicant_id,
        application_id=snapshot.application_id,
        as_of=snapshot.as_of,
        schema_version=snapshot.schema_version,
        values=kept,
        null_map=null_map,
        lineage=snapshot.lineage,
        input_hash=snapshot.input_hash,
    )


async def _bureau_only(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    application: Application,
    decision: Decision | None,
) -> CounterfactualOut:
    from app.services.policy.engine import evaluate
    from app.services.policy.schema import PolicyOutcome, PolicyRules

    if decision is None:
        return CounterfactualOut(
            available=False,
            outcome="SYSTEM_UNAVAILABLE",
            action=None,
            note="No decision to compare against.",
        )
    snapshot = await session.get(FeatureSnapshot, decision.feature_snapshot_id)
    policy_row = await session.get(PolicyVersion, decision.policy_version_id)
    if snapshot is None or policy_row is None:
        return CounterfactualOut(
            available=False,
            outcome="SYSTEM_UNAVAILABLE",
            action=None,
            note="Stored snapshot or policy missing.",
        )

    masked = _masked_snapshot(snapshot)
    has_bureau = bool(masked.values)

    # Risk without cash-flow features: the cash-flow scorecard cannot score -> no PD.
    pd: float | None = None
    try:
        pd = assess_risk(masked).pd
    except RiskError:
        pd = None

    # Coverage from bureau sources only.
    bureau_evidence = await _bureau_source_evidence(session, tenant_id, snapshot.applicant_id)
    coverage = assess_coverage(masked, bureau_evidence, COVERAGE_WEIGHTS_VERSION)
    affordability = assess_affordability(masked, _requested_terms(application, snapshot))

    four = FourAssessments(
        manipulation=ManipulationInput(band="CLEAR"),
        affordability=AffordabilityInput(
            status=affordability.status,
            max_supportable_principal_paise=affordability.max_supportable_principal_paise,
            dsr=affordability.dsr,
            dsr_ceiling=affordability.dsr_ceiling,
        ),
        coverage=CoverageInput(
            score=coverage.score,
            band=coverage.band,
            missing_sources=tuple(
                MissingSourceInput(source_type=m.source_type, coverage_delta=m.coverage_delta)
                for m in coverage.missing_sources
            ),
        ),
        risk=RiskInput(pd=pd, calibration_status="UNCALIBRATED"),
    )
    result = evaluate(four, loan_request(application, snapshot), PolicyRules(**policy_row.rules))
    outcome = result.outcome
    action_enum = None
    if outcome in {o.value for o in PolicyOutcome}:
        from app.services.orchestrator.service import OUTCOME_TO_ACTION

        action_enum = OUTCOME_TO_ACTION.get(PolicyOutcome(outcome))
    note = (
        "A bureau-only lender lacks the cash-flow evidence that carried this decision."
        if not has_bureau
        else f"Bureau-only signals resolve to {outcome}."
    )
    return CounterfactualOut(
        available=has_bureau,
        outcome=outcome,
        action=action_enum.value if action_enum else None,
        note=note,
    )


def _requested_terms(application: Application, snapshot: FeatureSnapshot) -> RequestedTerms:
    request = loan_request(application, snapshot)
    return RequestedTerms(
        amount_paise=request.amount_paise,
        tenor_months=request.tenor_months,
        annual_rate_bps=request.annual_rate_bps,
    )


async def _bureau_source_evidence(
    session: AsyncSession, tenant_id: uuid.UUID, applicant_id: uuid.UUID
) -> list[SourceEvidence]:
    stmt = (
        select(SourceSnapshot, SourceConnection)
        .join(SourceConnection, SourceSnapshot.source_connection_id == SourceConnection.id)
        .where(
            SourceSnapshot.tenant_id == tenant_id,
            SourceSnapshot.applicant_id == applicant_id,
            SourceConnection.source_type == SourceType.BUREAU,
        )
    )
    evidence: list[SourceEvidence] = []
    for snapshot, connection in await session.execute(stmt):
        tier = snapshot.tier or connection.tier
        if tier is None:
            continue
        evidence.append(
            SourceEvidence(
                source_type=SourceType.BUREAU,
                tier=tier,
                latest_event_at=snapshot.period_end or snapshot.fetched_at,
            )
        )
    return evidence


# --------------------------------------------------------------------------- #
# Evidence pagination (server-side keyset over classified events)
# --------------------------------------------------------------------------- #
def _encode_cursor(occurred_at: datetime, event_id: uuid.UUID) -> str:
    raw = {"t": occurred_at.isoformat(), "id": str(event_id)}
    return base64.urlsafe_b64encode(json.dumps(raw).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(str(raw["t"])), uuid.UUID(str(raw["id"]))
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError):
        return None


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_EVIDENCE_LIMIT
    return max(1, min(limit, _MAX_EVIDENCE_LIMIT))


async def list_evidence(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    application_id: uuid.UUID,
    *,
    category: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> EvidencePage:
    application = await session.get(Application, application_id)
    if application is None or application.tenant_id != tenant_id:
        raise CaseNotFoundError(str(application_id))
    applicant_id = application.applicant_id
    page_size = _clamp_limit(limit)

    # Classification needs the applicant's full event context (recurrence/transfer look at
    # neighbours); classify once, then use it to resolve category + the per-event label.
    all_events = list(
        await session.scalars(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.applicant_id == applicant_id,
            )
        )
    )
    classified = classify([_to_txn(e) for e in all_events]).events
    category_by_id = {str(c.event.event_id): (c.category.value, c.confidence) for c in classified}
    trace_by_id = {str(c.event.event_id): c for c in classified}

    stmt: Select[Any] = select(LedgerEvent).where(
        LedgerEvent.tenant_id == tenant_id,
        LedgerEvent.applicant_id == applicant_id,
    )
    if from_ts is not None:
        stmt = stmt.where(LedgerEvent.occurred_at >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(LedgerEvent.occurred_at <= to_ts)
    if category is not None:
        matching = [
            uuid.UUID(event_id)
            for event_id, (cat, _) in category_by_id.items()
            if cat == category.upper()
        ]
        # A category with no members must return nothing, not everything.
        stmt = stmt.where(LedgerEvent.id.in_(matching or [uuid.UUID(int=0)]))
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded is not None:
            bound_ts, bound_id = decoded
            stmt = stmt.where(
                or_(
                    LedgerEvent.occurred_at < bound_ts,
                    and_(LedgerEvent.occurred_at == bound_ts, LedgerEvent.id < bound_id),
                )
            )
    stmt = stmt.order_by(LedgerEvent.occurred_at.desc(), LedgerEvent.id.desc()).limit(page_size + 1)

    events = list(await session.scalars(stmt))
    has_next = len(events) > page_size
    page = events[:page_size]

    rows: list[EvidenceEventOut] = []
    for event in page:
        trace = trace_by_id[str(event.id)]
        rows.append(
            EvidenceEventOut(
                id=event.id,
                occurred_at=event.occurred_at,
                direction=event.direction.value if event.direction else None,
                amount_paise=event.amount_paise,
                balance_paise=event.balance_paise,
                description=event.description,
                category=category_by_id.get(str(event.id), ("OTHER", 0.0))[0],
                confidence=category_by_id.get(str(event.id), ("OTHER", 0.0))[1],
                classification_method=trace.classification_method.value,
                classifier_version=event.classifier_version,
                catalog_version_id=trace.catalog_version_id,
                matched_entry_id=trace.matched_entry_id,
                match_similarity=trace.match_similarity,
            )
        )
    next_cursor = _encode_cursor(page[-1].occurred_at, page[-1].id) if has_next and page else None
    return EvidencePage(rows=rows, next_cursor=next_cursor)


# --------------------------------------------------------------------------- #
# Feature lineage - recomputed from the cited events, so traceability is provable.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _LineageInputs:
    snapshot: FeatureSnapshot
    spec: Any


async def get_lineage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    feature_key: str,
) -> LineageOut:
    snapshot = await session.get(FeatureSnapshot, snapshot_id)
    if snapshot is None or snapshot.tenant_id != tenant_id:
        raise CaseNotFoundError(str(snapshot_id))
    spec = _REGISTRY_BY_KEY.get(feature_key)
    if spec is None:
        raise CaseNotFoundError(feature_key)

    lineage_entry = dict((snapshot.lineage or {}).get(feature_key, {}))
    contributing_ids = [str(i) for i in lineage_entry.get("events", [])]
    value = (snapshot.values or {}).get(feature_key)
    null_reason = (snapshot.null_map or {}).get(feature_key)

    recomputed = await _recompute(session, tenant_id, snapshot, spec, contributing_ids)
    matches = _values_match(value, recomputed)

    return LineageOut(
        feature_key=feature_key,
        version=spec.version,
        dtype=spec.dtype,
        window=spec.window,
        formula_doc=spec.formula_doc,
        null_policy=spec.null_policy,
        monotonic_direction=spec.monotonic_direction,
        value=float(value) if value is not None else None,
        null_reason=null_reason,
        contributing_event_ids=contributing_ids,
        recomputed_value=float(recomputed) if recomputed is not None else None,
        matches=matches,
    )


async def _recompute(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    snapshot: FeatureSnapshot,
    spec: Any,
    contributing_ids: list[str],
) -> float | int | None:
    if not contributing_ids:
        # No cited events: recompute over an empty context so a "0 for zero events" feature
        # (e.g. history_depth) still reproduces, and a null feature stays null.
        empty_result = spec.compute(FeatureContext(as_of=snapshot.as_of, events=[]))
        empty_value: float | int | None = empty_result.value
        return empty_value
    ids = [uuid.UUID(i) for i in contributing_ids]
    events = list(
        await session.scalars(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.id.in_(ids),
            )
        )
    )
    classified = classify([_to_txn(e) for e in events]).events
    result = spec.compute(FeatureContext(as_of=snapshot.as_of, events=list(classified)))
    value: float | int | None = result.value
    return value


def _values_match(stored: Any, recomputed: float | int | None) -> bool:
    if stored is None or recomputed is None:
        return stored is None and recomputed is None
    return abs(float(stored) - float(recomputed)) < 1e-6
