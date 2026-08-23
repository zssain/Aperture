"""Mock credit-bureau source — a SIMULATED bureau behind a real interface.

A bureau file is not a stream of transactions; it's a small record (score, active
loans, recent delinquencies). This generator returns that record deterministically from
a per-applicant seed, so the same applicant always yields the same bureau reading. It is
persisted as a single BUREAU_RECORD ledger event whose payload the feature snapshot
reads — the risk scorecard itself stays cash-flow-only, so a bureau file adds a
verified source and populates the bureau signals without silently steering the score.

Real CIBIL/Experian/Equifax integrations would implement this same shape behind an
adapter; this keeps the demo self-contained and offline.
"""

import hashlib
import uuid
from dataclasses import dataclass

from app.models.enums import SourceTier, SourceType

BUREAU_SOURCE_TYPE: SourceType = SourceType.BUREAU
BUREAU_TIER: SourceTier = SourceTier.BANK_VERIFIED


@dataclass(frozen=True)
class BureauReading:
    """A simulated bureau pull. Values map 1:1 to the bureau_* feature payload keys."""

    score: int
    active_loans: int
    delinquencies_12m: int

    def to_payload(self) -> dict[str, int]:
        return {
            "bureau_score": self.score,
            "bureau_active_loans": self.active_loans,
            "bureau_delinquencies_12m": self.delinquencies_12m,
        }


def generate_bureau_reading(seed: str) -> BureauReading:
    """Deterministic, plausible bureau reading for ``seed`` (e.g. an applicant ref).

    Score lands in the healthy 690-850 band (CIBIL-like 300-900 scale), with a small
    number of active loans and rarely a delinquency - a realistic "has a bureau file"
    profile. Pure function: same seed gives an identical reading, so decisions replay."""
    digest = hashlib.sha256(f"bureau:{seed}".encode()).digest()
    score = 690 + digest[0] % 161  # 690..850
    active_loans = digest[1] % 4  # 0..3
    delinquencies_12m = 1 if digest[2] < 32 else 0  # ~1 in 8 has one recent miss
    return BureauReading(
        score=score, active_loans=active_loans, delinquencies_12m=delinquencies_12m
    )


def bureau_event_id(namespace: str) -> uuid.UUID:
    """Stable id for a seeded bureau event so re-seeding is idempotent."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"aperture-bureau:{namespace}")
