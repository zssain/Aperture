"""Registry allow-lists and their enforcement.

``assert_registry_integrity`` fails the build if a model allow-list references an
unknown feature or if any fairness attribute leaks into a model allow-list.
"""

from app.registries.credit_features import CREDIT_FEATURES
from app.registries.fairness_attributes import FAIRNESS_ATTRIBUTES
from app.registries.fraud_features import FRAUD_FEATURES
from app.services.features.registry import FEATURE_KEYS

__all__ = [
    "CREDIT_FEATURES",
    "FAIRNESS_ATTRIBUTES",
    "FRAUD_FEATURES",
    "RegistryViolationError",
    "assert_registry_integrity",
]


class RegistryViolationError(Exception):
    pass


def assert_registry_integrity(
    credit: frozenset[str] = CREDIT_FEATURES,
    fraud: frozenset[str] = FRAUD_FEATURES,
    fairness: frozenset[str] = FAIRNESS_ATTRIBUTES,
) -> None:
    unknown_credit = credit - FEATURE_KEYS
    if unknown_credit:
        raise RegistryViolationError(
            f"credit allow-list references non-registry features: {sorted(unknown_credit)}"
        )
    unknown_fraud = fraud - FEATURE_KEYS
    if unknown_fraud:
        raise RegistryViolationError(
            f"fraud allow-list references non-registry features: {sorted(unknown_fraud)}"
        )
    leaked = fairness & (credit | fraud)
    if leaked:
        raise RegistryViolationError(
            f"fairness attributes leaked into a model allow-list: {sorted(leaked)}"
        )
    fairness_as_feature = fairness & FEATURE_KEYS
    if fairness_as_feature:
        raise RegistryViolationError(
            f"fairness attributes must not be registry features: {sorted(fairness_as_feature)}"
        )
