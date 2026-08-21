"""Manipulation engine tests.

Every positive fixture is caught; the two legitimate fixtures are not. Findings cite real
ledger events whose numbers re-derive the rule (asserted). Banding is weighted-severity
(one High outranks three Mediums). A raising detector is UNAVAILABLE, not clear; thin data
is INSUFFICIENT_DATA, not clear. Independence from the risk score is a type-check failure.
"""

import json
import os
import pathlib
import re
import uuid
from datetime import datetime
from statistics import pstdev

import pytest
from app.models.applicant import Applicant
from app.models.assessment import ManipulationFinding
from app.models.enums import AssessmentKind, EventDirection, UserRole
from app.models.feature import FeatureSnapshot
from app.schemas.assessment import ManipulationPayload
from app.services.manipulation.base import DetectorResult, Finding
from app.services.manipulation.config import (
    MANIPULATION_CONFIG_VERSION,
    get_manipulation_config,
)
from app.services.manipulation.context import (
    CrossApplicantSignal,
    DeclaredApplication,
    LedgerEventView,
    ManipulationContext,
    ProvenanceView,
    SourceMetadataView,
)
from app.services.manipulation.detectors import d5_balance_arithmetic
from app.services.manipulation.service import (
    assess,
    band_findings,
    build_context,
    persist_manipulation,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_user

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "manipulation"
_NS = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _eid(name: str) -> uuid.UUID:
    return uuid.uuid5(_NS, name)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_context(name: str) -> ManipulationContext:
    data = json.loads((FIXTURES / name).read_text())
    events = [
        LedgerEventView(
            event_id=_eid(e["id"]),
            occurred_at=_dt(e["occurred_at"]),
            direction=EventDirection(e["direction"]),
            amount_paise=e["amount_paise"],
            balance_paise=e.get("balance_paise"),
            description=e.get("description"),
            counterparty_hash=e.get("counterparty"),
            source_snapshot_id=_eid(e["source"]) if e.get("source") else None,
        )
        for e in data["events"]
    ]
    declared_raw = data.get("declared", {})
    declared = DeclaredApplication(
        application_id=None,
        occupation=declared_raw.get("occupation"),
        claimed_period_start=(
            _dt(declared_raw["claimed_period_start"])
            if declared_raw.get("claimed_period_start")
            else None
        ),
        claimed_period_end=(
            _dt(declared_raw["claimed_period_end"])
            if declared_raw.get("claimed_period_end")
            else None
        ),
    )
    sources = [
        SourceMetadataView(
            source_snapshot_id=_eid(s["id"]),
            tier=s.get("tier"),
            provenance=tuple(
                ProvenanceView(p["code"], p["severity"], p["detail"])
                for p in s.get("provenance", [])
            ),
            event_ids=tuple(_eid(x) for x in s.get("event_ids", [])),
        )
        for s in data.get("sources", [])
    ]
    cross = [
        CrossApplicantSignal(
            fingerprint_hash=c["fingerprint"],
            kind=c["kind"],
            application_count=c["application_count"],
            window_days=c["window_days"],
            event_ids=tuple(_eid(x) for x in c.get("event_ids", [])),
        )
        for c in data.get("cross_applicant", [])
    ]
    return build_context(
        as_of=_dt(data["as_of"]),
        events=events,
        declared=declared,
        sources=sources,
        cross_applicant=cross,
    )


def _findings_for(context: ManipulationContext, detector_id: str) -> list[Finding]:
    return [f for f in assess(context).findings if f.detector_id == detector_id]


# --------------------------------------------------------------------------- #
# Per-detector: positive fixture caught, legitimate fixtures not flagged.
# --------------------------------------------------------------------------- #
def test_d1_circular_flow_positive_is_high() -> None:
    result = assess(load_context("circular_flow.json"))
    assert result.band == "HIGH"
    assert result.trigger_counts["D1"] >= 1


def test_d2_inflow_burst_positive_is_high() -> None:
    result = assess(load_context("burst.json"))
    assert result.band == "HIGH"
    assert result.trigger_counts["D2"] >= 1


def test_d3_concentration_positive_is_medium() -> None:
    findings = _findings_for(load_context("concentration_gig.json"), "D3")
    assert len(findings) == 1
    assert findings[0].severity == "MEDIUM"


def test_d4_round_number_salary_positive_is_medium() -> None:
    findings = _findings_for(load_context("round_number_salary.json"), "D4")
    assert len(findings) == 1
    assert findings[0].severity == "MEDIUM"


def test_d5_balance_arithmetic_positive_is_high() -> None:
    result = assess(load_context("unbalanced.json"))
    assert result.band == "HIGH"
    assert result.trigger_counts["D5"] >= 1


def test_d6_document_provenance_positive_flags() -> None:
    findings = _findings_for(load_context("tampered_document.json"), "D6")
    assert len(findings) == 2  # editor-produced + balance-discontinuity
    assert all(f.severity == "MEDIUM" for f in findings)


def test_d7_account_age_mismatch_positive_is_medium() -> None:
    findings = _findings_for(load_context("account_age_mismatch.json"), "D7")
    assert len(findings) == 1
    assert findings[0].severity == "MEDIUM"


def test_d8_cross_applicant_reuse_positive_is_high() -> None:
    result = assess(load_context("cross_applicant_reuse.json"))
    assert result.band == "HIGH"
    assert result.trigger_counts["D8"] >= 1


@pytest.mark.parametrize("fixture", ["legitimate_lumpy_gig.json", "legitimate_seasonal.json"])
def test_legitimate_fixtures_are_clear(fixture: str) -> None:
    result = assess(load_context(fixture))
    assert result.band == "CLEAR", (fixture, [f.statement for f in result.findings])
    assert result.findings == ()


def test_legitimate_lumpy_gig_produces_clear() -> None:
    # The single most important false-positive guard: gig income is irregular by nature.
    assert assess(load_context("legitimate_lumpy_gig.json")).band == "CLEAR"


# --------------------------------------------------------------------------- #
# Citations are real and re-derive the rule.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "fixture",
    [
        "circular_flow.json",
        "burst.json",
        "concentration_gig.json",
        "round_number_salary.json",
        "unbalanced.json",
        "tampered_document.json",
        "account_age_mismatch.json",
        "cross_applicant_reuse.json",
    ],
)
def test_every_cited_event_exists_and_findings_are_cited(fixture: str) -> None:
    context = load_context(fixture)
    known = {e.event_id for e in context.events}
    findings = assess(context).findings
    assert findings  # each positive fixture produces at least one finding
    for finding in findings:
        assert finding.cited_event_ids, finding  # no finding without citations
        assert set(finding.cited_event_ids) <= known


