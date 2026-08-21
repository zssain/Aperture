"""Registry enforcement — the build fails if a fairness attribute reaches a model."""

import pytest
from app.registries import (
    CREDIT_FEATURES,
    FAIRNESS_ATTRIBUTES,
    FRAUD_FEATURES,
    RegistryViolationError,
    assert_registry_integrity,
)
from app.services.features.registry import FEATURE_KEYS


def test_current_registries_are_consistent() -> None:
    assert_registry_integrity()


def test_credit_and_fraud_allow_lists_are_registry_features() -> None:
    assert CREDIT_FEATURES <= FEATURE_KEYS
    assert FRAUD_FEATURES <= FEATURE_KEYS


def test_fairness_attributes_are_not_model_inputs() -> None:
    assert not (FAIRNESS_ATTRIBUTES & CREDIT_FEATURES)
    assert not (FAIRNESS_ATTRIBUTES & FRAUD_FEATURES)
    assert not (FAIRNESS_ATTRIBUTES & FEATURE_KEYS)


def test_adding_a_fairness_attribute_to_credit_fails() -> None:
    poisoned = CREDIT_FEATURES | {"age"}
    with pytest.raises(RegistryViolationError):
        assert_registry_integrity(credit=frozenset(poisoned))


def test_adding_a_fairness_attribute_to_fraud_fails() -> None:
    poisoned = FRAUD_FEATURES | {"gender"}
    with pytest.raises(RegistryViolationError):
        assert_registry_integrity(fraud=frozenset(poisoned))


def test_unknown_feature_in_allow_list_fails() -> None:
    with pytest.raises(RegistryViolationError):
        assert_registry_integrity(credit=CREDIT_FEATURES | {"not_a_real_feature"})


def test_vector_metadata_and_text_never_reach_risk_features() -> None:
    forbidden = {
        "description",
        "normalized_narration",
        "embedding",
        "match_similarity",
        "matched_entry_id",
        "vector_classified_share",
    }
    assert CREDIT_FEATURES.isdisjoint(forbidden)
