"""The exception-queue service.

Every view, filter, sort and page of this queue is resolved in ONE round-trip of set-based
SQL - the client never receives the full set (that is what keeps it responsive at 10k+ rows
and stable while cases resolve underneath it). Two things are worth reading closely:

- ``project_routed_because`` turns a decision's ordered ``fired_rules`` - plus the assessment
  values and the policy thresholds that were in force - into the short phrase that the analyst
  reads in the second column ("Coverage 41 (min 55)", "Verification ELEVATED / circular flow
  x3"). It is a pure function so a test can assert it matches the gate that actually fired.
- Pagination is keyset (cursor), never offset: the cursor is the last row's (sort value, id),
  so inserting or resolving rows cannot shift the page under the reader.
"""

import base64
import binascii
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    Float,
    Integer,
    Select,
    String,
    and_,
    cast,
    func,
    literal,
    or_,
    select,
    true,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.assessment import Assessment
from app.models.change import DecisionChange
from app.models.decision import Decision, HumanReview
from app.models.enums import ApplicationStatus, AssessmentKind, ReviewStatus
from app.models.policy import PolicyVersion
from app.schemas.queue import (
    DecisionChangeOut,
    MetricOut,
    QueueResponse,
    QueueRowOut,
    RecommendationOut,
    RoutedBecauseOut,
)

# --------------------------------------------------------------------------- #
# Views and role scoping. A view the role cannot access is ABSENT from the response
# (counts + tabs), never returned and hidden client-side.
# --------------------------------------------------------------------------- #
VIEWS: tuple[str, ...] = (
    "my-exceptions",
    "fraud-review",
    "evidence-needed",
    "newly-eligible",
    "deterioration",
    "all-decisions",
    "qa-sample",
)

# Fraud is walled off from credit (invariant 5): a fraud reviewer sees the fraud queue and the
# read-only ledger, nothing else; credit roles never see the fraud queue.
_ROLE_VIEWS: dict[str, tuple[str, ...]] = {
    "CREDIT_ANALYST": (
        "my-exceptions",
        "evidence-needed",
        "newly-eligible",
        "deterioration",
        "all-decisions",
    ),
    "FRAUD_REVIEWER": ("fraud-review", "all-decisions"),
    "CREDIT_POLICY_OWNER": (
        "my-exceptions",
        "evidence-needed",
        "newly-eligible",
        "deterioration",
        "all-decisions",
        "qa-sample",
    ),
    "AUDITOR": ("all-decisions", "qa-sample"),
}

# Where each role lands when no view is named. A fraud reviewer lands on fraud-review.
_DEFAULT_VIEW: dict[str, str] = {
    "CREDIT_ANALYST": "my-exceptions",
    "FRAUD_REVIEWER": "fraud-review",
    "CREDIT_POLICY_OWNER": "my-exceptions",
    "AUDITOR": "all-decisions",
}

# Manipulation detector ids -> the short human phrase used in routed_because.
DETECTOR_LABELS: dict[str, str] = {
    "D1": "circular flow",
    "D2": "inflow burst",
    "D3": "counterparty concentration",
    "D4": "round-number salary",
    "D5": "balance arithmetic",
    "D6": "document provenance",
    "D7": "account age mismatch",
    "D8": "cross-applicant reuse",
}

# The decisive gate's outcome that means "this is a fraud case" (kept out of my-exceptions).
_FRAUD_OUTCOMES: tuple[str, ...] = ("FRAUD_REVIEW", "REVIEW_FRAUD")

# Deterministic QA sample: ~1 in this many automated decisions (stable per decision id).
QA_SAMPLE_MODULUS = 20

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_MIDDOT = "·"  # middle dot separator used in routed_because phrases
_TIMES = "×"  # multiplication sign for "xN" finding counts


class QueueAccessError(Exception):
    """The role may not see the requested view -> the route returns 403."""

    def __init__(self, view: str) -> None:
        super().__init__(f"view not accessible: {view}")
        self.view = view


def accessible_views(role: str) -> tuple[str, ...]:
    allowed = set(_ROLE_VIEWS.get(role, ()))
    return tuple(v for v in VIEWS if v in allowed)


def default_view(role: str) -> str:
    return _DEFAULT_VIEW.get(role, "all-decisions")


