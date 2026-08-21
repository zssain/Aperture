"""Case-file tests: assembler completeness, blocking_tab per routing reason, lineage
correctness (recomputed from cited events), the bureau-only counterfactual, evidence
pagination + server-side category filter, and cross-tenant 404.

The integration tests drive a real decision through the orchestrator (so they need the risk
scorecard); the pure ``blocking_tab`` mapping is asserted without a database.
"""

import uuid

import pytest
from app.models.enums import UserRole
from app.services.cases.assembler import (
    CaseNotFoundError,
    assemble_case,
    blocking_tab_for,
    get_lineage,
    list_evidence,
)
from app.services.orchestrator.service import decide
from app.services.risk.registry import REGISTRY_PATH
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.decision_fixtures import AS_OF, build_decidable, publish_seed
from tests.factories import create_user

pytestmark = requires_db

_needs_artifacts = pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="risk artifacts not built")


def _gate(number: int, name: str, outcome: str) -> dict[str, object]:
    return {"number": number, "name": name, "outcome": outcome}


# --------------------------------------------------------------------------- #
# blocking_tab: the case opens on the tab that answers the first gate that fired.
# --------------------------------------------------------------------------- #
def test_blocking_tab_per_routing_reason() -> None:
    cases: list[tuple[list[dict[str, object]], str]] = [
        ([_gate(1, "manipulation_high", "FRAUD_REVIEW")], "verification"),
        ([_gate(5, "manipulation_elevated", "REVIEW_FRAUD")], "verification"),
        ([_gate(2, "affordability_fail", "DECLINE_AFFORDABILITY")], "assessment"),
        ([_gate(3, "affordability_indeterminate", "REVIEW_EVIDENCE")], "assessment"),
        ([_gate(4, "coverage_below_min", "REVIEW_EVIDENCE")], "evidence"),
        ([_gate(6, "pd_decline", "DECLINE_RISK")], "assessment"),
        ([_gate(8, "approve_standard", "APPROVE_STANDARD")], "decision"),
        # An approval forced to a human by the ceiling opens on Decision & Audit.
        (
            [
                _gate(7, "approve_enhanced", "APPROVE_ENHANCED"),
                _gate(10, "mandatory_review", "APPROVE_ENHANCED"),
            ],
            "decision",
        ),
    ]
    for fired, expected in cases:
        assert blocking_tab_for(fired, True) == expected
    # No decision at all (an assessment was unavailable) → start at the evidence.
    assert blocking_tab_for([], False) == "evidence"


# --------------------------------------------------------------------------- #
# Assembler completeness + versions.
# --------------------------------------------------------------------------- #
@_needs_artifacts
async def test_case_assembles_with_all_four_assessments(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k1"
    )

    case = await assemble_case(db_session, d.tenant_id, d.application.id)

    assert set(case.assessments.keys()) == {"RISK", "COVERAGE", "AFFORDABILITY", "MANIPULATION"}
    assert case.assessment_failed is False
    assert case.decision is not None
    assert case.decision.reasons  # reasons present
    assert case.decision.reasons[0].code.startswith("GATE_")
    # Versions travel with each assessment.
    assert case.assessments["RISK"].calibration_status == "UNCALIBRATED"
    assert case.assessments["RISK"].model_version  # model version present
    assert case.assessments["COVERAGE"].engine_version
    # The band opens on a real tab and the PD chip is uncalibrated.
    assert case.blocking_tab in {"evidence", "assessment", "verification", "recourse", "decision"}
    assert case.chips.pd.status == "uncalibrated"
    assert case.feature_snapshot_id is not None


@_needs_artifacts
async def test_case_opens_on_its_actual_blocking_tab(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k1"
    )
    case = await assemble_case(db_session, d.tenant_id, d.application.id)
    assert case.decision is not None
    assert case.blocking_tab == blocking_tab_for(case.decision.fired_rules, True)


