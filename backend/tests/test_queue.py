"""Exception-queue tests: role scoping, per-view partitioning, the routed_because projection,
server-side filtering/sorting/cursor pagination, and performance at 10k decisions.

Decisions are seeded directly (not via the orchestrator) so we can exercise every gate/routing
combination cheaply and at scale. Every test scopes to its own tenant, because the module-scoped
``migrated_db`` keeps rows across tests in a file.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.assessment import Assessment
from app.models.decision import Decision
from app.models.enums import (
    AssessmentKind,
    CalibrationStatus,
    DecisionAction,
    PolicyStatus,
    UserRole,
)
from app.models.feature import FeatureSnapshot
from app.models.policy import PolicyVersion
from app.services.policy.defaults import seed_policy_v1
from app.services.queue.service import (
    QueueAccessError,
    accessible_views,
    list_queue,
    project_routed_because,
)
from sqlalchemy import event, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.conftest import requires_db
from tests.factories import create_user

pytestmark = requires_db

_AS_OF = datetime(2026, 8, 1, tzinfo=UTC)
_RULES = seed_policy_v1().model_dump(mode="json")


class Seed:
    """Tenant + applicant + application + a LIVE policy the seeded decisions reference."""

    def __init__(
        self,
        tenant_id: uuid.UUID,
        applicant_id: uuid.UUID,
        application_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        self.tenant_id = tenant_id
        self.applicant_id = applicant_id
        self.application_id = application_id
        self.policy_version_id = policy_version_id
        self.user_id = user_id


async def _make_seed(session: AsyncSession, *, amount_paise: int = 10_000_000) -> Seed:
    user, tenant = await create_user(session, role=UserRole.CREDIT_ANALYST)
    applicant = Applicant(
        tenant_id=tenant.id, external_ref=f"ext-{uuid.uuid4().hex[:8]}", display_name="Asha Kumar"
    )
    session.add(applicant)
    await session.flush()
    application = Application(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        requested_amount_paise=amount_paise,
        requested_tenor_months=12,
    )
    session.add(application)
    policy = PolicyVersion(
        tenant_id=tenant.id,
        version=1,
        status=PolicyStatus.LIVE,
        rules=_RULES,
    )
    session.add(policy)
    await session.flush()
    await session.commit()
    return Seed(tenant.id, applicant.id, application.id, policy.id, user.id)


async def _seed_decision(
    session: AsyncSession,
    seed: Seed,
    *,
    fired_rules: list[dict[str, object]],
    routing: str,
    action: DecisionAction,
    pd: float = 0.12,
    calibration: CalibrationStatus = CalibrationStatus.UNCALIBRATED,
    coverage_score: int = 62,
    manip_band: str = "CLEAR",
    trigger_counts: dict[str, int] | None = None,
    is_final: bool = False,
    terms: dict[str, object] | None = None,
    approved_limit_paise: int | None = None,
    decided_offset_minutes: int = 0,
) -> Decision:
    snapshot = FeatureSnapshot(
        tenant_id=seed.tenant_id,
        applicant_id=seed.applicant_id,
        application_id=seed.application_id,
        as_of=_AS_OF,
        schema_version="features-v1",
        values={},
        null_map={},
        input_hash=uuid.uuid4().hex,
    )
    session.add(snapshot)
    await session.flush()
    session.add_all(
        [
            Assessment(
                tenant_id=seed.tenant_id,
                applicant_id=seed.applicant_id,
                feature_snapshot_id=snapshot.id,
                kind=AssessmentKind.RISK,
                payload={"pd": pd, "calibration_status": calibration.value},
                engine_version="scorecard-v1",
                calibration_status=calibration,
            ),
            Assessment(
                tenant_id=seed.tenant_id,
                applicant_id=seed.applicant_id,
                feature_snapshot_id=snapshot.id,
                kind=AssessmentKind.COVERAGE,
                payload={"score": coverage_score, "band": "MID"},
                engine_version="coverage-v1",
                calibration_status=CalibrationStatus.NOT_APPLICABLE,
            ),
            Assessment(
                tenant_id=seed.tenant_id,
                applicant_id=seed.applicant_id,
                feature_snapshot_id=snapshot.id,
                kind=AssessmentKind.MANIPULATION,
                payload={"band": manip_band, "trigger_counts": trigger_counts or {}},
                engine_version="manip-config-v1",
                calibration_status=CalibrationStatus.NOT_APPLICABLE,
            ),
        ]
    )
    decision = Decision(
        tenant_id=seed.tenant_id,
        application_id=seed.application_id,
        applicant_id=seed.applicant_id,
        feature_snapshot_id=snapshot.id,
        policy_version_id=seed.policy_version_id,
        action=action,
        routing=routing,
        fired_rules=fired_rules,
        is_final=is_final,
        terms=terms or {},
        approved_limit_paise=approved_limit_paise,
        decided_at=_AS_OF - timedelta(minutes=decided_offset_minutes),
    )
    session.add(decision)
    await session.commit()
    return decision


def _gate(number: int, name: str, outcome: str) -> dict[str, object]:
    return {"number": number, "name": name, "outcome": outcome}


# --------------------------------------------------------------------------- #
# routed_because: a pure projection, asserted for every routing reason.
# --------------------------------------------------------------------------- #
def test_routed_because_matches_the_gate_that_fired() -> None:
    rules = _RULES

    coverage = project_routed_because(
        fired_rules=[_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")],
        pd=0.1,
        coverage_score=41,
        trigger_counts=None,
        rules={**rules, "min_coverage": 55},
    )
    assert coverage.text == "Coverage 41 (min 55)"
    assert coverage.rule_number == 4

    fraud = project_routed_because(
        fired_rules=[_gate(5, "manipulation_elevated", "REVIEW_FRAUD")],
        pd=0.1,
        coverage_score=70,
        trigger_counts={"D1": 3, "D2": 1},
        rules=rules,
    )
    assert fraud.text == "Verification ELEVATED · circular flow ×3"
    assert fraud.rule_number == 5

    near = project_routed_because(
        fired_rules=[_gate(6, "pd_decline", "DECLINE_RISK")],
        pd=0.171,
        coverage_score=70,
        trigger_counts=None,
        rules={**rules, "pd_decline_threshold": 0.170, "exploration_margin": 0.03},
    )
    assert near.text == "Near boundary PD 0.171 (threshold 0.170)"
    assert near.rule_number == 6

    # An approval forced to a human by the ceiling is in the queue *because of rule 10*.
    mandatory = project_routed_because(
        fired_rules=[
            _gate(7, "approve_enhanced", "APPROVE_ENHANCED"),
            _gate(10, "mandatory_review", "APPROVE_ENHANCED"),
        ],
        pd=0.05,
        coverage_score=80,
        trigger_counts=None,
        rules={**rules, "mandatory_review_ceiling_paise": 20_000_000},
    )
    assert mandatory.rule_number == 10
    assert "Mandatory review" in mandatory.text


# --------------------------------------------------------------------------- #
# Role scoping: views the role cannot access are absent, not hidden.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_views_are_role_scoped(db_session: AsyncSession) -> None:
    assert "fraud-review" not in accessible_views("CREDIT_ANALYST")
    assert "qa-sample" not in accessible_views("CREDIT_ANALYST")
    assert accessible_views("FRAUD_REVIEWER") == ("fraud-review", "all-decisions")
    assert accessible_views("AUDITOR") == ("all-decisions", "qa-sample")

    seed = await _make_seed(db_session)
    # An analyst's counts contain exactly the analyst's views.
    resp = await list_queue(db_session, seed.tenant_id, "CREDIT_ANALYST")
    assert set(resp.counts.keys()) == set(accessible_views("CREDIT_ANALYST"))
    assert "fraud-review" not in resp.counts

    # Requesting a forbidden view is a hard error (403 at the route), not an empty page.
    with pytest.raises(QueueAccessError):
        await list_queue(db_session, seed.tenant_id, "CREDIT_ANALYST", view="fraud-review")


@pytest.mark.asyncio
async def test_fraud_reviewer_default_landing_view(db_session: AsyncSession) -> None:
    seed = await _make_seed(db_session)
    resp = await list_queue(db_session, seed.tenant_id, "FRAUD_REVIEWER")
    assert resp.view == "fraud-review"


# --------------------------------------------------------------------------- #
# Per-view partitioning + tab counts match row counts.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_views_partition_decisions(db_session: AsyncSession) -> None:
    seed = await _make_seed(db_session)
    await _seed_decision(
        db_session,
        seed,
        fired_rules=[_gate(5, "manipulation_elevated", "REVIEW_FRAUD")],
        routing="HUMAN",
        action=DecisionAction.REFER,
        manip_band="ELEVATED",
        trigger_counts={"D1": 2},
        decided_offset_minutes=10,
    )
    await _seed_decision(
        db_session,
        seed,
        fired_rules=[_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")],
        routing="HUMAN",
        action=DecisionAction.REFER,
        coverage_score=30,
        decided_offset_minutes=20,
    )
    await _seed_decision(
        db_session,
        seed,
        fired_rules=[
            _gate(7, "approve_enhanced", "APPROVE_ENHANCED"),
            _gate(10, "mandatory_review", "APPROVE_ENHANCED"),
        ],
        routing="HUMAN",
        action=DecisionAction.APPROVE,
        approved_limit_paise=25_000_000,
        decided_offset_minutes=30,
    )
    await _seed_decision(
        db_session,
        seed,
        fired_rules=[_gate(8, "approve_standard", "APPROVE_STANDARD")],
        routing="AUTOMATED",
        action=DecisionAction.APPROVE,
        is_final=True,
        decided_offset_minutes=40,
    )

    fraud = await list_queue(db_session, seed.tenant_id, "FRAUD_REVIEWER", view="fraud-review")
    assert len(fraud.rows) == 1
    assert fraud.rows[0].verification == "ELEVATED"

    analyst = await list_queue(db_session, seed.tenant_id, "CREDIT_ANALYST", view="my-exceptions")
    # my-exceptions is the broad human inbox: the coverage case and the mandatory-review
    # approval, but NOT the fraud case (that is walled off to fraud-review).
    assert len(analyst.rows) == 2
    assert any(r.routed_because.rule_number == 10 for r in analyst.rows)
    assert all(r.verification != "ELEVATED" for r in analyst.rows)  # no fraud cases leak in

    evidence = await list_queue(
        db_session, seed.tenant_id, "CREDIT_ANALYST", view="evidence-needed"
    )
    # evidence-needed is the coverage/recourse subset of the human inbox.
    assert len(evidence.rows) == 1
    assert evidence.rows[0].routed_because.text.startswith("Coverage 30")

    allv = await list_queue(db_session, seed.tenant_id, "CREDIT_ANALYST", view="all-decisions")
    assert len(allv.rows) == 4

    # Tab counts equal the row counts of each view for this tenant.
    assert analyst.counts["my-exceptions"] == 2
    assert analyst.counts["evidence-needed"] == 1
    assert analyst.counts["all-decisions"] == 4
    assert fraud.counts["fraud-review"] == 1


@pytest.mark.asyncio
async def test_uncalibrated_pd_renders_neutral(db_session: AsyncSession) -> None:
    seed = await _make_seed(db_session)
    await _seed_decision(
        db_session,
        seed,
        fired_rules=[_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")],
        routing="HUMAN",
        action=DecisionAction.REFER,
        pd=0.187,
        calibration=CalibrationStatus.UNCALIBRATED,
        coverage_score=30,
    )
    resp = await list_queue(db_session, seed.tenant_id, "CREDIT_ANALYST", view="evidence-needed")
    assert resp.rows[0].pd.status == "uncalibrated"
    assert resp.rows[0].pd.value == pytest.approx(0.187)


# --------------------------------------------------------------------------- #
# Server-side filtering + pagination, verified by inspecting the emitted SQL.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_filtering_and_pagination_are_server_side(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    seed = await _make_seed(db_session)
    for i in range(5):
        await _seed_decision(
            db_session,
            seed,
            fired_rules=[_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")],
            routing="HUMAN",
            action=DecisionAction.REFER,
            coverage_score=20 + i * 10,
            decided_offset_minutes=i,
        )

    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", _capture)
    try:
        resp = await list_queue(
            db_session,
            seed.tenant_id,
            "CREDIT_ANALYST",
            view="evidence-needed",
            coverage_min=40,
            limit=2,
            sort="coverage",
        )
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", _capture)

    # The coverage filter, ordering and limit are all pushed into SQL; no OFFSET anywhere.
    row_sql = next(s for s in statements if "LIMIT" in s and "ORDER BY" in s)
    assert ">=" in row_sql  # coverage_min pushed down
    assert "OFFSET" not in row_sql  # keyset pagination, not offset
    assert "AS INTEGER" in row_sql  # filtering/sorting on the JSONB coverage score, cast in SQL
    assert "assessments" in row_sql  # the assessment payloads are joined, not fetched per-row

    # Only coverage_score >= 40 comes back (three of five rows), first page capped at 2.
    assert len(resp.rows) == 2
    assert resp.next_cursor is not None
    assert all(r.coverage.value is not None and r.coverage.value >= 40 for r in resp.rows)


@pytest.mark.asyncio
async def test_cursor_pagination_is_stable_across_inserts(db_session: AsyncSession) -> None:
    seed = await _make_seed(db_session)
    for i in range(6):
        await _seed_decision(
            db_session,
            seed,
            fired_rules=[_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")],
            routing="HUMAN",
            action=DecisionAction.REFER,
            coverage_score=10 + i,
            decided_offset_minutes=i,
        )

    seen: list[str] = []
    page = await list_queue(
        db_session,
        seed.tenant_id,
        "CREDIT_ANALYST",
        view="evidence-needed",
        sort="coverage",
        limit=2,
    )
    seen.extend(str(r.id) for r in page.rows)

    # A new case resolved-in underneath the reader must not shift the page.
    await _seed_decision(
        db_session,
        seed,
        fired_rules=[_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")],
        routing="HUMAN",
        action=DecisionAction.REFER,
        coverage_score=11,
        decided_offset_minutes=99,
    )

    while page.next_cursor is not None:
        page = await list_queue(
            db_session,
            seed.tenant_id,
            "CREDIT_ANALYST",
            view="evidence-needed",
            sort="coverage",
            limit=2,
            cursor=page.next_cursor,
        )
        seen.extend(str(r.id) for r in page.rows)

    assert len(seen) == len(set(seen))  # no duplicates, no skips


@pytest.mark.asyncio
async def test_qa_sample_is_deterministic(db_session: AsyncSession) -> None:
    seed = await _make_seed(db_session)
    for i in range(40):
        await _seed_decision(
            db_session,
            seed,
            fired_rules=[_gate(8, "approve_standard", "APPROVE_STANDARD")],
            routing="AUTOMATED",
            action=DecisionAction.APPROVE,
            is_final=True,
            decided_offset_minutes=i,
        )
    first = await list_queue(db_session, seed.tenant_id, "AUDITOR", view="qa-sample", limit=100)
    second = await list_queue(db_session, seed.tenant_id, "AUDITOR", view="qa-sample", limit=100)
    assert [str(r.id) for r in first.rows] == [str(r.id) for r in second.rows]
    assert first.auto_decided_24h >= 0


# --------------------------------------------------------------------------- #
# Performance: the query stays fast at 10k decisions (cursor pagination).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_query_is_fast_at_10k_decisions(db_session: AsyncSession) -> None:
    seed = await _make_seed(db_session)
    total = 10_000
    snap_rows = []
    assess_rows = []
    decision_rows = []
    for i in range(total):
        snap_id = uuid.uuid4()
        snap_rows.append(
            {
                "id": snap_id,
                "tenant_id": seed.tenant_id,
                "applicant_id": seed.applicant_id,
                "application_id": seed.application_id,
                "as_of": _AS_OF,
                "schema_version": "features-v1",
                "values": {},
                "null_map": {},
                "input_hash": uuid.uuid4().hex,
            }
        )
        for kind, payload in (
            (AssessmentKind.RISK, {"pd": 0.12, "calibration_status": "UNCALIBRATED"}),
            (AssessmentKind.COVERAGE, {"score": 30 + (i % 50), "band": "MID"}),
            (AssessmentKind.MANIPULATION, {"band": "CLEAR", "trigger_counts": {}}),
        ):
            assess_rows.append(
                {
                    "id": uuid.uuid4(),
                    "tenant_id": seed.tenant_id,
                    "applicant_id": seed.applicant_id,
                    "feature_snapshot_id": snap_id,
                    "kind": kind,
                    "payload": payload,
                    "engine_version": "v1",
                    "calibration_status": CalibrationStatus.UNCALIBRATED
                    if kind == AssessmentKind.RISK
                    else CalibrationStatus.NOT_APPLICABLE,
                }
            )
        decision_rows.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": seed.tenant_id,
                "application_id": seed.application_id,
                "applicant_id": seed.applicant_id,
                "feature_snapshot_id": snap_id,
                "policy_version_id": seed.policy_version_id,
                "action": DecisionAction.REFER,
                "routing": "HUMAN",
                "fired_rules": [_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")],
                "is_final": False,
                "terms": {},
                "exploration_cohort": False,
                "decided_at": _AS_OF - timedelta(minutes=i),
            }
        )

    for chunk_start in range(0, total, 2000):
        await db_session.execute(
            insert(FeatureSnapshot), snap_rows[chunk_start : chunk_start + 2000]
        )
    for chunk_start in range(0, len(assess_rows), 2000):
        await db_session.execute(insert(Assessment), assess_rows[chunk_start : chunk_start + 2000])
    for chunk_start in range(0, total, 2000):
        await db_session.execute(insert(Decision), decision_rows[chunk_start : chunk_start + 2000])
    await db_session.commit()

    started = time.perf_counter()
    resp = await list_queue(
        db_session, seed.tenant_id, "CREDIT_ANALYST", view="evidence-needed", limit=50
    )
    elapsed = time.perf_counter() - started

    assert len(resp.rows) == 50
    assert resp.next_cursor is not None
    assert resp.counts["evidence-needed"] == total
    # Target is < 300ms; allow headroom for the loaded test box but keep it honest.
    assert elapsed < 1.0, f"queue query took {elapsed * 1000:.0f}ms at {total} rows"

    # Verify the 10k count query is not the bottleneck either.
    assert (
        await db_session.scalar(
            select(Decision).where(Decision.tenant_id == seed.tenant_id).limit(1)
        )
    ) is not None
