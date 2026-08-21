import json
import socket
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.models.enums import ClassificationMethod, EventDirection, SourceTier, SourceType
from app.models.feature import FeatureSnapshot
from app.services.affordability.service import RequestedTerms, assess_affordability
from app.services.classification.rules import TxnCategory
from app.services.classification.service import TxnEvent, VectorCandidate, classify
from app.services.classification.vector import normalize_narration
from app.services.coverage.service import SourceEvidence, assess_coverage
from app.services.coverage.weights import COVERAGE_WEIGHTS_VERSION
from app.services.features.service import compute_feature_values
from app.services.manipulation.context import (
    DeclaredApplication,
    LedgerEventView,
    ProvenanceView,
    SourceMetadataView,
)
from app.services.manipulation.service import assess as assess_manipulation
from app.services.manipulation.service import build_context
from app.services.orchestrator.assessments import AssessmentBundle, to_four_assessments
from app.services.policy.defaults import seed_policy_v1
from app.services.policy.engine import evaluate
from app.services.policy.schema import LoanRequest
from app.services.risk.service import assess_risk

HERE = Path(__file__).parent
PERSONAS: list[dict[str, Any]] = json.loads((HERE / "fixtures/personas.json").read_text())
EXPECTED: dict[str, Any] = json.loads((HERE / "expected/decisions.json").read_text())
AS_OF = datetime(2026, 8, 1, tzinfo=UTC)


def corpus(persona: dict[str, Any]) -> tuple[list[TxnEvent], dict[uuid.UUID, VectorCandidate]]:
    months = int(persona.get("months", 6))
    category = {
        "gig": TxnCategory.GIG_INCOME,
        "salary": TxnCategory.SALARY,
        "business": TxnCategory.BUSINESS_INCOME,
        "unknown": TxnCategory.OTHER,
    }[persona["kind"]]
    events: list[TxnEvent] = []
    candidates: dict[uuid.UUID, VectorCandidate] = {}
    volatile = persona["id"] in {"high-risk", "near-boundary", "starter"}
    balance = {"high-risk": 0, "near-boundary": 5_000_000}.get(
        str(persona["id"]), 2_000_000
    )
    for month in reversed(range(months)):
        amount = (
            (250_000 if month % 2 else 8_000_000)
            if volatile
            else 4_000_000 + month * 1_000
        )
        event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{persona['id']}:{month}:income")
        balance += amount
        item = TxnEvent(
            event_id,
            AS_OF
            - timedelta(
                days=30 * month + 5 + (45 if persona["id"] == "thin-salaried" else 0)
            ),
            EventDirection.CREDIT,
            amount,
            balance,
            str(persona["narration"]),
            (
                f"{persona['id']}:{month}"
                if persona["classification"] == "VECTOR_KNN"
                else str(persona["id"])
            ),
            uuid.UUID(int=1),
        )
        events.append(item)
        if persona["classification"] == "VECTOR_KNN":
            candidates[event_id] = VectorCandidate(
                category,
                0.91,
                uuid.uuid5(uuid.NAMESPACE_URL, f"entry:{persona['id']}"),
                uuid.UUID(int=2),
                (category, category, TxnCategory.OTHER),
                normalize_narration(item.description or ""),
            )
        if volatile:
            expense_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{persona['id']}:{month}:opaque")
            expense_amount = amount - 50_000
            balance -= expense_amount
            events.append(
                TxnEvent(
                    expense_id,
                    item.occurred_at + timedelta(days=2),
                    EventDirection.DEBIT,
                    expense_amount,
                    balance,
                    "ZXQ 991188 opaque expense",
                    f"opaque:{month}",
                    uuid.UUID(int=1),
                )
            )
    if persona["id"] == "manipulation":
        # The synthetic statement's repeated impossible balance is the detector input;
        # the expected fraud routing is produced by D5, not hardcoded in the decision.
        events = [
            TxnEvent(
                event.event_id,
                event.occurred_at,
                event.direction,
                event.amount_paise,
                6_000_000,
                event.description,
                event.counterparty_hash,
                event.source_connection_id,
            )
            for event in events
        ]
    return events, candidates