# --------------------------------------------------------------------------- #
# Lineage: cited event IDs genuinely contribute — asserted by recomputing from them.
# --------------------------------------------------------------------------- #
@_needs_artifacts
async def test_lineage_recomputes_from_cited_events(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k1"
    )
    case = await assemble_case(db_session, d.tenant_id, d.application.id)
    assert case.feature_snapshot_id is not None

    lineage = await get_lineage(
        db_session, d.tenant_id, case.feature_snapshot_id, "median_monthly_inflow_paise"
    )
    assert lineage.contributing_event_ids  # income events cited
    assert lineage.value is not None
    assert lineage.matches is True  # recomputed from the cited events equals the stored value
    assert lineage.formula_doc  # definition/formula present
    assert lineage.window == "6m"


@_needs_artifacts
async def test_lineage_unknown_feature_is_404(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k1"
    )
    case = await assemble_case(db_session, d.tenant_id, d.application.id)
    assert case.feature_snapshot_id is not None
    with pytest.raises(CaseNotFoundError):
        await get_lineage(db_session, d.tenant_id, case.feature_snapshot_id, "not_a_feature")


# --------------------------------------------------------------------------- #
# Bureau-only counterfactual: a bureau-only lender cannot approve this thin-file borrower.
# --------------------------------------------------------------------------- #
@_needs_artifacts
async def test_bureau_only_counterfactual_differs(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    result = await decide(
        db_session, d.context, application_id=d.application.id, as_of=AS_OF, idempotency_key="k1"
    )
    case = await assemble_case(db_session, d.tenant_id, d.application.id)

    # No bureau evidence exists, so a bureau-only policy has nothing to score.
    assert case.bureau_only.available is False
    # The cash-flow decision approved; bureau-only cannot reach that outcome.
    assert result.decision.action.value in {"APPROVE", "APPROVE_STARTER"}
    assert case.bureau_only.action not in {"APPROVE", "APPROVE_STARTER"}


# --------------------------------------------------------------------------- #
# Evidence: server-side pagination + category filter.
# --------------------------------------------------------------------------- #
@_needs_artifacts
async def test_evidence_paginates_and_filters_server_side(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session, months=7)
    await publish_seed(db_session, d)

    first = await list_evidence(db_session, d.tenant_id, d.application.id, limit=5)
    assert len(first.rows) == 5
    assert first.next_cursor is not None
    # Events come back newest-first.
    assert first.rows[0].occurred_at >= first.rows[-1].occurred_at

    seen: set[str] = {str(r.id) for r in first.rows}
    page = first
    while page.next_cursor is not None:
        page = await list_evidence(
            db_session, d.tenant_id, d.application.id, limit=5, cursor=page.next_cursor
        )
        seen.update(str(r.id) for r in page.rows)
    assert len(seen) == 7 * 3  # 7 months × (salary + rent + emi)

    # Category filter is applied server-side: only salary credits come back.
    salary = await list_evidence(
        db_session, d.tenant_id, d.application.id, category="SALARY", limit=50
    )
    assert len(salary.rows) == 7
    assert all(r.category == "SALARY" for r in salary.rows)


@_needs_artifacts
async def test_evidence_empty_category_returns_nothing(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    await publish_seed(db_session, d)
    # No BUSINESS_INCOME events exist → the filter returns an empty page, not everything.
    result = await list_evidence(
        db_session, d.tenant_id, d.application.id, category="BUSINESS_INCOME", limit=50
    )
    assert result.rows == []


# --------------------------------------------------------------------------- #
# No decision / assessment unavailable → NO DECISION state.
# --------------------------------------------------------------------------- #
async def test_case_with_no_decision(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session, with_source=False)
    case = await assemble_case(db_session, d.tenant_id, d.application.id)
    assert case.decision is None
    assert case.assessment_failed is True
    assert case.chips.pd.status == "unavailable"
    assert case.chips.verification == "UNAVAILABLE"
    assert case.blocking_tab == "evidence"
    assert case.bureau_only.available is False


# --------------------------------------------------------------------------- #
# Cross-tenant is a 404, never a 403.
# --------------------------------------------------------------------------- #
async def test_cross_tenant_case_is_not_found(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    _, other_tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    with pytest.raises(CaseNotFoundError):
        await assemble_case(db_session, other_tenant.id, d.application.id)


async def test_missing_case_is_not_found(db_session: AsyncSession) -> None:
    d = await build_decidable(db_session)
    with pytest.raises(CaseNotFoundError):
        await assemble_case(db_session, d.tenant_id, uuid.uuid4())