def test_d1_citation_re_derives_circular_rule() -> None:
    context = load_context("circular_flow.json")
    cfg = get_manipulation_config(MANIPULATION_CONFIG_VERSION)["d1"]
    by_id = {e.event_id: e for e in context.events}
    finding = _findings_for(context, "D1")[0]
    cited = [by_id[i] for i in finding.cited_event_ids]
    # All cited events share one counterparty, and there are >= min_cycles return debits.
    counterparties = {e.counterparty_hash for e in cited}
    assert len(counterparties) == 1
    debits = [e for e in cited if e.direction == EventDirection.DEBIT]
    assert len(debits) >= int(cfg["min_cycles"])


def test_d5_citation_re_derives_balance_drift() -> None:
    context = load_context("unbalanced.json")
    cfg = get_manipulation_config(MANIPULATION_CONFIG_VERSION)["d5"]
    by_id = {e.event_id: e for e in context.events}
    finding = _findings_for(context, "D5")[0]
    prev, cur = (by_id[i] for i in finding.cited_event_ids)
    signed = cur.amount_paise if cur.direction == EventDirection.CREDIT else -cur.amount_paise
    assert prev.balance_paise is not None and cur.balance_paise is not None
    expected = prev.balance_paise + signed
    assert abs(cur.balance_paise - expected) > int(cfg["tolerance_paise"])


def test_d4_citation_re_derives_round_and_irregular() -> None:
    context = load_context("round_number_salary.json")
    cfg = get_manipulation_config(MANIPULATION_CONFIG_VERSION)["d4"]
    by_id = {e.event_id: e for e in context.events}
    cited = [by_id[i] for i in _findings_for(context, "D4")[0].cited_event_ids]
    multiple = int(cfg["multiple_paise"])
    round_share = sum(1 for e in cited if e.amount_paise % multiple == 0) / len(cited)
    assert round_share >= float(cfg["min_round_share"])
    variance = pstdev([e.occurred_at.day for e in cited])
    assert variance > float(cfg["salary_date_variance_days"])


