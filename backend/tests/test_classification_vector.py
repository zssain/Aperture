import uuid
from datetime import UTC, datetime

from app.models.enums import ClassificationMethod, EventDirection
from app.services.classification.rules import TxnCategory
from app.services.classification.service import TxnEvent, VectorCandidate, classify
from app.services.classification.vector import normalize_narration


def event(description: str) -> TxnEvent:
    return TxnEvent(
        uuid.uuid4(),
        datetime(2026, 8, 1, tzinfo=UTC),
        EventDirection.DEBIT,
        10_000,
        None,
        description,
        "cp",
        None,
    )


def candidate(item: TxnEvent, similarity: float, votes: tuple[TxnCategory, ...]) -> VectorCandidate:
    return VectorCandidate(
        TxnCategory.UTILITY,
        similarity,
        uuid.uuid4(),
        uuid.uuid4(),
        votes,
        normalize_narration(item.description or ""),
    )


def test_tier_one_always_wins_over_disagreeing_vector() -> None:
    item = event("electricity utility bill")
    match = candidate(item, 0.99, (TxnCategory.MERCHANT,) * 3)
    result = classify([item], vector_candidates={item.event_id: match})
    assert result.events[0].category is TxnCategory.UTILITY
    assert result.events[0].classification_method is ClassificationMethod.RULE


def test_below_floor_and_disagreement_are_unclassified() -> None:
    low = event("bescom ref 998811")
    disagree = event("mysterious vendor")
    candidates = {
        low.event_id: candidate(low, 0.81, (TxnCategory.UTILITY,) * 3),
        disagree.event_id: candidate(
            disagree,
            0.95,
            (TxnCategory.UTILITY, TxnCategory.MERCHANT, TxnCategory.EMI),
        ),
    }
    result = classify([low, disagree], vector_candidates=candidates)
    assert all(
        row.classification_method is ClassificationMethod.UNCLASSIFIED for row in result.events
    )


def test_accepted_vector_records_complete_trace() -> None:
    item = event("bescom 778899")
    match = candidate(item, 0.91, (TxnCategory.UTILITY,) * 3)
    result = classify([item], vector_candidates={item.event_id: match}).events[0]
    assert result.classification_method is ClassificationMethod.VECTOR_KNN
    assert result.match_similarity == 0.91
    assert result.matched_entry_id == match.matched_entry_id
    assert result.catalog_version_id == match.catalog_version_id


def test_normalizer_preserves_mixed_indic_scripts() -> None:
    assert "बिजली" in normalize_narration("UPI/123456/बिजली TNEB தமிழ்")
    assert "தமிழ்" in normalize_narration("UPI/123456/बिजली TNEB தமிழ்")
