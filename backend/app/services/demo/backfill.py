"""Synthetic *historical* cohort so the model-health page can measure real numbers.

The curated demo book (:mod:`app.services.demo.seed`) runs 12 personas through the real
pipeline but creates **no closed outcomes**. So the model-health page correctly reports
``NOT_YET_MEASURABLE`` for calibration/discrimination (needs 200 closed outcomes) and
``INSUFFICIENT_SAMPLE`` for drift (needs 100 decisions). This module seeds a synthetic
*historical* cohort so those panels measure genuine numbers — without fabricating any.

Honesty contract
----------------
* **Every ``pd`` is a genuine model output.** Each synthetic applicant is generated as a
  dated bank-event corpus and scored by the REAL classification → snapshot → assessment
  → policy pipeline (:func:`app.services.orchestrator.service.decide`). Nothing here writes
  a feature value or a pd directly.
* **Outcome labels come from an INDEPENDENT ground truth**, not from the model's pd. Each
  applicant has a latent repayment capacity ``h``; the bank corpus is generated from ``h``
  and the model scores that corpus, while the outcome is drawn from a documented logistic
  hazard of ``h`` (:func:`_ground_truth_hazard`). Drawing labels from the model's own score
  would make calibration look artificially perfect and would fabricate a favourable result
  for an admittedly-uncalibrated model. Because both the hazard and the model derive from
  ``h`` through *different* functions, the reliability curve shows the model's real,
  imperfect calibration.
* **Everything is labelled.** Every outcome records ``synthetic_backfill: True`` plus the
  ground-truth hazard and latent capacity in ``detail`` so an auditor can see exactly how each
  label was produced (applicants carry realistic names in a dedicated ``APL-2xxx`` ref range).
* **The cohort stays out of the live queue.** Any decision that routes to a human review is
  resolved on creation (historical cases are, by definition, already closed), so it never
  appears in the analyst's pending exception queue — only in views that genuinely mean
  "all decisions".
"""

import hashlib
import math
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.applicant import Applicant
from app.models.decision import Decision, HumanReview
from app.models.enums import OutcomeLabel, ReviewOutcome, ReviewStatus, SourceTier, UserRole
from app.models.outcome import Outcome
from app.models.tenant import Tenant
from app.models.user import User
from app.services.demo.personas import IncomePortion, MonthlyDebit, PersonaSpec
from app.services.demo.seed import _context, _create_persona
from app.services.orchestrator.service import decide
from app.services.reviews.service import is_fraud_routed
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Coverage variety: a mix of statement lengths spreads coverage scores across deciles.
_MONTHS_CHOICES: tuple[int, ...] = (3, 4, 5, 6, 8)
_OCCUPATIONS: tuple[str, ...] = ("SALARIED", "GIG", "SELF_EMPLOYED", "BUSINESS")
# Realistic names so the historical book reads like a real portfolio rather than a synthetic
# dump. The cohort stays identifiable in the data via outcome.detail.synthetic_backfill.
_FIRST_NAMES: tuple[str, ...] = (
    "Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan",
    "Kabir", "Dhruv", "Kartik", "Rahul", "Nikhil", "Aryan", "Vikram", "Manish", "Suresh",
    "Ananya", "Diya", "Aadhya", "Saanvi", "Ira", "Myra", "Aarohi", "Anika", "Kiara", "Riya",
    "Sara", "Meera", "Tara", "Neha", "Pooja", "Sneha", "Priya", "Divya", "Isha", "Kavya",
)
_LAST_NAMES: tuple[str, ...] = (
    "Sharma", "Verma", "Gupta", "Iyer", "Nair", "Menon", "Reddy", "Rao", "Patel", "Shah",
    "Kulkarni", "Deshpande", "Joshi", "Pillai", "Chauhan", "Malhotra", "Kapoor", "Bose",
    "Banerjee", "Das", "Mehta", "Khan", "Sheikh", "Ahmed", "Pawar", "Shinde", "Naidu", "Bhat",
    "Kumar", "Singh", "Yadav", "Mishra", "Pandey", "Tiwari", "Saxena", "Agarwal", "Jain", "Sinha",
)


def _historical_ref(index: int) -> str:
    """External ref for a backfill applicant — the curated ``APL-`` format, offset so it never
    collides with the hand-authored personas (which sit below APL-1200)."""
    return f"APL-{2000 + index:04d}"


def _historical_name(index: int) -> str:
    """A realistic, deterministic display name for a backfill applicant."""
    first = _FIRST_NAMES[int(_uniform("first", index) * len(_FIRST_NAMES))]
    last = _LAST_NAMES[int(_uniform("last", index) * len(_LAST_NAMES))]
    return f"{first} {last}"
