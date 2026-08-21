"""Detector protocol, finding shape and a shared money formatter.

A :class:`Finding` is an arithmetic statement a human can check against the transactions:
it names the exact ledger events (``cited_event_ids``) whose numbers re-derive the rule,
and ``statement`` spells those numbers out in plain language. A detector returns a
:class:`DetectorResult` so it can say OK / INSUFFICIENT_DATA distinctly - a skipped or
data-starved detector is never mistaken for a clean one.
"""

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.services.manipulation.context import ManipulationContext


class DetectorStatus(enum.StrEnum):
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNAVAILABLE = "UNAVAILABLE"


class Severity(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class Finding:
    detector_id: str
    severity: str  # Severity value
    statement: str
    cited_event_ids: tuple[uuid.UUID, ...]
    confidence: float
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectorResult:
    detector_id: str
    status: DetectorStatus
    findings: tuple[Finding, ...] = ()


@runtime_checkable
class Detector(Protocol):
    detector_id: str

    def run(self, context: ManipulationContext) -> DetectorResult: ...


def format_rupees(paise: int) -> str:
    """Render integer paise as a rupee string with a numeral (never a float in state)."""
    return f"₹{paise / 100:,.2f}"
