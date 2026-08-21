"""SQLAlchemy models.

Importing this package registers every table on ``Base.metadata`` (used by Alembic).
``IMMUTABLE_TABLES`` is the single source of truth for which tables carry a
BEFORE UPDATE OR DELETE immutability trigger — consumed by the migration and asserted
by the schema tests.
"""

from app.models.applicant import Applicant
from app.models.application import Application
from app.models.assessment import Assessment, ManipulationFinding
from app.models.audit import LedgerEntry
from app.models.change import DecisionChange, RedecisionAlert
from app.models.consent import Consent
from app.models.decision import Decision, DecisionReason, HumanReview, RecourseOption
from app.models.feature import FeatureSnapshot
from app.models.job import Job
from app.models.ledger import LedgerEvent
from app.models.merchant_catalog import EmbeddingCache, MerchantCatalogEntry, MerchantCatalogVersion
from app.models.model_registry import ModelVersion
from app.models.notice import Notice
from app.models.outcome import Outcome
from app.models.policy import PolicyVersion
from app.models.security import RateLimitEvent, RetentionItem
from app.models.session import UserSession
from app.models.source import SourceConnection, SourceSnapshot
from app.models.tenant import Tenant
from app.models.user import User

# Tables whose rows are immutable once written (enforced by a DB trigger).
IMMUTABLE_TABLES: tuple[str, ...] = (
    "ledger_events",
    "ledger_entries",
    "feature_snapshots",
    "assessments",
    "decisions",
    "decision_reasons",
    "decision_changes",
    "redecision_alerts",
)

__all__ = [
    "IMMUTABLE_TABLES",
    "Applicant",
    "Application",
    "Assessment",
    "Consent",
    "Decision",
    "DecisionChange",
    "DecisionReason",
    "EmbeddingCache",
    "FeatureSnapshot",
    "HumanReview",
    "Job",
    "LedgerEntry",
    "LedgerEvent",
    "ManipulationFinding",
    "MerchantCatalogEntry",
    "MerchantCatalogVersion",
    "ModelVersion",
    "Notice",
    "Outcome",
    "PolicyVersion",
    "RateLimitEvent",
    "RecourseOption",
    "RedecisionAlert",
    "RetentionItem",
    "SourceConnection",
    "SourceSnapshot",
    "Tenant",
    "User",
    "UserSession",
]
