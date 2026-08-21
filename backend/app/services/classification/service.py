"""Deterministic transaction classification.

``classify`` is a pure function of the event set: the same events always produce the
same categories, rule ids and confidences (identical for training and serving).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime

from app.models.enums import ClassificationMethod, EventDirection
from app.services.classification.rules import (
    CLASSIFIER_VERSION,
    CONF_KEYWORD,
    CONF_NONE,
    CONF_RECURRENCE,
    CONF_TRANSFER,
    KEYWORD_RULES,
    RECURRENCE_AMOUNT_CV_MAX,
    RECURRENCE_MIN_OCCURRENCES,
    RECURRENCE_PERIOD_DAYS,
    RECURRENCE_PERIOD_TOLERANCE_DAYS,
    TRANSFER_ROUNDTRIP_WINDOW_DAYS,
    TxnCategory,
)


@dataclass(frozen=True)
class TxnEvent:
    """Provider-agnostic view of a ledger event used for classification/features."""

    event_id: uuid.UUID
    occurred_at: datetime
    direction: EventDirection
    amount_paise: int
    balance_paise: int | None
    description: str | None
    counterparty_hash: str | None
    source_connection_id: uuid.UUID | None
    stored_category: TxnCategory | None = None
    stored_method: ClassificationMethod | None = None
    stored_classifier_version: str | None = None
    stored_normalized_narration: str | None = None
    stored_catalog_version_id: uuid.UUID | None = None
    stored_matched_entry_id: uuid.UUID | None = None
    stored_match_similarity: float | None = None


@dataclass(frozen=True)
class ClassifiedEvent:
    event: TxnEvent
    category: TxnCategory
    rule_id: str
    confidence: float
    classification_method: ClassificationMethod = ClassificationMethod.UNCLASSIFIED
    normalized_narration: str | None = None
    catalog_version_id: uuid.UUID | None = None
    matched_entry_id: uuid.UUID | None = None
    match_similarity: float | None = None


@dataclass(frozen=True)
class VectorCandidate:
    category: TxnCategory
    similarity: float
    matched_entry_id: uuid.UUID
    catalog_version_id: uuid.UUID
    top_three_categories: tuple[TxnCategory, ...]
    normalized_narration: str


@dataclass(frozen=True)
class ClassificationSignal:
    code: str
    event_ids: tuple[uuid.UUID, ...]
    detail: str


@dataclass(frozen=True)
class ClassificationResult:
    classifier_version: str
    events: tuple[ClassifiedEvent, ...]
    signals: tuple[ClassificationSignal, ...]


def _classify_keyword(event: TxnEvent) -> ClassifiedEvent:
    if (
        event.stored_category is not None
        and event.stored_method is not None
        and event.stored_method is not ClassificationMethod.UNCLASSIFIED
    ):
        return ClassifiedEvent(
            event=event,
            category=event.stored_category,
            rule_id="RECORDED",
            confidence=0.0,
            classification_method=event.stored_method,
            normalized_narration=event.stored_normalized_narration,
            catalog_version_id=event.stored_catalog_version_id,
            matched_entry_id=event.stored_matched_entry_id,
            match_similarity=event.stored_match_similarity,
        )
    description = (event.description or "").lower()
    direction = event.direction.value
    for rule in KEYWORD_RULES:
        if rule.direction is not None and rule.direction != direction:
            continue
        if any(keyword in description for keyword in rule.keywords):
            return ClassifiedEvent(
                event,
                rule.category,
                rule.rule_id,
                CONF_KEYWORD,
                ClassificationMethod.RULE,
            )
    return ClassifiedEvent(event, TxnCategory.OTHER, "NONE", CONF_NONE)


def _amount_cv(amounts: list[int]) -> float:
    mean = sum(amounts) / len(amounts)
    if mean == 0:
        return float("inf")
    variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
    return float(variance**0.5) / mean


def _is_recurring(times: list[datetime], amounts: list[int]) -> bool:
    if len(times) < RECURRENCE_MIN_OCCURRENCES:
        return False
    ordered = sorted(times)
    gaps = [(ordered[i + 1] - ordered[i]).days for i in range(len(ordered) - 1)]
    periodic = all(
        abs(gap - RECURRENCE_PERIOD_DAYS) <= RECURRENCE_PERIOD_TOLERANCE_DAYS for gap in gaps
    )
    return periodic and _amount_cv(amounts) <= RECURRENCE_AMOUNT_CV_MAX


def _apply_recurrence(classified: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """Reclassify unlabelled recurring credits as gig income (recurrence, not keyword)."""
    by_counterparty: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(classified):
        if item.event.counterparty_hash and item.event.direction == EventDirection.CREDIT:
            by_counterparty[item.event.counterparty_hash].append(index)

    result = list(classified)
    for indices in by_counterparty.values():
        times = [classified[i].event.occurred_at for i in indices]
        amounts = [classified[i].event.amount_paise for i in indices]
        if not _is_recurring(times, amounts):
            continue
        for i in indices:
            if result[i].category is TxnCategory.OTHER:
                result[i] = replace(
                    result[i],
                    category=TxnCategory.GIG_INCOME,
                    rule_id="RECURRENCE_CREDIT",
                    confidence=CONF_RECURRENCE,
                    classification_method=ClassificationMethod.RULE,
                )
    return result


def _apply_transfer(
    classified: list[ClassifiedEvent],
) -> tuple[list[ClassifiedEvent], list[ClassificationSignal]]:
    """A counterparty seen in both directions within a short window → transfer."""
    by_counterparty: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(classified):
        if item.event.counterparty_hash:
            by_counterparty[item.event.counterparty_hash].append(index)

    result = list(classified)
    signals: list[ClassificationSignal] = []
    for indices in by_counterparty.values():
        credits = [i for i in indices if classified[i].event.direction == EventDirection.CREDIT]
        debits = [i for i in indices if classified[i].event.direction == EventDirection.DEBIT]
        if not credits or not debits:
            continue
        paired: set[int] = set()
        for ci in credits:
            for di in debits:
                delta = abs(
                    (classified[ci].event.occurred_at - classified[di].event.occurred_at).days
                )
                if delta <= TRANSFER_ROUNDTRIP_WINDOW_DAYS:
                    paired.update({ci, di})
                    signals.append(
                        ClassificationSignal(
                            code="TRANSFER_ROUNDTRIP",
                            event_ids=(
                                classified[ci].event.event_id,
                                classified[di].event.event_id,
                            ),
                            detail="Same counterparty credited and debited within window.",
                        )
                    )
        for ci in credits:
            if ci in paired:
                result[ci] = replace(
                    result[ci],
                    category=TxnCategory.TRANSFER_IN,
                    rule_id="TRANSFER_ROUNDTRIP",
                    confidence=CONF_TRANSFER,
                    classification_method=ClassificationMethod.RULE,
                )
    return result, signals


def classify(
    events: list[TxnEvent],
    *,
    vector_candidates: dict[uuid.UUID, VectorCandidate] | None = None,
    similarity_floor: float = 0.82,
) -> ClassificationResult:
    ordered = sorted(events, key=lambda e: (e.occurred_at, str(e.event_id)))
    classified = [_classify_keyword(event) for event in ordered]
    classified = _apply_recurrence(classified)
    classified, signals = _apply_transfer(classified)
    candidates = vector_candidates or {}
    resolved: list[ClassifiedEvent] = []
    for item in classified:
        # A persisted tier-1 or tier-2 trace is immutable replay input. A newer
        # catalogue candidate must never overwrite the recorded classification.
        if item.classification_method is not ClassificationMethod.UNCLASSIFIED:
            resolved.append(item)
            continue
        candidate = candidates.get(item.event.event_id)
        if candidate is None:
            resolved.append(item)
            continue
        agreement = candidate.top_three_categories.count(candidate.category) >= 2
        if candidate.similarity < similarity_floor or not agreement:
            resolved.append(replace(item, normalized_narration=candidate.normalized_narration))
            continue
        resolved.append(
            replace(
                item,
                category=candidate.category,
                rule_id="VECTOR_KNN",
                confidence=0.0,
                classification_method=ClassificationMethod.VECTOR_KNN,
                normalized_narration=candidate.normalized_narration,
                catalog_version_id=candidate.catalog_version_id,
                matched_entry_id=candidate.matched_entry_id,
                match_similarity=candidate.similarity,
            )
        )
    signals.sort(key=lambda s: tuple(str(i) for i in s.event_ids))
    recorded_versions = {
        event.stored_classifier_version
        for event in events
        if event.stored_classifier_version is not None
    }
    return ClassificationResult(
        classifier_version=(
            next(iter(recorded_versions)) if len(recorded_versions) == 1 else CLASSIFIER_VERSION
        ),
        events=tuple(resolved),
        signals=tuple(signals),
    )
