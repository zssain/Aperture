"""Evidence coverage scoring — a pure, versioned, hand-checkable function.

``assess_coverage`` returns a 0-100 score, a band, a full component breakdown (each with
its own contribution), and ``missing_sources`` whose ``coverage_delta`` is computed by
actually re-scoring with a representative source added — so the recourse engine can rely
on it exactly. No model, no I/O.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.models.enums import AssessmentKind, CalibrationStatus, SourceTier, SourceType
from app.models.feature import FeatureSnapshot
from app.schemas.assessment import CoveragePayload
from app.services.coverage.weights import (
    COVERAGE_WEIGHTS_VERSION,
    get_coverage_weights,
)

COVERAGE_ENGINE = "coverage-v1"


@dataclass(frozen=True)
class SourceEvidence:
    """A purified view of a source snapshot for coverage scoring (plain object)."""

    source_type: SourceType
    tier: SourceTier
    latest_event_at: datetime


@dataclass(frozen=True)
class CoverageComponent:
    name: str
    weight: int
    fraction: float
    contribution: float
    detail: str


@dataclass(frozen=True)
class MissingSource:
    source_type: str
    why: str
    coverage_delta: int


@dataclass(frozen=True)
class CoverageAssessment:
    score: int
    band: str
    components: list[CoverageComponent]
    missing_sources: list[MissingSource]
    weights_version: str
    engine_version: str


def _tier_weight(weights: dict[str, Any], tier: SourceTier) -> float:
    return float(weights["tier_weights"][tier.value])


def _component_fractions(
    values: dict[str, Any],
    null_map: dict[str, Any],
    as_of: datetime,
    sources: list[SourceEvidence],
    weights: dict[str, Any],
) -> dict[str, tuple[float, str]]:
    """Return {component: (fraction 0..1, human detail)}."""
    fractions: dict[str, tuple[float, str]] = {}

    # Tier — the best-available evidential tier.
    if sources:
        best = max(_tier_weight(weights, s.tier) for s in sources)
        best_tier = max(sources, key=lambda s: _tier_weight(weights, s.tier)).tier
        fractions["tier"] = (best, f"best tier {best_tier.value}")
    else:
        fractions["tier"] = (0.0, "no sources")

    # Verification — is any evidence from a verified (AA/bank) source? This rewards
    # HAVING verified evidence without penalising additional diverse sources (that is
    # the diversity component's job).
    if sources:
        has_verified = any(
            s.tier in (SourceTier.AA_VERIFIED, SourceTier.BANK_VERIFIED) for s in sources
        )
        frac = 1.0 if has_verified else 0.5
        fractions["verification"] = (
            frac,
            "verified source present" if has_verified else "declared documents only",
        )
    else:
        fractions["verification"] = (0.0, "no sources")

    # History depth vs the required window.
    depth = values.get("history_depth_days")
    required = weights["required_window_days"]
    if depth is None:
        fractions["history_depth"] = (0.0, "history depth unavailable")
    else:
        frac = min(1.0, depth / required)
        fractions["history_depth"] = (frac, f"{depth}/{required} days")

    # Freshness — days since the most recent event across sources.
    if sources:
        latest = max(s.latest_event_at for s in sources)
        days = (as_of - latest).days
        full = weights["freshness"]["full_days"]
        zero = weights["freshness"]["zero_days"]
        if days <= full:
            frac = 1.0
        elif days >= zero:
            frac = 0.0
        else:
            frac = (zero - days) / (zero - full)
        fractions["freshness"] = (frac, f"latest event {days} days old")
    else:
        fractions["freshness"] = (0.0, "no sources")

    # Diversity — distinct types, diminishing returns for extra of the same type.
    if sources:
        counts: dict[str, int] = {}
        for source in sources:
            counts[source.source_type.value] = counts.get(source.source_type.value, 0) + 1
        decay = weights["diversity"]["decay"]
        target = weights["diversity"]["target"]
        effective = sum(sum(decay**i for i in range(count)) for count in counts.values())
        frac = min(1.0, effective / target)
        fractions["diversity"] = (frac, f"effective diversity {effective:.3f}/{target}")
    else:
        fractions["diversity"] = (0.0, "no sources")

    # Completeness — required features present (not null) in the snapshot.
    required_features = weights["required_features"]
    present = sum(1 for key in required_features if key not in null_map)
    frac = present / len(required_features) if required_features else 0.0
    unclassified = float(values.get("unclassified_inflow_share", 0.0))
    frac *= 1.0 - min(1.0, max(0.0, unclassified))
    fractions["completeness"] = (
        frac,
        f"{present}/{len(required_features)} required features; "
        f"unclassified inflow share {unclassified:.3f}",
    )

    return fractions


def _score(
    values: dict[str, Any],
    null_map: dict[str, Any],
    as_of: datetime,
    sources: list[SourceEvidence],
    weights: dict[str, Any],
) -> tuple[int, list[CoverageComponent]]:
    fractions = _component_fractions(values, null_map, as_of, sources, weights)
    component_weights = weights["component_weights"]
    components: list[CoverageComponent] = []
    total = 0.0
    for name, weight in component_weights.items():
        fraction, detail = fractions[name]
        contribution = weight * fraction
        total += contribution
        components.append(
            CoverageComponent(
                name=name,
                weight=weight,
                fraction=round(fraction, 6),
                contribution=round(contribution, 6),
                detail=detail,
            )
        )
    return round(total), components


def _band(score: int, diversity_fraction: float, weights: dict[str, Any]) -> str:
    thresholds = weights["band_thresholds"]
    high_gated = weights.get("high_requires_full_diversity", False)
    if score >= thresholds["HIGH"] and not (high_gated and diversity_fraction < 1.0):
        return "HIGH"
    if score >= thresholds["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def _diversity_fraction(components: list[CoverageComponent]) -> float:
    for component in components:
        if component.name == "diversity":
            return component.fraction
    return 0.0


def assess_coverage(
    feature_snapshot: FeatureSnapshot,
    source_snapshots: list[SourceEvidence],
    weights_version: str = COVERAGE_WEIGHTS_VERSION,
) -> CoverageAssessment:
    weights = get_coverage_weights(weights_version)
    values = feature_snapshot.values
    null_map = feature_snapshot.null_map
    as_of = feature_snapshot.as_of

    score, components = _score(values, null_map, as_of, source_snapshots, weights)

    present_types = {s.source_type for s in source_snapshots}
    missing: list[MissingSource] = []
    for type_name, spec in weights["canonical_sources"].items():
        if SourceType(type_name) in present_types:
            continue
        representative = SourceEvidence(
            source_type=SourceType(type_name),
            tier=SourceTier(spec["tier"]),
            latest_event_at=as_of - timedelta(days=spec["freshness_days"]),
        )
        with_source, _ = _score(
            values, null_map, as_of, [*source_snapshots, representative], weights
        )
        missing.append(
            MissingSource(
                source_type=type_name,
                why=spec["why"],
                coverage_delta=with_source - score,
            )
        )

    return CoverageAssessment(
        score=score,
        band=_band(score, _diversity_fraction(components), weights),
        components=components,
        missing_sources=missing,
        weights_version=weights_version,
        engine_version=f"{COVERAGE_ENGINE}+{weights_version}",
    )


def coverage_payload(assessment: CoverageAssessment) -> CoveragePayload:
    return CoveragePayload(
        score=assessment.score,
        band=assessment.band,
        weights_version=assessment.weights_version,
        components=[
            {
                "name": c.name,
                "weight": c.weight,
                "fraction": c.fraction,
                "contribution": c.contribution,
                "detail": c.detail,
            }
            for c in assessment.components
        ],
        missing_sources=[
            {
                "source_type": m.source_type,
                "why": m.why,
                "coverage_delta": m.coverage_delta,
            }
            for m in assessment.missing_sources
        ],
    )


async def persist_coverage(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    feature_snapshot: FeatureSnapshot,
    assessment: CoverageAssessment,
) -> Assessment:
    payload = coverage_payload(assessment)
    row = Assessment(
        tenant_id=tenant_id,
        applicant_id=feature_snapshot.applicant_id,
        feature_snapshot_id=feature_snapshot.id,
        kind=AssessmentKind.COVERAGE,
        payload=payload.model_dump(mode="json"),
        engine_version=assessment.engine_version,
        calibration_status=CalibrationStatus.NOT_APPLICABLE,
    )
    session.add(row)
    await session.commit()
    return row