# --------------------------------------------------------------------------- #
# Column expressions. Assessment values live as JSONB payloads on the ``assessments`` rows
# over the decision's feature snapshot; the policy thresholds live on the policy version.
# These are module-level so the row query, the filters, the sort and the cursor all read the
# SAME expressions and can never drift.
# --------------------------------------------------------------------------- #
_RiskA = aliased(Assessment)
_CovA = aliased(Assessment)
_ManipA = aliased(Assessment)
_ChangeFilter = aliased(DecisionChange)

_pd_expr: ColumnElement[float] = cast(_RiskA.payload["pd"].astext, Float)
_cov_expr: ColumnElement[int] = cast(_CovA.payload["score"].astext, Integer)
_band_expr: ColumnElement[str] = _ManipA.payload["band"].astext
_amount_expr: ColumnElement[int] = func.coalesce(Application.requested_amount_paise, 0)
_waiting_secs: ColumnElement[Any] = func.extract("epoch", func.now() - Decision.decided_at)

# The decisive gate is the first fired rule (the gate that broke the ordered ladder).
_gate_outcome: ColumnElement[str] = Decision.fired_rules[0]["outcome"].astext


def _resolved_exists() -> ColumnElement[bool]:
    return (
        select(HumanReview.id)
        .where(
            HumanReview.decision_id == Decision.id,
            HumanReview.status == ReviewStatus.RESOLVED,
        )
        .exists()
    )


def _unresolved() -> ColumnElement[bool]:
    # A human-routed decision is unresolved until it is superseded, finalised, or a review
    # closes it. is_final is False for HUMAN routings by construction.
    return and_(
        Decision.superseded_by.is_(None),
        Decision.is_final.is_(False),
        ~_resolved_exists(),
    )


def _sample_predicate() -> ColumnElement[bool]:
    bucket = func.mod(func.abs(func.hashtext(cast(Decision.id, String))), QA_SAMPLE_MODULUS)
    return bucket == 0


def _view_predicate(view: str) -> ColumnElement[bool]:
    """The SQL boolean that defines a view. Shared by row listing and count aggregation."""
    if view == "my-exceptions":
        return and_(
            Decision.routing == "HUMAN",
            _gate_outcome.notin_(_FRAUD_OUTCOMES),
            _unresolved(),
        )
    if view == "fraud-review":
        return and_(_gate_outcome.in_(_FRAUD_OUTCOMES), _unresolved())
    if view == "evidence-needed":
        return and_(_gate_outcome == "REVIEW_EVIDENCE", _unresolved())
    if view in ("newly-eligible", "deterioration"):
        direction = "IMPROVED" if view == "newly-eligible" else "WORSENED"
        since = datetime.now(UTC) - timedelta(days=settings.decision_change_window_days)
        return (
            select(_ChangeFilter.id)
            .where(
                _ChangeFilter.tenant_id == Decision.tenant_id,
                _ChangeFilter.new_decision_id == Decision.id,
                _ChangeFilter.direction == direction,
                _ChangeFilter.detected_at >= since,
            )
            .correlate(Decision)
            .exists()
        )
    if view == "all-decisions":
        return true()
    if view == "qa-sample":
        return and_(Decision.routing == "AUTOMATED", _sample_predicate())
    raise QueueAccessError(view)


# --------------------------------------------------------------------------- #
# Sorting + keyset cursor.
# --------------------------------------------------------------------------- #
_SORTS: tuple[str, ...] = (
    "waiting",
    "-waiting",
    "pd",
    "-pd",
    "coverage",
    "-coverage",
    "amount",
    "-amount",
)


def _order_col(sort: str) -> Any:
    base = sort.lstrip("-")
    if base == "waiting":
        return Decision.decided_at
    if base == "pd":
        return func.coalesce(_pd_expr, 1.0)
    if base == "coverage":
        return func.coalesce(_cov_expr, -1)
    if base == "amount":
        return _amount_expr
    raise QueueAccessError(sort)


def _is_desc(sort: str) -> bool:
    return sort.startswith("-")


def _encode_cursor(sort: str, value: Any, decision_id: uuid.UUID) -> str:
    raw = {
        "f": sort,
        "v": value.isoformat() if isinstance(value, datetime) else str(value),
        "id": str(decision_id),
    }
    return base64.urlsafe_b64encode(json.dumps(raw).encode()).decode()


