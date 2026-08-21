"""Re-decision supersession, change specificity, failure safety and demo flow."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.api.routes.decisions import decision_history, get_decision
from app.api.routes.demo import generate_income_consistency_demo
from app.core.config import settings
from app.jobs.redecide import handle_redecide
from app.models.assessment import Assessment
from app.models.change import DecisionChange, RedecisionAlert
from app.models.consent import Consent
from app.models.decision import Decision, HumanReview
from app.models.enums import (
    AssessmentKind,
    CalibrationStatus,
    ConsentStatus,
    DecisionAction,
    EventDirection,
    EvidenceEventType,
    JobStatus,
    JobType,
    ReviewOutcome,
    ReviewStatus,
    SourceType,
)
from app.models.feature import FeatureSnapshot
from app.models.job import Job
from app.models.ledger import LedgerEvent
from app.models.source import SourceConnection
from app.schemas.event import DemoIncomeConsistencyRequest
from app.services.decisions.change_detector import detect_change
from app.services.demo.event_generator import income_consistency_sequence
from app.services.events.service import ingest_event
from app.services.orchestrator.service import decide
from app.services.policy.defaults import seed_policy_v1
from app.services.queue.service import list_queue
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.decision_fixtures import (
    AS_OF,
    Decidable,
    build_decidable,
    publish_rules,
    publish_seed,
)


async def _initial(session: AsyncSession) -> tuple[Decidable, Decision]:
    d = await build_decidable(session)
    await publish_seed(session, d)
    result = await decide(
        session,
        d.context,
        application_id=d.application.id,
        as_of=AS_OF,
        idempotency_key=f"initial:{uuid.uuid4()}",
        generate_recourse=False,
    )
    return d, result.decision


async def _job(session: AsyncSession, d: Decidable, as_of: datetime) -> Job:
    job = Job(
        tenant_id=d.tenant_id,
        job_type=JobType.REDECISION,
        status=JobStatus.RUNNING,
        payload={
            "handler": "redecide",
            "application_id": str(d.application.id),
            "applicant_id": str(d.applicant.id),
            "event_ids": [],
            "as_of": as_of.isoformat(),
            "user_id": str(d.user_id),
        },
    )
    session.add(job)
    await session.commit()
    return job


async def test_change_record_has_exact_deltas_named_feature_and_queue_view(
    db_session: AsyncSession,
) -> None:
    d, previous = await _initial(db_session)
    old_snapshot = await db_session.get(FeatureSnapshot, previous.feature_snapshot_id)
    assert old_snapshot is not None
    # Create a successor with one known feature move. The standing real decision
    # remains the previous side of the comparison.
    values = dict(old_snapshot.values)
    before_cv = float(values.get("monthly_inflow_cv") or 0.0)
    values["monthly_inflow_cv"] = before_cv + 0.4
    snapshot = FeatureSnapshot(
        tenant_id=d.tenant_id,
        applicant_id=d.applicant.id,
        application_id=d.application.id,
        as_of=AS_OF + timedelta(days=1),
        schema_version=old_snapshot.schema_version,
        values=values,
        null_map=dict(old_snapshot.null_map),
        input_hash=uuid.uuid4().hex,
    )
    db_session.add(snapshot)
    await db_session.flush()
    db_session.add_all(
        [
            Assessment(
                tenant_id=d.tenant_id,
                applicant_id=d.applicant.id,
                feature_snapshot_id=snapshot.id,
                kind=AssessmentKind.RISK,
                payload={"pd": 0.42},
                engine_version="test",
                calibration_status=CalibrationStatus.UNCALIBRATED,
            ),
            Assessment(
                tenant_id=d.tenant_id,
                applicant_id=d.applicant.id,
                feature_snapshot_id=snapshot.id,
                kind=AssessmentKind.COVERAGE,
                payload={"score": 88},
                engine_version="test",
                calibration_status=CalibrationStatus.NOT_APPLICABLE,
            ),
        ]
    )
    successor = Decision(
        tenant_id=d.tenant_id,
        application_id=d.application.id,
        applicant_id=d.applicant.id,
        feature_snapshot_id=snapshot.id,
        policy_version_id=previous.policy_version_id,
        action=DecisionAction.DECLINE,
        routing="AUTOMATED",
        idempotency_key=f"manual-successor:{uuid.uuid4()}",
        is_final=True,
        terms={},
        fired_rules=[{"number": 7, "name": "pd_decline", "outcome": "DECLINE_RISK"}],
    )
    db_session.add(successor)
    await db_session.flush()
    previous.superseded_by = successor.id
    await db_session.commit()

    change = await detect_change(
        db_session,
        d.context,
        previous=previous,
        new=successor,
        human_action_protected=False,
    )
    old_risk = await db_session.scalar(
        select(Assessment).where(
            Assessment.feature_snapshot_id == previous.feature_snapshot_id,
            Assessment.kind == AssessmentKind.RISK,
        )
    )
    assert old_risk is not None
    assert float(change.pd_delta or 0) == pytest.approx(0.42 - float(old_risk.payload["pd"]))
    moved = {item["feature_key"]: item for item in change.feature_changes}
    assert moved["monthly_inflow_cv"]["label"] == "Income consistency"
    assert moved["monthly_inflow_cv"]["before"] == pytest.approx(before_cv)
    assert moved["monthly_inflow_cv"]["after"] == pytest.approx(before_cv + 0.4)
    queue = await list_queue(db_session, d.tenant_id, "CREDIT_ANALYST", view="deterioration")
    assert [row.id for row in queue.rows] == [successor.id]
    assert queue.rows[0].change is not None
    assert queue.rows[0].change.previous_band in {"STARTER", "STANDARD", "ENHANCED"}
    assert queue.rows[0].change.new_band == "DECLINE"


async def test_redecision_creates_new_snapshot_supersedes_and_keeps_both_readable(
    db_session: AsyncSession,
) -> None:
    d, previous = await _initial(db_session)
    job = await _job(db_session, d, AS_OF + timedelta(days=1))
    result = await handle_redecide(db_session, job, d.context)
    assert result["status"] in {"CHANGED", "UNCHANGED"}
    new = await db_session.get(Decision, uuid.UUID(result["decision_id"]))
    await db_session.refresh(previous)
    assert new is not None
    assert previous.superseded_by == new.id
    assert new.feature_snapshot_id != previous.feature_snapshot_id
    assert await db_session.get(Decision, previous.id) is not None
    assert await db_session.get(Decision, new.id) is not None
    assert (await get_decision(previous.id, d.context, db_session)).id == previous.id
    assert (await get_decision(new.id, d.context, db_session)).id == new.id
    history = await decision_history(d.application.id, d.context, db_session)
    assert {row.id for row in history} == {previous.id, new.id}
    assessments = await db_session.scalar(
        select(func.count())
        .select_from(Assessment)
        .where(Assessment.feature_snapshot_id == new.feature_snapshot_id)
    )
    assert assessments == 4


async def test_failure_keeps_previous_intact_and_persists_alert(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, previous = await _initial(db_session)
    job = await _job(db_session, d, AS_OF + timedelta(days=1))
    job_id = job.id

    async def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("feature engine unavailable")

    monkeypatch.setattr("app.jobs.redecide.decide", fail)
    result = await handle_redecide(db_session, job, d.context)
    assert result["status"] == "FAILED_SAFE"
    await db_session.refresh(previous)
    assert previous.superseded_by is None
    alert = await db_session.scalar(select(RedecisionAlert).where(RedecisionAlert.job_id == job_id))
    assert alert is not None
    assert alert.previous_decision_id == previous.id


async def test_human_finalization_is_not_overwritten_and_change_is_surfaced(
    db_session: AsyncSession,
) -> None:
    d, previous = await _initial(db_session)
    review = HumanReview(
        tenant_id=d.tenant_id,
        application_id=d.application.id,
        decision_id=previous.id,
        reviewer_id=d.user_id,
        status=ReviewStatus.RESOLVED,
        outcome=ReviewOutcome.APPROVED,
        reason_code="MANUAL_FINAL",
        reason_text="Verified by analyst",
        resolved_at=datetime.now(UTC),
    )
    db_session.add(review)
    await db_session.commit()
    job = await _job(db_session, d, AS_OF + timedelta(days=1))
    result = await handle_redecide(db_session, job, d.context)
    assert result["human_action_protected"] is True
    await db_session.refresh(review)
    assert review.status == ReviewStatus.RESOLVED
    assert review.outcome == ReviewOutcome.APPROVED
    assert review.decision_id == previous.id
    change = await db_session.get(DecisionChange, uuid.UUID(result["change_id"]))
    assert change is not None and change.human_action_protected is True
    review_on_new = await db_session.scalar(
        select(HumanReview).where(HumanReview.decision_id == uuid.UUID(result["decision_id"]))
    )
    assert review_on_new is None


async def test_demo_generator_uses_real_event_and_feature_engines(
    db_session: AsyncSession,
) -> None:
    d = await build_decidable(db_session)
    connection = await db_session.scalar(
        select(SourceConnection).where(SourceConnection.applicant_id == d.applicant.id)
    )
    assert connection is not None
    # An uneven historic business stream creates a real high income-CV starting point.
    for index, days in enumerate((178, 148, 118)):
        db_session.add(
            LedgerEvent(
                tenant_id=d.tenant_id,
                applicant_id=d.applicant.id,
                source_connection_id=connection.id,
                event_type=EvidenceEventType.TRANSACTION,
                direction=EventDirection.CREDIT,
                amount_paise=20_000_000,
                description="historic invoice settlement",
                counterparty_hash=f"historic-{index}",
                occurred_at=AS_OF - timedelta(days=days),
                received_at=AS_OF - timedelta(days=days),
                idempotency_key=f"historic-demo-{d.applicant.id}-{index}",
            )
        )
    await db_session.commit()
    demo_policy = seed_policy_v1().model_copy(
        update={
            "policy_version": "demo-income-consistency-v1",
            "pd_enhanced": 0.002,
            "pd_standard": 0.005,
            "pd_decline_threshold": 0.01,
            "exploration_budget": 0.0,
        }
    )
    await publish_rules(db_session, d, demo_policy, version=1)
    initial = await decide(
        db_session,
        d.context,
        application_id=d.application.id,
        as_of=AS_OF,
        idempotency_key=f"demo-initial:{uuid.uuid4()}",
        generate_recourse=False,
    )
    previous = initial.decision
    # This test proves the demo helper emits evidence rather than feature/decision
    # overrides: every item is appended by the production event service.
    consent = Consent(
        tenant_id=d.tenant_id,
        applicant_id=d.applicant.id,
        status=ConsentStatus.GRANTED,
        purpose="ongoing underwriting",
        scope={"sources": [SourceType.BANK.value]},
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(consent)
    await db_session.flush()
    connection.consent_id = consent.id
    await db_session.commit()
    events = income_consistency_sequence(d.applicant.external_ref)
    results = [await ingest_event(db_session, d.context, event) for event in events]
    assert len({result.job.id for result in results if result.job}) == 1
    job = results[0].job
    assert job is not None
    job.status = JobStatus.RUNNING
    await db_session.commit()
    outcome = await handle_redecide(db_session, job, d.context)
    new = await db_session.get(Decision, uuid.UUID(outcome["decision_id"]))
    assert new is not None
    assert new.feature_snapshot_id != previous.feature_snapshot_id
    change = await db_session.get(DecisionChange, uuid.UUID(outcome["change_id"]))
    assert change is not None
    old_snapshot = await db_session.get(FeatureSnapshot, previous.feature_snapshot_id)
    new_snapshot = await db_session.get(FeatureSnapshot, new.feature_snapshot_id)
    assert old_snapshot is not None and new_snapshot is not None
    old_risk = await db_session.scalar(
        select(Assessment).where(
            Assessment.feature_snapshot_id == previous.feature_snapshot_id,
            Assessment.kind == AssessmentKind.RISK,
        )
    )
    new_risk = await db_session.scalar(
        select(Assessment).where(
            Assessment.feature_snapshot_id == new.feature_snapshot_id,
            Assessment.kind == AssessmentKind.RISK,
        )
    )
    assert old_risk is not None and new_risk is not None
    transition_detail = {
        "old_pd": old_risk.payload["pd"],
        "new_pd": new_risk.payload["pd"],
        "old_outcome": change.previous_outcome,
        "new_outcome": change.new_outcome,
    }
    assert change.previous_outcome == "DECLINE_RISK", transition_detail
    assert change.new_outcome == "APPROVE_STARTER"
    assert change.direction == "IMPROVED"
    assert any(item["label"] == "Income consistency" for item in change.feature_changes), {
        "moves": change.feature_changes,
        "old_cv": old_snapshot.values.get("monthly_inflow_cv"),
        "new_cv": new_snapshot.values.get("monthly_inflow_cv"),
    }
    queue = await list_queue(db_session, d.tenant_id, "CREDIT_ANALYST", view="newly-eligible")
    assert [row.id for row in queue.rows] == [new.id]


async def test_demo_route_is_disabled_and_never_available_in_production(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = await build_decidable(db_session)
    payload = DemoIncomeConsistencyRequest(applicant_ref=d.applicant.external_ref)
    monkeypatch.setattr(settings, "demo_events_enabled", False)
    with pytest.raises(HTTPException) as disabled:
        await generate_income_consistency_demo(payload, d.context, db_session)
    assert disabled.value.status_code == 404

    monkeypatch.setattr(settings, "demo_events_enabled", True)
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(HTTPException) as production:
        await generate_income_consistency_demo(payload, d.context, db_session)
    assert production.value.status_code == 404
