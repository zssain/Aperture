import time
import uuid
from datetime import UTC, datetime

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
from app.services.policy.simulation import UNCALIBRATED_CAVEAT, policy_hash, simulate_policy
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.factories import create_user


def test_policy_hash_changes_with_exact_draft() -> None:
    original = seed_policy_v1().model_dump(mode="json")
    changed = {**original, "min_coverage": original["min_coverage"] + 1}
    assert policy_hash(original) != policy_hash(changed)


def test_uncalibrated_loss_caveat_is_explicit() -> None:
    assert "UNCALIBRATED" in UNCALIBRATED_CAVEAT
    assert "directional only" in UNCALIBRATED_CAVEAT


@requires_db
async def test_thousand_snapshot_simulation_is_fast_and_transition_is_exact(
    db_session: AsyncSession,
) -> None:
    user, tenant = await create_user(db_session, role=UserRole.CREDIT_POLICY_OWNER)
    applicant = Applicant(tenant_id=tenant.id, external_ref=f"sim-{uuid.uuid4().hex}")
    db_session.add(applicant)
    await db_session.flush()
    application = Application(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        requested_amount_paise=1_000_000,
        requested_tenor_months=12,
    )
    policy = PolicyVersion(
        tenant_id=tenant.id,
        version=1,
        status=PolicyStatus.DRAFT,
        rules=seed_policy_v1().model_dump(mode="json"),
        created_by=user.id,
    )
    db_session.add_all([application, policy])
    await db_session.flush()
    as_of = datetime(2026, 8, 1, tzinfo=UTC)
    snapshots = [
        FeatureSnapshot(
            tenant_id=tenant.id,
            applicant_id=applicant.id,
            application_id=application.id,
            as_of=as_of,
            schema_version="features-v1",
            values={"history_depth_days": 90, "bureau_score": None},
            null_map={"bureau_score": "missing"},
            input_hash=uuid.uuid4().hex,
        )
        for _ in range(1_000)
    ]
    db_session.add_all(snapshots)
    await db_session.flush()
    assessments: list[Assessment] = []
    decisions: list[Decision] = []
    for snapshot in snapshots:
        common = {
            "tenant_id": tenant.id,
            "applicant_id": applicant.id,
            "feature_snapshot_id": snapshot.id,
            "calibration_status": CalibrationStatus.NOT_APPLICABLE,
        }
        assessments.extend(
            [
                Assessment(
                    **{**common, "calibration_status": CalibrationStatus.UNCALIBRATED},
                    kind=AssessmentKind.RISK,
                    payload={"pd": 0.05, "calibration_status": "UNCALIBRATED", "reason_codes": []},
                    engine_version="risk-v1",
                ),
                Assessment(
                    **common,
                    kind=AssessmentKind.COVERAGE,
                    payload={"score": 80, "band": "HIGH", "missing_sources": []},
                    engine_version="coverage-v1",
                ),
                Assessment(
                    **common,
                    kind=AssessmentKind.AFFORDABILITY,
                    payload={
                        "status": "PASS",
                        "max_supportable_principal_paise": 2_000_000,
                        "dsr": 0.2,
                        "dsr_ceiling": 0.5,
                    },
                    engine_version="affordability-v1",
                ),
                Assessment(
                    **common,
                    kind=AssessmentKind.MANIPULATION,
                    payload={"band": "CLEAR"},
                    engine_version="manipulation-v1",
                ),
            ]
        )
        decisions.append(
            Decision(
                tenant_id=tenant.id,
                application_id=application.id,
                applicant_id=applicant.id,
                feature_snapshot_id=snapshot.id,
                policy_version_id=policy.id,
                action=DecisionAction.DECLINE,
                routing="AUTO",
                terms={},
                fired_rules=[],
                decided_at=as_of,
            )
        )
    db_session.add_all([*assessments, *decisions])
    await db_session.commit()

    started = time.perf_counter()
    report = await simulate_policy(db_session, tenant_id=tenant.id, policy_id=policy.id)
    elapsed = time.perf_counter() - started
    assert elapsed < 60
    assert report["n_snapshots"] == 1_000
    assert report["transition_matrix"] == {"DECLINE->APPROVE": 1_000}
    assert report["approval_delta"] == 1.0
    assert set(report) == {
        "draft_hash",
        "n_snapshots",
        "approval_delta",
        "cohort_deltas",
        "transition_matrix",
        "modelled_bad_rate_delta",
        "expected_loss_delta",
        "caveats",
        "largest_flips",
    }