def _decode_cursor(cursor: str, sort: str) -> tuple[Any, uuid.UUID] | None:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if raw.get("f") != sort:
            return None  # sort changed since the cursor was issued -> start fresh
        base = sort.lstrip("-")
        text = str(raw["v"])
        value: Any
        if base == "waiting":
            value = datetime.fromisoformat(text)
        elif base == "pd":
            value = float(text)
        else:
            value = int(text)
        return value, uuid.UUID(str(raw["id"]))
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- #
# routed_because projection - the second column, and the point of the whole screen.
# --------------------------------------------------------------------------- #
def _fmt_pd(pd: float | None) -> str:
    return f"{pd:.3f}" if pd is not None else "n/a"


def _top_detector(trigger_counts: dict[str, Any] | None) -> tuple[str, int] | None:
    if not trigger_counts:
        return None
    best_id: str | None = None
    best_count = 0
    for detector_id, count in trigger_counts.items():
        try:
            value = int(count)
        except (TypeError, ValueError):
            continue
        if value > best_count:
            best_count = value
            best_id = detector_id
    if best_id is None or best_count == 0:
        return None
    return DETECTOR_LABELS.get(best_id, best_id), best_count


def project_routed_because(
    *,
    fired_rules: Sequence[dict[str, Any]],
    pd: float | None,
    coverage_score: int | None,
    trigger_counts: dict[str, Any] | None,
    rules: dict[str, Any],
) -> RoutedBecauseOut:
    """Pure projection of the decisive fired rule into a numbered, human phrase.

    The phrase always matches the gate that actually determined the outcome; when an approval
    was forced to a human by the mandatory-review ceiling (rule 10), THAT is the reason the
    case is in the queue and the phrase says so.
    """
    gate: dict[str, Any] | None = None
    mandatory = False
    exploration = False
    for rule in fired_rules:
        number = int(rule.get("number", 0))
        if 1 <= number <= 9 and gate is None:
            gate = rule
        elif number == 10:
            mandatory = True
        elif number == 11:
            exploration = True

    if mandatory:
        ceiling = int(rules.get("mandatory_review_ceiling_paise", 0))
        return RoutedBecauseOut(
            text=f"Mandatory review {_MIDDOT} over ₹{ceiling // 100:,}",
            rule_number=10,
        )

    if gate is None:
        return RoutedBecauseOut(text="System unavailable", rule_number=0)

    name = str(gate.get("name", ""))
    number = int(gate.get("number", 0))
    min_coverage = int(rules.get("min_coverage", 0))
    pd_decline = float(rules.get("pd_decline_threshold", 0.0))
    margin = float(rules.get("exploration_margin", 0.0))

    if name == "manipulation_high":
        detector = _top_detector(trigger_counts)
        suffix = f" {_MIDDOT} {detector[0]} {_TIMES}{detector[1]}" if detector else ""
        return RoutedBecauseOut(text=f"Fraud HIGH{suffix}", rule_number=number)
    if name == "manipulation_elevated":
        detector = _top_detector(trigger_counts)
        suffix = f" {_MIDDOT} {detector[0]} {_TIMES}{detector[1]}" if detector else ""
        return RoutedBecauseOut(text=f"Verification ELEVATED{suffix}", rule_number=number)
    if name == "coverage_below_min":
        score = coverage_score if coverage_score is not None else 0
        return RoutedBecauseOut(text=f"Coverage {score} (min {min_coverage})", rule_number=number)
    if name == "affordability_fail":
        return RoutedBecauseOut(text="Affordability FAIL", rule_number=number)
    if name == "affordability_indeterminate":
        return RoutedBecauseOut(text="Affordability indeterminate", rule_number=number)
    if name == "pd_decline":
        near = pd is not None and pd <= pd_decline + margin
        if near:
            text = f"Near boundary PD {_fmt_pd(pd)} (threshold {pd_decline:.3f})"
        else:
            text = f"Risk PD {_fmt_pd(pd)} (declines above {pd_decline:.3f})"
        return RoutedBecauseOut(text=text, rule_number=number)
    if name == "approve_enhanced":
        return RoutedBecauseOut(
            text=f"Approved enhanced {_MIDDOT} PD {_fmt_pd(pd)}", rule_number=number
        )
    if name == "approve_standard":
        return RoutedBecauseOut(
            text=f"Approved standard {_MIDDOT} PD {_fmt_pd(pd)}", rule_number=number
        )
    if name == "approve_starter":
        tail = f" {_MIDDOT} exploration" if exploration else ""
        return RoutedBecauseOut(text=f"Approved starter{tail}", rule_number=number)
    return RoutedBecauseOut(text=name or "Routed", rule_number=number)


