"""Stored classification traces win over later catalogue versions during replay."""

import uuid
from datetime import UTC, datetime

from app.models.enums import ClassificationMethod, EventDirection
from app.services.classification.rules import TxnCategory
from app.services.classification.service import TxnEvent, VectorCandidate, classify


def test_catalogue_bump_changes_new_events_but_not_recorded_events() -> None:
    old_catalog = uuid.uuid4()
    new_catalog = uuid.uuid4()
    old_entry = uuid.uuid4()
    old = TxnEvent(
        event_id=uuid.uuid4(),
        occurred_at=datetime(2026, 8, 1, tzinfo=UTC),
        direction=EventDirection.CREDIT,
        amount_paise=100_000,
        balance_paise=None,
        description="opaque remittance",
        counterparty_hash="old",
        source_connection_id=None,
        stored_category=TxnCategory.GIG_INCOME,
        stored_method=ClassificationMethod.VECTOR_KNN,
        stored_classifier_version="clf-v2",
        stored_normalized_narration="opaque remittance",
        stored_catalog_version_id=old_catalog,
        stored_matched_entry_id=old_entry,
        stored_match_similarity=0.9,
    )
    replacement = VectorCandidate(
        TxnCategory.SALARY,
        0.99,
        uuid.uuid4(),
        new_catalog,
        (TxnCategory.SALARY,) * 3,
        "opaque remittance",
    )
    replayed = classify([old], vector_candidates={old.event_id: replacement}).events[0]
    assert replayed.category is TxnCategory.GIG_INCOME
    assert replayed.catalog_version_id == old_catalog
    fresh = TxnEvent(
        event_id=uuid.uuid4(),
        occurred_at=old.occurred_at,
        direction=old.direction,
        amount_paise=old.amount_paise,
        balance_paise=None,
        description=old.description,
        counterparty_hash="new",
        source_connection_id=None,
    )
    classified = classify([fresh], vector_candidates={fresh.event_id: replacement}).events[0]
    assert classified.category is TxnCategory.SALARY
    assert classified.catalog_version_id == new_catalog
