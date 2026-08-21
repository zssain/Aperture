import uuid
from datetime import UTC, datetime

from app.models.enums import ClassificationMethod, EventDirection
from app.services.classification.rules import TxnCategory
from app.services.classification.service import TxnEvent, VectorCandidate, classify
from app.services.classification.vector import normalize_narration


def test_200_string_benchmark_reports_tier_distribution() -> None:
    events: list[TxnEvent] = []
    candidates: dict[uuid.UUID, VectorCandidate] = {}
    for index in range(200):
        if index < 80:
            text, direction = f"salary payroll credit {index}", EventDirection.CREDIT
        elif index < 160:
            text, direction = f"RZPY ZOMATO PARTNER REMIT {index}", EventDirection.CREDIT
        else:
            text, direction = f"ZXQ NOISE {index}", EventDirection.CREDIT
        event = TxnEvent(
            uuid.uuid5(uuid.NAMESPACE_URL, f"benchmark:{index}"),
            datetime(2026, 8, 1, tzinfo=UTC),
            direction,
            100_000,
            None,
            text,
            f"cp-{index}",
            None,
        )
        events.append(event)
        if 80 <= index < 160:
            candidates[event.event_id] = VectorCandidate(
                TxnCategory.GIG_INCOME,
                0.9,
                uuid.uuid5(uuid.NAMESPACE_URL, f"catalog-entry:{index}"),
                uuid.UUID(int=9),
                (TxnCategory.GIG_INCOME,) * 3,
                normalize_narration(text),
            )
    result = classify(events, vector_candidates=candidates)
    counts = {
        method: sum(row.classification_method is method for row in result.events)
        for method in ClassificationMethod
    }
    assert counts == {
        ClassificationMethod.RULE: 80,
        ClassificationMethod.VECTOR_KNN: 80,
        ClassificationMethod.UNCLASSIFIED: 40,
    }