# --------------------------------------------------------------------------- #
# Row projection helpers.
# --------------------------------------------------------------------------- #
def _pd_metric(pd: float | None, calibration: str | None) -> MetricOut:
    if pd is None:
        return MetricOut(value=None, status="unavailable")
    if calibration == "UNCALIBRATED":
        return MetricOut(value=pd, status="uncalibrated")
    if calibration == "CALIBRATED":
        return MetricOut(value=pd, status="measured")
    return MetricOut(value=pd, status="measured")


def _coverage_metric(score: int | None) -> MetricOut:
    if score is None:
        return MetricOut(value=None, status="unavailable")
    return MetricOut(value=float(score), status="measured")


def _recommendation(row: Any) -> RecommendationOut:
    terms: dict[str, Any] = dict(row.terms or {})
    band = terms.get("band")
    return RecommendationOut(
        action=str(row.action.value if hasattr(row.action, "value") else row.action),
        band=str(band) if band else None,
        approved_limit_paise=row.approved_limit_paise,
        tenor_months=terms.get("approved_tenor_months") or row.requested_tenor_months,
        annual_rate_bps=terms.get("annual_rate_bps"),
    )


def _row_out(row: Any) -> QueueRowOut:
    return QueueRowOut(
        id=row.id,
        application_id=row.application_id,
        applicant_name=row.display_name or row.external_ref,
        applicant_ref=row.external_ref,
        amount_paise=row.requested_amount_paise,
        routed_because=project_routed_because(
            fired_rules=list(row.fired_rules or []),
            pd=row.pd,
            coverage_score=row.coverage,
            trigger_counts=row.trigger_counts,
            rules=dict(row.rules or {}),
        ),
        recommendation=_recommendation(row),
        pd=_pd_metric(row.pd, row.calibration_status),
        coverage=_coverage_metric(row.coverage),
        verification=row.verification or "UNKNOWN",
        waiting_seconds=int(row.waiting_seconds or 0),
        decided_at=row.decided_at,
        change=(
            DecisionChangeOut(
                direction=row.change_direction,
                previous_band=row.previous_band,
                new_band=row.new_band,
                previous_outcome=row.previous_outcome,
                new_outcome=row.new_outcome,
                human_action_protected=bool(row.human_action_protected),
            )
            if row.change_direction is not None
            else None
        ),
    )


def _pending_evidence_row_out(row: Any) -> QueueRowOut:
    return QueueRowOut(
        id=row.id,
        application_id=row.application_id,
        applicant_name=row.display_name or row.external_ref,
        applicant_ref=row.external_ref,
        amount_paise=row.requested_amount_paise,
        routed_because=RoutedBecauseOut(text="Consent required", rule_number=0),
        recommendation=RecommendationOut(
            action="REFER",
            band=None,
            approved_limit_paise=None,
            tenor_months=row.requested_tenor_months,
            annual_rate_bps=None,
        ),
        pd=MetricOut(value=None, status="unavailable"),
        coverage=MetricOut(value=None, status="unavailable"),
        verification="UNKNOWN",
        waiting_seconds=int(row.waiting_seconds or 0),
        decided_at=row.decided_at,
        change=None,
    )