# Realistic reviewer reason codes so the overrides panel shows a real breakdown.
_REASON_CODES: tuple[tuple[str, str], ...] = (
    ("POLICY_EXCEPTION", "Approved above ceiling on documented cash-flow strength."),
    ("ADDITIONAL_CONTEXT", "Verified income continuity with the applicant directly."),
    ("DOCUMENT_VERIFIED", "Confirmed the uploaded statement against the source bank."),
    ("MANUAL_AFFORDABILITY", "Re-ran affordability with the corrected obligation set."),
    ("IDENTITY_CONFIRMED", "Cleared the identity flag after a manual KYC check."),
)


def _uniform(*parts: object) -> float:
    """Deterministic uniform in [0, 1) from a seed — no wall-clock, fully replayable."""
    raw = hashlib.sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(raw[:8], "big") / 2.0**64


def _income_portions(occupation: str, index: int) -> tuple[IncomePortion, ...]:
    """Income payers for one applicant, diversified enough for gig/self-employed to clear D3.

    Salaried keeps a single employer (normal); gig income is split across three platforms and
    self-employed/business across two clients, so no single counterparty exceeds ~55% of
    inflow. Counterparties are per-applicant so the cohort shows no cross-applicant reuse.
    """
    # All portions land early in the month (before rent/EMI at days 24/20) so the running
    # balance never dips negative mid-month regardless of the debt-service ratio.
    if occupation == "GIG":
        return (
            IncomePortion(29, 400, "Platform delivery payout", f"PLATFORM-A {index % 19:02d}"),
            IncomePortion(27, 350, "Platform delivery payout", f"PLATFORM-B {index % 23:02d}"),
            IncomePortion(25, 250, "Platform delivery payout", f"PLATFORM-C {index % 29:02d}"),
        )
    if occupation in ("SELF_EMPLOYED", "BUSINESS"):
        return (
            IncomePortion(29, 550, "Client invoice settlement", f"CLIENT-A {index % 19:02d}"),
            IncomePortion(26, 450, "Client invoice settlement", f"CLIENT-B {index % 23:02d}"),
        )
    return (IncomePortion(28, 1000, "Salary credit", f"EMPLOYER {index % 37:02d}"),)


