"""Domain enumerations.

Every enum is a Python :class:`enum.StrEnum` mirrored to a native PostgreSQL enum
type. The SQLAlchemy ``Enum`` type objects are defined once here and reused by the
models so each native type is created exactly once by the migration.
"""

import enum

import sqlalchemy as sa


class UserRole(enum.StrEnum):
    CREDIT_POLICY_OWNER = "CREDIT_POLICY_OWNER"
    CREDIT_ANALYST = "CREDIT_ANALYST"
    FRAUD_REVIEWER = "FRAUD_REVIEWER"
    AUDITOR = "AUDITOR"


class ApplicationStatus(enum.StrEnum):
    AWAITING_CONSENT = "AWAITING_CONSENT"
    OPEN = "OPEN"
    PROCESSING = "PROCESSING"
    DECIDED = "DECIDED"
    REFERRED = "REFERRED"
    CLOSED = "CLOSED"


class ConsentStatus(enum.StrEnum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class SourceType(enum.StrEnum):
    BANK = "BANK"
    UPI = "UPI"
    UTILITY = "UTILITY"
    TELECOM = "TELECOM"
    BUREAU = "BUREAU"


class SourceConnectionStatus(enum.StrEnum):
    PENDING = "PENDING"
    CONNECTED = "CONNECTED"
    FAILED = "FAILED"
    REVOKED = "REVOKED"
    UNAVAILABLE = "UNAVAILABLE"


class SourceTier(enum.StrEnum):
    AA_VERIFIED = "AA_VERIFIED"
    BANK_VERIFIED = "BANK_VERIFIED"
    DECLARED_DOCUMENT = "DECLARED_DOCUMENT"


class EventDirection(enum.StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class EvidenceEventType(enum.StrEnum):
    TRANSACTION = "TRANSACTION"
    PAYMENT = "PAYMENT"
    BALANCE = "BALANCE"
    BUREAU_RECORD = "BUREAU_RECORD"
    OTHER = "OTHER"


class ClassificationMethod(enum.StrEnum):
    RULE = "RULE"
    VECTOR_KNN = "VECTOR_KNN"
    UNCLASSIFIED = "UNCLASSIFIED"


class MerchantCatalogStatus(enum.StrEnum):
    DRAFT = "draft"
    LIVE = "live"
    RETIRED = "retired"


class AssessmentKind(enum.StrEnum):
    RISK = "RISK"
    AFFORDABILITY = "AFFORDABILITY"
    COVERAGE = "COVERAGE"
    MANIPULATION = "MANIPULATION"


class CalibrationStatus(enum.StrEnum):
    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FindingSeverity(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    LIVE = "LIVE"
    ARCHIVED = "ARCHIVED"


class DecisionAction(enum.StrEnum):
    APPROVE = "APPROVE"
    APPROVE_STARTER = "APPROVE_STARTER"
    DECLINE = "DECLINE"
    REFER = "REFER"


class ReviewStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"


class ReviewOutcome(enum.StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    ESCALATED = "ESCALATED"


class ModelStatus(enum.StrEnum):
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class OutcomeLabel(enum.StrEnum):
    PERFORMING = "PERFORMING"
    DELINQUENT = "DELINQUENT"
    DEFAULTED = "DEFAULTED"
    PAID_OFF = "PAID_OFF"
    WRITTEN_OFF = "WRITTEN_OFF"


class NoticeType(enum.StrEnum):
    DECISION = "DECISION"
    RECOURSE_REQUEST = "RECOURSE_REQUEST"


class NoticeChannel(enum.StrEnum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    POST = "POST"


class NoticeStatus(enum.StrEnum):
    RENDERED = "RENDERED"
    SENT = "SENT"
    FAILED = "FAILED"


class JobType(enum.StrEnum):
    DECISION = "DECISION"
    INGEST = "INGEST"
    REDECISION = "REDECISION"
    NOTICE = "NOTICE"


class JobStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEAD = "DEAD"


def _pg_enum(py_enum: type[enum.StrEnum], name: str) -> sa.Enum:
    """Build a native PostgreSQL enum type that stores the member values."""
    return sa.Enum(
        py_enum,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


# Reusable native enum type objects (one per PostgreSQL type).
USER_ROLE = _pg_enum(UserRole, "user_role")
APPLICATION_STATUS = _pg_enum(ApplicationStatus, "application_status")
CONSENT_STATUS = _pg_enum(ConsentStatus, "consent_status")
SOURCE_TYPE = _pg_enum(SourceType, "source_type")
SOURCE_CONNECTION_STATUS = _pg_enum(SourceConnectionStatus, "source_connection_status")
SOURCE_TIER = _pg_enum(SourceTier, "source_tier")
EVENT_DIRECTION = _pg_enum(EventDirection, "event_direction")
EVIDENCE_EVENT_TYPE = _pg_enum(EvidenceEventType, "evidence_event_type")
CLASSIFICATION_METHOD = _pg_enum(ClassificationMethod, "classification_method")
MERCHANT_CATALOG_STATUS = _pg_enum(MerchantCatalogStatus, "merchant_catalog_status")
ASSESSMENT_KIND = _pg_enum(AssessmentKind, "assessment_kind")
CALIBRATION_STATUS = _pg_enum(CalibrationStatus, "calibration_status")
FINDING_SEVERITY = _pg_enum(FindingSeverity, "finding_severity")
POLICY_STATUS = _pg_enum(PolicyStatus, "policy_status")
DECISION_ACTION = _pg_enum(DecisionAction, "decision_action")
REVIEW_STATUS = _pg_enum(ReviewStatus, "review_status")
REVIEW_OUTCOME = _pg_enum(ReviewOutcome, "review_outcome")
MODEL_STATUS = _pg_enum(ModelStatus, "model_status")
OUTCOME_LABEL = _pg_enum(OutcomeLabel, "outcome_label")
NOTICE_TYPE = _pg_enum(NoticeType, "notice_type")
NOTICE_CHANNEL = _pg_enum(NoticeChannel, "notice_channel")
NOTICE_STATUS = _pg_enum(NoticeStatus, "notice_status")
JOB_TYPE = _pg_enum(JobType, "job_type")
JOB_STATUS = _pg_enum(JobStatus, "job_status")