# --------------------------------------------------------------------------- #
# Query builders.
# --------------------------------------------------------------------------- #
def _base_select() -> Select[Any]:
    return (
        select(
            Decision.id,
            Decision.application_id,
            Decision.action,
            Decision.approved_limit_paise,
            Decision.terms,
            Decision.fired_rules,
            Decision.decided_at,
            Applicant.display_name,
            Applicant.external_ref,
            Application.requested_amount_paise,
            Application.requested_tenor_months,
            _pd_expr.label("pd"),
            _RiskA.calibration_status.label("calibration_status"),
            _cov_expr.label("coverage"),
            _band_expr.label("verification"),
            _ManipA.payload["trigger_counts"].label("trigger_counts"),
            PolicyVersion.rules.label("rules"),
            _waiting_secs.label("waiting_seconds"),
            DecisionChange.direction.label("change_direction"),
            DecisionChange.previous_band,
            DecisionChange.new_band,
            DecisionChange.previous_outcome,
            DecisionChange.new_outcome,
            DecisionChange.human_action_protected,
        )
        .select_from(Decision)
        .join(Applicant, Applicant.id == Decision.applicant_id)
        .join(Application, Application.id == Decision.application_id)
        .join(PolicyVersion, PolicyVersion.id == Decision.policy_version_id)
        .outerjoin(DecisionChange, DecisionChange.new_decision_id == Decision.id)
        .outerjoin(
            _RiskA,
            and_(
                _RiskA.feature_snapshot_id == Decision.feature_snapshot_id,
                _RiskA.kind == AssessmentKind.RISK,
            ),
        )
        .outerjoin(
            _CovA,
            and_(
                _CovA.feature_snapshot_id == Decision.feature_snapshot_id,
                _CovA.kind == AssessmentKind.COVERAGE,
            ),
        )
        .outerjoin(
            _ManipA,
            and_(
                _ManipA.feature_snapshot_id == Decision.feature_snapshot_id,
                _ManipA.kind == AssessmentKind.MANIPULATION,
            ),
        )
    )


def _apply_filters(
    stmt: Select[Any],
    *,
    q: str | None,
    band: str | None,
    coverage_min: int | None,
    coverage_max: int | None,
    amount_min: int | None,
    amount_max: int | None,
    waiting_gt: int | None,
) -> Select[Any]:
    if q:
        term = f"%{q}%"
        stmt = stmt.where(
            or_(Applicant.display_name.ilike(term), Applicant.external_ref.ilike(term))
        )
    if band:
        stmt = stmt.where(_band_expr == band.upper())
    if coverage_min is not None:
        stmt = stmt.where(_cov_expr >= coverage_min)
    if coverage_max is not None:
        stmt = stmt.where(_cov_expr <= coverage_max)
    if amount_min is not None:
        stmt = stmt.where(_amount_expr >= amount_min)
    if amount_max is not None:
        stmt = stmt.where(_amount_expr <= amount_max)
    if waiting_gt is not None:
        stmt = stmt.where(_waiting_secs > waiting_gt * 3600)
    return stmt


async def _counts(
    session: AsyncSession, tenant_id: uuid.UUID, views: Sequence[str]
) -> dict[str, int]:
    """One scan, one count(*) FILTER per accessible view - so tab counts need no extra request."""
    if not views:
        return {}
    columns = [func.count().filter(_view_predicate(view)) for view in views]
    stmt = select(*columns).select_from(Decision).where(Decision.tenant_id == tenant_id)
    row = (await session.execute(stmt)).one()
    counts = {view: int(row[index]) for index, view in enumerate(views)}
    pending = int(
        await session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.tenant_id == tenant_id,
                Application.status == ApplicationStatus.AWAITING_CONSENT,
            )
        )
        or 0
    )
    # Consent-declined cases are undecided, but deliberately overlap the analyst's
    # broad inbox and evidence-needed subset just like coverage-routed decisions do.
    for view in ("my-exceptions", "evidence-needed"):
        if view in counts:
            counts[view] += pending
    return counts


