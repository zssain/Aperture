"""Legally explicit retention classes."""

import enum
from datetime import timedelta


class RetentionClass(enum.StrEnum):
    RAW_EVIDENCE = "RAW_EVIDENCE"
    DERIVED_FEATURES = "DERIVED_FEATURES"
    DECISION_RECORD = "DECISION_RECORD"
    COMMUNICATION = "COMMUNICATION"


RETENTION_WINDOWS = {
    RetentionClass.RAW_EVIDENCE: timedelta(days=90),
    RetentionClass.DERIVED_FEATURES: timedelta(days=365 * 2),
    RetentionClass.DECISION_RECORD: timedelta(days=365 * 7),
    RetentionClass.COMMUNICATION: timedelta(days=365 * 2),
}