def test_d3_citation_re_derives_concentration() -> None:
    context = load_context("concentration_gig.json")
    cfg = get_manipulation_config(MANIPULATION_CONFIG_VERSION)["d3"]
    by_id = {e.event_id: e for e in context.events}
    cited = [by_id[i] for i in _findings_for(context, "D3")[0].cited_event_ids]
    total = sum(e.amount_paise for e in context.events if e.direction == EventDirection.CREDIT)
    assert sum(e.amount_paise for e in cited) / total >= float(cfg["concentration_pct"])


# --------------------------------------------------------------------------- #
# Statements are arithmetic sentences: they contain actual numbers.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "fixture",
    [
        "circular_flow.json",
        "burst.json",
        "concentration_gig.json",
        "round_number_salary.json",
        "unbalanced.json",
        "account_age_mismatch.json",
        "cross_applicant_reuse.json",
    ],
)
def test_statements_contain_a_numeral(fixture: str) -> None:
    for finding in assess(load_context(fixture)).findings:
        assert re.search(r"\d", finding.statement), finding.statement


# --------------------------------------------------------------------------- #
# Banding is by weighted severity, not count.
# --------------------------------------------------------------------------- #
def _mk(severity: str, confidence: float) -> Finding:
    return Finding("Dx", severity, "value=1", (_eid("z"),), confidence, {})


def test_one_high_outranks_three_mediums() -> None:
    findings = [
        _mk("HIGH", 0.1),
        _mk("MEDIUM", 0.9),
        _mk("MEDIUM", 0.9),
        _mk("MEDIUM", 0.9),
    ]
    assert band_findings(findings, MANIPULATION_CONFIG_VERSION) == "HIGH"


def test_two_mediums_are_elevated() -> None:
    findings = [_mk("MEDIUM", 0.9), _mk("MEDIUM", 0.9)]
    assert band_findings(findings, MANIPULATION_CONFIG_VERSION) == "ELEVATED"


def test_single_medium_elevated_only_above_confidence_threshold() -> None:
    assert band_findings([_mk("MEDIUM", 0.8)], MANIPULATION_CONFIG_VERSION) == "ELEVATED"
    assert band_findings([_mk("MEDIUM", 0.5)], MANIPULATION_CONFIG_VERSION) == "CLEAR"


def test_no_findings_is_clear() -> None:
    assert band_findings([], MANIPULATION_CONFIG_VERSION) == "CLEAR"


# --------------------------------------------------------------------------- #
# Partial failure: a raising detector is UNAVAILABLE, the band comes from the rest,
# and the skip is recorded. A skipped detector is never a clear detector.
# --------------------------------------------------------------------------- #
class _RaisingDetector:
    detector_id = "D1"

    def run(self, context: ManipulationContext) -> DetectorResult:
        raise RuntimeError("detector is broken")


def test_raising_detector_is_unavailable_band_from_rest() -> None:
    context = load_context("unbalanced.json")  # D5 fires HIGH on its own
    result = assess(context, detectors=(_RaisingDetector(), d5_balance_arithmetic.DETECTOR))
    assert result.detector_statuses["D1"] == "UNAVAILABLE"
    assert "D1" in result.skipped
    assert result.trigger_counts["D1"] == 0
    assert result.band == "HIGH"  # computed from D5, the surviving detector


# --------------------------------------------------------------------------- #
# Insufficient data is INSUFFICIENT_DATA, never CLEAR.
# --------------------------------------------------------------------------- #
def test_thin_data_yields_insufficient_not_clear() -> None:
    result = assess(load_context("insufficient_data.json"))
    assert result.detector_statuses["D2"] == "INSUFFICIENT_DATA"
    assert result.detector_statuses["D7"] == "INSUFFICIENT_DATA"
    assert "D2" in result.insufficient
    assert "D7" in result.insufficient


def test_missing_balance_column_yields_insufficient_for_d5() -> None:
    # round_number_salary has income credits but no balance column at all.
    result = assess(load_context("round_number_salary.json"))
    assert result.detector_statuses["D5"] == "INSUFFICIENT_DATA"