async def _auto_decided_24h(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    since = datetime.now(UTC) - timedelta(hours=24)
    stmt = (
        select(func.count())
        .select_from(Decision)
        .where(
            Decision.tenant_id == tenant_id,
            Decision.routing == "AUTOMATED",
            Decision.decided_at >= since,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _pending_order_col(sort: str) -> Any:
    base = sort.lstrip("-")
    if base == "waiting":
        return Application.created_at
    if base == "pd":
        return literal(1.0)
    if base == "coverage":
        return literal(-1)
    return func.coalesce(Application.requested_amount_paise, 0)


async def _pending_evidence_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    q: str | None,
    band: str | None,
    coverage_min: int | None,
    coverage_max: int | None,
    amount_min: int | None,
    amount_max: int | None,
    waiting_gt: int | None,
    sort: str,
    cursor: str | None,
    limit: int,
) -> list[Any]:
    # Unknown assessment values never satisfy assessment filters; null is not zero.
    if band or coverage_min is not None or coverage_max is not None:
        return []
    waiting = func.extract("epoch", func.now() - Application.created_at)
    order_col = _pending_order_col(sort)
    stmt = (
        select(
            Application.id,
            Application.id.label("application_id"),
            Application.requested_amount_paise,
            Application.requested_tenor_months,
            Application.created_at.label("decided_at"),
            Applicant.display_name,
            Applicant.external_ref,
            waiting.label("waiting_seconds"),
            order_col.label("sort_val"),
        )
        .join(Applicant, Applicant.id == Application.applicant_id)
        .where(
            Application.tenant_id == tenant_id,
            Application.status == ApplicationStatus.AWAITING_CONSENT,
        )
    )
    if q:
        term = f"%{q}%"
        stmt = stmt.where(
            or_(Applicant.display_name.ilike(term), Applicant.external_ref.ilike(term))
        )
    amount = func.coalesce(Application.requested_amount_paise, 0)
    if amount_min is not None:
        stmt = stmt.where(amount >= amount_min)
    if amount_max is not None:
        stmt = stmt.where(amount <= amount_max)
    if waiting_gt is not None:
        stmt = stmt.where(waiting > waiting_gt * 3600)
    desc = _is_desc(sort)
    if cursor:
        decoded = _decode_cursor(cursor, sort)
        if decoded is not None:
            bound_value, bound_id = decoded
            keyset = tuple_(order_col, Application.id)
            reference = tuple_(literal(bound_value), literal(bound_id))
            stmt = stmt.where(keyset < reference if desc else keyset > reference)
    if desc:
        stmt = stmt.order_by(order_col.desc(), Application.id.desc())
    else:
        stmt = stmt.order_by(order_col.asc(), Application.id.asc())
    return list((await session.execute(stmt.limit(limit + 1))).all())


async def list_queue(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    role: str,
    *,
    view: str | None = None,
    q: str | None = None,
    band: str | None = None,
    coverage_min: int | None = None,
    coverage_max: int | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
    waiting_gt: int | None = None,
    sort: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> QueueResponse:
    views = accessible_views(role)
    resolved_view = view or default_view(role)
    if resolved_view not in views:
        raise QueueAccessError(resolved_view)

    resolved_sort = sort if sort in _SORTS else "waiting"
    page_size = _clamp_limit(limit)

    stmt = _base_select().where(Decision.tenant_id == tenant_id, _view_predicate(resolved_view))
    stmt = _apply_filters(
        stmt,
        q=q,
        band=band,
        coverage_min=coverage_min,
        coverage_max=coverage_max,
        amount_min=amount_min,
        amount_max=amount_max,
        waiting_gt=waiting_gt,
    )

    order_col = _order_col(resolved_sort)
    desc = _is_desc(resolved_sort)

    if cursor:
        decoded = _decode_cursor(cursor, resolved_sort)
        if decoded is not None:
            bound_value, bound_id = decoded
            keyset = tuple_(order_col, Decision.id)
            reference = tuple_(literal(bound_value), literal(bound_id))
            stmt = stmt.where(keyset < reference if desc else keyset > reference)

    if desc:
        stmt = stmt.order_by(order_col.desc(), Decision.id.desc())
    else:
        stmt = stmt.order_by(order_col.asc(), Decision.id.asc())

    stmt = stmt.add_columns(order_col.label("sort_val")).limit(page_size + 1)

    result = list((await session.execute(stmt)).all())
    pending: list[Any] = []
    if resolved_view in {"my-exceptions", "evidence-needed"}:
        pending = await _pending_evidence_rows(
            session,
            tenant_id,
            q=q,
            band=band,
            coverage_min=coverage_min,
            coverage_max=coverage_max,
            amount_min=amount_min,
            amount_max=amount_max,
            waiting_gt=waiting_gt,
            sort=resolved_sort,
            cursor=cursor,
            limit=page_size,
        )

    tagged = [(row, False) for row in result] + [(row, True) for row in pending]
    tagged.sort(key=lambda item: (item[0].sort_val, item[0].id), reverse=desc)
    has_next = len(tagged) > page_size
    page = tagged[:page_size]

    rows = [
        _pending_evidence_row_out(row) if is_pending else _row_out(row) for row, is_pending in page
    ]
    next_cursor = (
        _encode_cursor(resolved_sort, page[-1][0].sort_val, page[-1][0].id)
        if has_next and page
        else None
    )

    counts = await _counts(session, tenant_id, views)
    auto24 = await _auto_decided_24h(session, tenant_id)

    return QueueResponse(
        view=resolved_view,
        counts=counts,
        rows=rows,
        next_cursor=next_cursor,
        auto_decided_24h=auto24,
    )
