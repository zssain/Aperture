import time
import uuid
from datetime import UTC, datetime

from app.models.decision import Decision
from app.models.enums import (
    ClassificationMethod,
    DecisionAction,
    EventDirection,
    MerchantCatalogStatus,
)
from app.models.merchant_catalog import MerchantCatalogEntry, MerchantCatalogVersion
from app.services.classification.rules import TxnCategory
from app.services.classification.service import TxnEvent, VectorCandidate, classify
from app.services.orchestrator.service import decide
from app.services.policy.defaults import seed_policy_v1
from app.services.policy.engine import evaluate
from app.services.policy.schema import (
    AffordabilityInput,
    CoverageInput,
    FourAssessments,
    LoanRequest,
    ManipulationInput,
    RiskInput,
)
from app.services.queue.service import list_queue
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.decision_fixtures import AS_OF, build_decidable, publish_seed


def _assessment() -> FourAssessments:
    return FourAssessments(
        manipulation=ManipulationInput(band="LOW"),
        affordability=AffordabilityInput(
            status="ASSESSABLE",
            max_supportable_principal_paise=10_000_000,
            dsr=0.2,
            dsr_ceiling=0.5,
        ),
        coverage=CoverageInput(score=80, band="HIGH", missing_sources=()),
        risk=RiskInput(
            pd=0.1,
            calibration_status="UNCALIBRATED",
            top_contributors=(),
            reason_codes=(),
        ),
    )


def test_decision_latency_p95_budget_including_classification() -> None:
    samples: list[float] = []
    for _index in range(100):
        event = TxnEvent(
            uuid.uuid4(),
            datetime.now(UTC),
            EventDirection.CREDIT,
            1_000_000,
            None,
            "semantic remittance",
            "cp",
            None,
        )
        started = time.perf_counter()
        classified = classify(
            [event],
            vector_candidates={
                event.event_id: VectorCandidate(
                    TxnCategory.GIG_INCOME,
                    0.9,
                    uuid.uuid4(),
                    uuid.UUID(int=99),
                    (TxnCategory.GIG_INCOME,) * 3,
                    "semantic remittance",
                )
            },
        )
        assert classified.events[0].classification_method is ClassificationMethod.VECTOR_KNN
        evaluate(
            _assessment(),
            LoanRequest(
                application_id=uuid.uuid4(),
                amount_paise=1_000_000,
                tenor_months=12,
                annual_rate_bps=1800,
            ),
            seed_policy_v1(),
        )
        samples.append(time.perf_counter() - started)
    assert sorted(samples)[94] < 2.5


async def test_queue_query_10000_decisions_under_300ms(db_session: AsyncSession) -> None:
    fixture = await build_decidable(db_session)
    await publish_seed(db_session, fixture)
    seed = await decide(
        db_session,
        fixture.context,
        application_id=fixture.application.id,
        as_of=AS_OF,
        idempotency_key="performance-seed",
        generate_recourse=False,
    )
    decision = seed.decision
    await db_session.execute(
        insert(Decision),
        [
            {
                "id": uuid.uuid4(),
                "tenant_id": fixture.tenant_id,
                "application_id": fixture.application.id,
                "applicant_id": fixture.applicant.id,
                "feature_snapshot_id": decision.feature_snapshot_id,
                "policy_version_id": decision.policy_version_id,
                "action": DecisionAction.APPROVE,
                "routing": "AUTOMATED",
                "idempotency_key": f"performance-queue-{index}",
                "exploration_cohort": False,
                "approved_limit_paise": 1_000_000,
                "terms": {},
                "fired_rules": [
                    {"number": 8, "name": "approve_standard", "outcome": "APPROVE_STANDARD"}
                ],
                "is_final": True,
            }
            for index in range(9_999)
        ],
    )
    await db_session.commit()
    started = time.perf_counter()
    page = await list_queue(
        db_session, fixture.tenant_id, "AUDITOR", view="all-decisions", limit=50
    )
    elapsed = time.perf_counter() - started
    assert len(page.rows) == 50
    assert elapsed < 0.3, f"10,000-decision queue query took {elapsed:.3f}s"


def test_simulation_1000_snapshots_under_60s() -> None:
    request = LoanRequest(
        application_id=uuid.uuid4(), amount_paise=1_000_000, tenor_months=12, annual_rate_bps=1800
    )
    started = time.perf_counter()
    for _ in range(1_000):
        evaluate(_assessment(), request, seed_policy_v1())
    assert time.perf_counter() - started < 60


async def test_catalogue_sized_database_knn_under_50ms(db_session: AsyncSession) -> None:
    catalog = MerchantCatalogVersion(
        version="performance-catalog",
        status=MerchantCatalogStatus.DRAFT,
        embedding_model_id="performance-384",
        embedding_dimension=384,
        entry_count=310,
        content_hash="a" * 64,
    )
    db_session.add(catalog)
    await db_session.flush()
    db_session.add_all(
        MerchantCatalogEntry(
            catalog_version_id=catalog.id,
            canonical_name=f"performance-merchant-{index:03d}",
            category="MERCHANT",
            aliases=[],
            embedding=[index / 100_000.0] * 384,
            source_note="synthetic performance corpus",
        )
        for index in range(310)
    )
    await db_session.commit()
    query_vector = "[" + ",".join(["0.001"] * 384) + "]"
    # Warm the connection/plan so the asserted latency measures the kNN operation.
    statement = text(
        "SELECT id FROM merchant_catalog_entries "
        "WHERE catalog_version_id = :catalog_id "
        "ORDER BY embedding <=> CAST(:vector AS vector) LIMIT 5"
    )
    await db_session.execute(statement, {"catalog_id": catalog.id, "vector": query_vector})
    started = time.perf_counter()
    rows = (
        await db_session.execute(statement, {"catalog_id": catalog.id, "vector": query_vector})
    ).all()
    elapsed = time.perf_counter() - started
    assert len(rows) == 5
    assert elapsed < 0.05, f"catalogue kNN query took {elapsed:.3f}s"