def _historical_spec(index: int) -> tuple[PersonaSpec, float]:
    """Build one balance-coherent historical applicant plus its latent capacity ``h``.

    ``h`` in [0, 1) is the applicant's underlying repayment strength. It is turned into the
    features the published scorecard (:mod:`ml.scorecard.cashflow_scorecard_v1`) actually
    weighs, so weaker applicants score a genuinely higher model pd: lower income, a heavier
    debt-service ratio, thinner balances, and — for the weakest — recently *missed* utility
    and telecom payments (a broken on-time streak). Counterparties are diversified and
    salaries de-rounded so the cohort does not trip the manipulation detectors (a single
    round-number employer with one landlord would look like D3/D4 fraud). The spec is a pure
    function of ``index`` so the same book reproduces byte-identically.
    """
    h = _uniform("h", index)
    weak = 1.0 - h
    # ~28% of the cohort are thin-file applicants: a short, declared-document statement with no
    # balance column and no utility footprint. They score genuinely lower on evidence coverage
    # (mirroring the curated coverage-limited persona), so the coverage distribution spans the
    # low/mid range instead of clustering entirely at HIGH.
    thin_file = _uniform("thin", index) < 0.28
    # Thin-file statements are 3-4 months: short enough to lower the coverage history score, but
    # NOT the 2-month case that trips the D2 inflow-burst detector (a 45-day pre-window with only
    # one month in the 180-day baseline reads as a 4x spike; 3+ months keeps the ratio under 3x).
    months = (
        (3 if _uniform("thin-len", index) < 0.5 else 4)
        if thin_file
        else _MONTHS_CHOICES[index % len(_MONTHS_CHOICES)]
    )
    # De-round the salary (breaks the D4 round-number-salary detector) and floor it low so
    # the weakest applicants sit near the bottom of the income transform.
    jitter = int(_uniform("jitter", index) * 90_000) - 45_000
    income_base = 1_200_000 + round(h * 7_800_000) + jitter  # ~₹12k-₹90k monthly
    # Debt-service ratio is the strongest PD lever; keep permille_min above the total
    # obligation ratio so every lean month still nets positive (balance stays coherent).
    dsr = 0.05 + weak * 0.42  # EMI / income, 0.05..0.47
    rent_ratio = 0.15 + weak * 0.08  # 0.15..0.23
    emi = round(income_base * dsr)
    rent = round(income_base * rent_ratio)
    power = round(income_base * 0.03)
    telecom = round(income_base * 0.015)
    volatility = round(weak * 170)  # permille_min >= 830 > max obligation ratio (~0.75)
    permille = tuple(1000 if month % 2 == 0 else 1000 - volatility for month in range(months))
    # Thin balances for weak applicants (raises PD via the balance-buffer features).
    target = round(income_base * (0.04 + h * 0.76))
    opening = round(income_base * (0.30 + h * 0.60))
    # The weakest miss their two most recent utility/telecom bills -> broken on-time streak.
    missed = (0, 1) if weak > 0.6 else ()
    # Keep every historical request below the ₹200,000 mandatory-review ceiling so the cohort
    # auto-decides and never lands in the live analyst exception queue as a pending review.
    requested = 1_200_000 + round(_uniform("req", index) * 17_800_000)  # ₹12k-₹190k
    occupation = _OCCUPATIONS[index % len(_OCCUPATIONS)]
    # Gig/self-employed income must be spread across several payers: a single payer at 100%
    # of inflow is exactly what D3 flags as a fabricated-gig fraud signal (salaried is exempt,
    # one employer being normal). Keep the top payer's share well under the 0.80 threshold.
    income_portions = _income_portions(occupation, index)
    spec = PersonaSpec(
        ref=_historical_ref(index),
        name=_historical_name(index),
        occupation=occupation,
        story="Portfolio applicant (model-health backfill).",
        months=months,
        requested_amount_paise=requested,
        requested_tenor_months=12 if requested < 10_000_000 else 24,
        opening_balance_paise=opening,
        income_base_paise=income_base,
        income_monthly_permille=permille,
        income_portions=income_portions,
        debits=(
            MonthlyDebit(24, rent, "House rent paid to landlord", f"LANDLORD {index % 29:02d}"),
            MonthlyDebit(20, emi, "Loan EMI payment", f"LENDER {index % 13:02d}"),
            MonthlyDebit(15, power, "Electricity bill payment", "POWER UTIL", skip_months=missed),
            MonthlyDebit(12, telecom, "Mobile recharge", "TELECOM OP", skip_months=missed),
            MonthlyDebit(8, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
        ),
        # Thin-file applicants carry no balance column, sit at the declared-document tier and
        # skip the balance leveler; that legitimately lowers their coverage score.
        balances_present=not thin_file,
        tier=SourceTier.DECLARED_DOCUMENT if thin_file else SourceTier.AA_VERIFIED,
        balance_targets_paise=None if thin_file else tuple(target for _ in range(months)),
    )
    return spec, h


def _ground_truth_hazard(h: float) -> float:
    """P(adverse outcome) as a documented logistic of latent capacity ``h``.

    Independent of the model's pd. Spans ~0.55 (weak, h→0) to ~0.03 (strong, h→1).
    """
    z = 0.2 - 3.7 * h
    return 1.0 / (1.0 + math.exp(-z))


def _draw_outcome(index: int, hazard: float) -> OutcomeLabel:
    """Draw a closed-loan label from the independent ground-truth hazard (deterministic)."""
    adverse = _uniform("outcome", index) < hazard
    severity = _uniform("severity", index)
    if adverse:
        if severity < 0.5:
            return OutcomeLabel.DELINQUENT
        if severity < 0.85:
            return OutcomeLabel.DEFAULTED
        return OutcomeLabel.WRITTEN_OFF
    return OutcomeLabel.PAID_OFF if severity < 0.3 else OutcomeLabel.PERFORMING


async def _seed_historical_reviews(
    session: AsyncSession,
    tenant: Tenant,
    decisions: list[tuple[int, Decision, datetime]],
    credit_reviewers: list[User],
    fraud_reviewer: User,
) -> int:
    """Create *resolved* reviews for the historical cohort.

    ``decide`` sets ``routing=HUMAN`` but never writes a ``HumanReview`` — the live queue
    treats any human-routed decision *without* a resolved review as a pending exception. So a
    review is recorded for BOTH:

    * every human-routed historical decision — otherwise it would flood the analyst's live
      exception queue with closed history, and
    * a small extra sample of auto-decided cases — historical human spot-checks that give the
      overrides panel a realistic, reason-coded breakdown.

    Historical cases were, by definition, already actioned, so recording their resolutions is
    faithful, and it keeps the whole cohort out of the live pending queue.
    """
    targets = [
        (index, decision, decided_at)
        for index, decision, decided_at in decisions
        if decision.routing == "HUMAN" or _uniform("review", index) < 0.05
    ]
    created = 0
    for position, (index, decision, decided_at) in enumerate(targets):
        reason_code, reason_text = _REASON_CODES[position % len(_REASON_CODES)]
        fraud = is_fraud_routed(decision)
        reviewer = fraud_reviewer if fraud else credit_reviewers[position % len(credit_reviewers)]
        session.add(
            HumanReview(
                tenant_id=tenant.id,
                application_id=decision.application_id,
                decision_id=decision.id,
                reviewer_id=reviewer.id,
                queue="fraud-review" if fraud else "my-exceptions",
                status=ReviewStatus.RESOLVED,
                outcome=(
                    ReviewOutcome.APPROVED
                    if _uniform("review-outcome", index) < 0.65
                    else ReviewOutcome.DECLINED
                ),
                reason_code=reason_code,
                reason_text=reason_text,
                assigned_at=decided_at + timedelta(hours=2),
                resolved_at=decided_at + timedelta(hours=6),
            )
        )
        created += 1
    await session.commit()
    return created


async def seed_health_backfill(size: int | None = None) -> int:
    """Seed the historical cohort and return the number of new closed outcomes created.

    Idempotent: applicants that already exist (by their ``APL-2xxx`` ref) are skipped, so re-running
    tops the cohort up rather than duplicating it. Requires the curated demo book to already
    be seeded (tenant, model version, LIVE policy).
    """
    if not settings.demo_seed_enabled:
        raise RuntimeError("health backfill refused: set DEMO_SEED_ENABLED=true explicitly")
    count = settings.demo_backfill_size if size is None else size
    if count <= 0:
        return 0
    started = datetime.now(UTC)
    created = 0
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "aperture-demo"))
        if tenant is None:
            raise RuntimeError("health backfill requires the demo tenant; run seed_demo() first")
        analyst = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id, User.role == UserRole.CREDIT_ANALYST
            )
        )
        owner = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id, User.role == UserRole.CREDIT_POLICY_OWNER
            )
        )
        fraud_reviewer = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id, User.role == UserRole.FRAUD_REVIEWER
            )
        )
        if analyst is None or owner is None or fraud_reviewer is None:
            raise RuntimeError("health backfill requires the demo users; run seed_demo() first")
        context = _context(tenant, analyst)

        hist_decisions: list[tuple[int, Decision, datetime]] = []
        for index in range(count):
            ref = _historical_ref(index)
            existing = await session.scalar(
                select(Applicant.id).where(
                    Applicant.tenant_id == tenant.id, Applicant.external_ref == ref
                )
            )
            if existing is not None:
                continue
            spec, h = _historical_spec(index)
            # Anchor the whole applicant in the past so the book has a real timeline: the
            # statement, the point-in-time snapshot and the decision all sit ~4-14 months back.
            # That makes the drift window (older reference vs recent) a genuine time split
            # rather than a single instant, and dates every closed outcome in the past.
            decided_at = started - timedelta(days=120 + int(_uniform("decided", index) * 300))
            application = await _create_persona(
                session, tenant=tenant, spec=spec, anchor=decided_at
            )
            await session.flush()
            result = await decide(
                session,
                context,
                application_id=application.id,
                as_of=decided_at,
                idempotency_key=f"hist-{index:05d}",
                generate_recourse=False,
                decided_at=decided_at,
            )
            await session.flush()
            decision = result.decision
            hist_decisions.append((index, decision, decided_at))
            hazard = _ground_truth_hazard(h)
            observed = decided_at + timedelta(days=90)  # loan closes ~a quarter after decision
            session.add(
                Outcome(
                    tenant_id=tenant.id,
                    application_id=application.id,
                    decision_id=decision.id,
                    applicant_id=application.applicant_id,
                    label=_draw_outcome(index, hazard),
                    observed_at=observed,
                    detail={
                        "synthetic_backfill": True,
                        "performance_window_closed": True,
                        "ground_truth_hazard": round(hazard, 4),
                        "latent_capacity": round(h, 4),
                        "policy_version_id": str(decision.policy_version_id),
                    },
                )
            )
            created += 1
            if index % 40 == 39:
                await session.commit()
        await session.commit()

        resolved = await _seed_historical_reviews(
            session, tenant, hist_decisions, [analyst, owner], fraud_reviewer
        )
        outcome_total = int(
            await session.scalar(
                select(func.count()).select_from(Outcome).where(Outcome.tenant_id == tenant.id)
            )
            or 0
        )
        decision_total = int(
            await session.scalar(
                select(func.count()).select_from(Decision).where(Decision.tenant_id == tenant.id)
            )
            or 0
        )
    elapsed = (datetime.now(UTC) - started).total_seconds()
    print(
        f"Health backfill: +{created} historical applicants, {resolved} reviews resolved, "
        f"{outcome_total} closed outcomes / {decision_total} decisions total ({elapsed:.1f}s)."
    )
    return created


__all__ = ["seed_health_backfill"]