# --------------------------------------------------------------------------- #
# Cross-applicant detection at low volume returns nothing without erroring.
# --------------------------------------------------------------------------- #
def test_cross_applicant_low_volume_no_findings_no_error() -> None:
    context = build_context(
        as_of=_dt("2026-08-01T00:00:00+00:00"),
        events=[
            LedgerEventView(
                event_id=_eid("only"),
                occurred_at=_dt("2026-07-20T00:00:00+00:00"),
                direction=EventDirection.CREDIT,
                amount_paise=250000,
                balance_paise=None,
                description="neft inward",
                counterparty_hash="cpLow",
                source_snapshot_id=None,
            )
        ],
        declared=DeclaredApplication(None, "SALARIED", None, None),
        sources=[],
        cross_applicant=[
            CrossApplicantSignal("cpLow", "COUNTERPARTY", 2, 10, (_eid("only"),)),
        ],
    )
    result = assess(context)
    assert result.detector_statuses["D8"] == "OK"
    assert result.trigger_counts["D8"] == 0


# --------------------------------------------------------------------------- #
# Determinism and engine identity.
# --------------------------------------------------------------------------- #
def test_assess_is_deterministic() -> None:
    context = load_context("circular_flow.json")
    first = assess(context)
    second = assess(context)
    assert first.band == second.band
    assert [f.statement for f in first.findings] == [f.statement for f in second.findings]
    assert first.engine_version == f"manip-v1+{MANIPULATION_CONFIG_VERSION}"


# --------------------------------------------------------------------------- #
# Independence: the context type makes passing a risk assessment a type-check failure.
# --------------------------------------------------------------------------- #
def test_risk_assessment_cannot_enter_context_type_check() -> None:
    api = pytest.importorskip("mypy.api")
    backend_dir = pathlib.Path(__file__).resolve().parent.parent
    snippet = backend_dir / "tests" / "fixtures" / "manipulation" / "_independence_probe.py"
    snippet.write_text(
        "from datetime import datetime, timezone\n"
        "from app.services.manipulation.context import (\n"
        "    ManipulationContext,\n"
        "    DeclaredApplication,\n"
        ")\n"
        "from app.services.risk.service import RiskAssessment\n"
        "\n"
        "def bad(risk: RiskAssessment) -> ManipulationContext:\n"
        "    return ManipulationContext(\n"
        "        as_of=datetime.now(timezone.utc),\n"
        "        events=(),\n"
        "        declared=DeclaredApplication(None, None, None, None),\n"
        "        sources=(),\n"
        "        cross_applicant=(),\n"
        "        income_event_ids=frozenset(),\n"
        "        config_version='manip-config-v1',\n"
        "        risk=risk,\n"
        "    )\n"
    )
    prior = os.environ.get("MYPYPATH")
    os.environ["MYPYPATH"] = str(backend_dir)
    try:
        stdout, _stderr, status = api.run(
            ["--strict", "--no-incremental", "--explicit-package-bases", str(snippet)]
        )
    finally:
        if prior is None:
            os.environ.pop("MYPYPATH", None)
        else:
            os.environ["MYPYPATH"] = prior
        snippet.unlink(missing_ok=True)
    assert status != 0, stdout
    assert 'unexpected keyword argument "risk"' in stdout.lower(), stdout


# --------------------------------------------------------------------------- #
# Persistence: the band is an immutable assessment row; findings become
# manipulation_findings rows (citation-backed) for the fraud reviewer.
# --------------------------------------------------------------------------- #
async def test_manipulation_persists_assessment_and_findings(
    db_session: AsyncSession,
) -> None:
    _user, tenant = await create_user(db_session, role=UserRole.CREDIT_ANALYST)
    applicant = Applicant(tenant_id=tenant.id, external_ref=f"a-{uuid.uuid4().hex[:8]}")
    db_session.add(applicant)
    await db_session.flush()
    snapshot = FeatureSnapshot(
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        as_of=_dt("2026-08-01T00:00:00+00:00"),
        schema_version="features-v1",
        values={"median_monthly_inflow_paise": 100000},
        null_map={},
        input_hash="hash",
    )
    db_session.add(snapshot)
    await db_session.commit()

    assessment = assess(load_context("unbalanced.json"))  # a HIGH balance finding
    row = await persist_manipulation(
        db_session,
        tenant_id=tenant.id,
        applicant_id=applicant.id,
        feature_snapshot_id=snapshot.id,
        assessment=assessment,
    )
    assert row.kind is AssessmentKind.MANIPULATION
    assert row.engine_version == assessment.engine_version
    parsed = ManipulationPayload(**row.payload)
    assert parsed.band == "HIGH"

    findings = (
        (
            await db_session.execute(
                select(ManipulationFinding).where(ManipulationFinding.assessment_id == row.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(findings) == len(assessment.findings)
    assert all(f.code == "D5" for f in findings)