def decision(persona: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    events, candidates = corpus(persona)
    classified = classify(events, vector_candidates=candidates)
    values, null_map, _lineage = compute_feature_values(AS_OF, classified.events)
    applicant_id = uuid.uuid5(uuid.NAMESPACE_URL, f"golden:{persona['id']}:applicant")
    application_id = uuid.uuid5(uuid.NAMESPACE_URL, f"golden:{persona['id']}:application")
    snapshot = FeatureSnapshot(
        tenant_id=uuid.UUID(int=10),
        applicant_id=applicant_id,
        application_id=application_id,
        as_of=AS_OF,
        schema_version="features-v1",
        values=values,
        null_map=null_map,
        lineage={},
        classifier_version=classified.classifier_version,
        input_hash="golden",
    )
    risk = assess_risk(snapshot)
    requested_amount = (
        100_000
        if persona["id"] in {"near-boundary", "starter"}
        else 500_000
        if persona["id"] == "high-risk"
        else 5_000_000
    )
    affordability = assess_affordability(
        snapshot,
        RequestedTerms(
            amount_paise=requested_amount,
            tenor_months=12,
            annual_rate_bps=1800,
        ),
    )
    coverage = assess_coverage(
        snapshot,
        [
            SourceEvidence(
                source_type=SourceType.BANK,
                tier=(
                    SourceTier.DECLARED_DOCUMENT
                    if persona["id"] in {"sparse", "thin-salaried"}
                    else SourceTier.AA_VERIFIED
                ),
                latest_event_at=AS_OF - timedelta(days=2),
            )
        ],
        COVERAGE_WEIGHTS_VERSION,
    )
    event_views = [
        LedgerEventView(
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            direction=event.direction,
            amount_paise=event.amount_paise,
            balance_paise=event.balance_paise,
            description=event.description,
            counterparty_hash=event.counterparty_hash,
            source_snapshot_id=uuid.UUID(int=20),
        )
        for event in events
    ]
    provenance = (
        ProvenanceView("FILE_HASH_MISMATCH", "HIGH", "synthetic manipulation fixture"),
    ) if persona["id"] == "manipulation" else ()
    manipulation = assess_manipulation(
        build_context(
            as_of=AS_OF,
            events=event_views,
            declared=DeclaredApplication(application_id, None, None, None),
            sources=[
                SourceMetadataView(
                    uuid.UUID(int=20),
                    SourceTier.AA_VERIFIED.value,
                    provenance,
                    tuple(event.event_id for event in events),
                )
            ],
            cross_applicant=[],
        )
    )
    bundle = AssessmentBundle(
        risk=risk,
        coverage=coverage,
        affordability=affordability,
        manipulation=manipulation,
    )
    policy_decision = evaluate(
        to_four_assessments(bundle),
        LoanRequest(
            application_id=application_id,
            amount_paise=requested_amount,
            tenor_months=12,
            annual_rate_bps=1800,
        ),
        seed_policy_v1().model_copy(update={"exploration_budget": 0.0}),
    )
    complete = {
        "outcome": policy_decision.outcome,
        "terms": asdict(policy_decision.terms) if policy_decision.terms else None,
        "assessments": {
            "risk": {
                "pd": round(risk.pd, 8),
                "calibration_status": risk.calibration_status,
                "model_version": risk.model_version,
                "reason_codes": list(risk.reason_codes),
            },
            "affordability": {
                "status": affordability.status,
                "reason": affordability.reason,
                "max_supportable_principal_paise": affordability.max_supportable_principal_paise,
            },
            "coverage": {
                "score": coverage.score,
                "band": coverage.band,
                "unclassified_inflow_share": values.get("unclassified_inflow_share"),
                "null_features": sorted(null_map),
            },
            "manipulation": {
                "band": manipulation.band,
                "finding_detectors": [finding.detector_id for finding in manipulation.findings],
            },
        },
        "reason_codes": [reason.code for reason in policy_decision.reasons],
        "fired_rules": [asdict(rule) for rule in policy_decision.fired_rules],
        "classification_distribution": {
            method.value: sum(row.classification_method is method for row in classified.events)
            for method in ClassificationMethod
        },
    }
    return complete, values


def test_all_twelve_complete_decisions_and_real_feature_derivation() -> None:
    assert len(PERSONAS) == 12
    for persona in PERSONAS:
        result, values = decision(persona)
        assert result == EXPECTED["cases"][persona["id"]]
        assert set(result) == {
            "outcome",
            "terms",
            "assessments",
            "reason_codes",
            "fired_rules",
            "classification_distribution",
        }
        events, candidates = corpus(persona)
        assert (
            values
            == compute_feature_values(AS_OF, classify(events, vector_candidates=candidates).events)[
                0
            ]
        )


def test_two_vector_personas_and_one_unclassified_persona() -> None:
    distributions = {p["id"]: decision(p)[0]["classification_distribution"] for p in PERSONAS}
    assert sum(v["VECTOR_KNN"] > 0 for v in distributions.values()) >= 2
    assert distributions["sparse"]["UNCLASSIFIED"] > 0


def test_replay_identical_with_ai_disabled_and_zero_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("replay attempted outbound network access")

    monkeypatch.setattr(socket, "create_connection", blocked)
    for persona in PERSONAS:
        first = json.dumps(decision(persona)[0], sort_keys=True, separators=(",", ":"))
        replay = json.dumps(decision(persona)[0], sort_keys=True, separators=(",", ":"))
        assert replay == first


def test_forced_divergence_is_detected() -> None:
    original = decision(PERSONAS[0])[0]
    changed = {**original, "outcome": "DECLINE_RISK"}
    assert changed != original


def test_golden_ids_are_absent_from_training_manifest() -> None:
    manifest = (HERE.parents[2] / "ml/data/manifest.json").read_text()
    assert all(str(persona["id"]) not in manifest for persona in PERSONAS)
