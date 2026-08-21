from app.services.retention.policy import RETENTION_WINDOWS, RetentionClass


def test_retention_classes_are_explicit_and_decision_is_longest() -> None:
    assert RETENTION_WINDOWS[RetentionClass.RAW_EVIDENCE].days == 90
    assert RETENTION_WINDOWS[RetentionClass.DERIVED_FEATURES].days == 730
    assert RETENTION_WINDOWS[RetentionClass.COMMUNICATION].days == 730
    assert RETENTION_WINDOWS[RetentionClass.DECISION_RECORD].days == 2555


def test_merchant_catalogue_is_not_an_applicant_retention_class() -> None:
    assert "MERCHANT_CATALOG" not in RetentionClass.__members__
