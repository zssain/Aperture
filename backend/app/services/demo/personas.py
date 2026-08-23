"""Deterministic demo persona corpus.

Each persona is a *behavioural script* — dated, realistically-narrated bank events that
flow through the real classification, feature, assessment and policy engines. Nothing
here sets a feature value or an outcome directly; the specs below were designed against
the published scorecard weights and coverage formula so the seeded book shows a
realistic decision mix (enhanced/standard/starter approvals, a risk decline, an
affordability decline, an evidence referral and a fraud referral).

All amounts are integer paise. All schedules are fixed offsets from the seed anchor so
the same anchor always produces byte-identical events.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models.enums import EventDirection, SourceTier


@dataclass(frozen=True)
class IncomePortion:
    """One recurring payout inside a monthly income total."""

    day_in_month: int
    permille: int  # share of the month's income total, in 1/1000
    description: str
    counterparty: str


@dataclass(frozen=True)
class MonthlyDebit:
    day_in_month: int
    amount_paise: int
    description: str
    counterparty: str
    skip_months: tuple[int, ...] = ()  # month indices (0 = most recent) with no payment


@dataclass(frozen=True)
class ExtraCredit:
    """A one-off credit at an explicit day offset (transfers, bursts)."""

    days_ago: int
    amount_paise: int
    description: str
    counterparty: str


@dataclass(frozen=True)
class PersonaSpec:
    ref: str
    name: str
    occupation: str
    story: str
    months: int
    requested_amount_paise: int
    requested_tenor_months: int
    opening_balance_paise: int
    income_base_paise: int
    income_monthly_permille: tuple[int, ...]  # len == months; index 0 = most recent
    income_portions: tuple[IncomePortion, ...]
    debits: tuple[MonthlyDebit, ...]
    extra_credits: tuple[ExtraCredit, ...] = ()
    # Per-month end-of-month balance targets (index 0 = most recent). When set, the
    # surplus above the target is spent as ordinary UPI debits — the way real people
    # spend what they earn — so balances stay in a realistic band.
    balance_targets_paise: tuple[int, ...] | None = None
    # Days-in-month at which the surplus above the balance target is spent. Earlier
    # (larger) days keep balances realistically tight through the month; the default
    # spends at month end, letting balances ride high between paydays.
    leveler_spend_days: tuple[int, int] = (4, 1)
    # Whether one-off credits count as spendable income for the leveler. True for
    # recurring side income (it should be spent like any income); False for story
    # events such as a fraudulent pre-application burst, which must visibly pile up.
    level_extra_credits: bool = False
    balances_present: bool = True
    tier: SourceTier = SourceTier.AA_VERIFIED
    # When true, also attach a simulated credit-bureau file (a second source type +
    # populated bureau signals) so the demo shows the bureau path end to end.
    has_bureau: bool = False
    # (days_ago of an existing event, paise): an unexplained running-balance jump is
    # applied from that event onward — the signature of a hand-edited statement.
    balance_jump: tuple[int, int] | None = None


@dataclass(frozen=True)
class PersonaEvent:
    occurred_at: datetime
    direction: EventDirection
    amount_paise: int
    balance_paise: int | None
    description: str
    counterparty_hash: str


@dataclass(frozen=True)
class PersonaCorpus:
    spec: PersonaSpec
    events: tuple[PersonaEvent, ...] = field(default_factory=tuple)
    period_start: datetime | None = None
    period_end: datetime | None = None


def counterparty_hash(name: str) -> str:
    """Deterministic pseudonymous hash — no counterparty plaintext in the ledger."""
    return hashlib.sha256(f"demo-cp:{name}".encode()).hexdigest()


@dataclass(frozen=True)
class _Draft:
    days_ago: int
    direction: EventDirection
    amount_paise: int
    description: str
    counterparty: str


def _income_rows(spec: PersonaSpec, month: int) -> list[_Draft]:
    total = spec.income_base_paise * spec.income_monthly_permille[month] // 1000
    if total <= 0 or not spec.income_portions:
        return []
    rows: list[_Draft] = []
    allocated = 0
    for position, portion in enumerate(spec.income_portions):
        last = position == len(spec.income_portions) - 1
        amount = total - allocated if last else total * portion.permille // 1000
        allocated += amount
        rows.append(
            _Draft(
                days_ago=30 * month + portion.day_in_month,
                direction=EventDirection.CREDIT,
                amount_paise=amount,
                description=portion.description,
                counterparty=portion.counterparty,
            )
        )
    return rows


_LEVELER_SPENDS = (
    (600, "UPI purchase - Swiggy Instamart order", "SWIGGY INSTAMART"),
    (400, "UPI POS purchase - DMart", "DMART"),
)


def build_corpus(spec: PersonaSpec, anchor: datetime) -> PersonaCorpus:
    """Expand a spec into dated, balance-coherent events (oldest month first)."""
    drafts: list[_Draft] = []
    for month in range(spec.months):
        month_rows = _income_rows(spec, month)
        for debit in spec.debits:
            if month in debit.skip_months:
                continue
            month_rows.append(
                _Draft(
                    days_ago=30 * month + debit.day_in_month,
                    direction=EventDirection.DEBIT,
                    amount_paise=debit.amount_paise,
                    description=debit.description,
                    counterparty=debit.counterparty,
                )
            )
        drafts.extend(month_rows)
    drafts.extend(
        _Draft(
            days_ago=credit.days_ago,
            direction=EventDirection.CREDIT,
            amount_paise=credit.amount_paise,
            description=credit.description,
            counterparty=credit.counterparty,
        )
        for credit in spec.extra_credits
    )

    if spec.balance_targets_paise is not None:
        running = spec.opening_balance_paise
        for month in reversed(range(spec.months)):
            net = 0
            for draft in drafts:
                if 30 * month <= draft.days_ago < 30 * (month + 1):
                    signed = (
                        draft.amount_paise
                        if draft.direction is EventDirection.CREDIT
                        else -draft.amount_paise
                    )
                    is_extra = any(
                        c.days_ago == draft.days_ago and c.description == draft.description
                        for c in spec.extra_credits
                    )
                    if spec.level_extra_credits or not is_extra:
                        net += signed
            surplus = running + net - spec.balance_targets_paise[month]
            if surplus >= 2_000:
                for day, (permille, description, merchant) in zip(
                    spec.leveler_spend_days, _LEVELER_SPENDS, strict=True
                ):
                    amount = surplus * permille // 1000
                    net -= amount
                    drafts.append(
                        _Draft(
                            days_ago=30 * month + day,
                            direction=EventDirection.DEBIT,
                            amount_paise=amount,
                            description=description,
                            counterparty=merchant,
                        )
                    )
            running += net

    # Chronological order, stable within a day; each event gets a distinct minute so
    # any timestamp sort (including D5's) reproduces exactly this sequence.
    ordered = sorted(enumerate(drafts), key=lambda pair: (-pair[1].days_ago, pair[0]))
    events: list[PersonaEvent] = []
    balance = spec.opening_balance_paise
    jump_applied = False
    day_sequence: dict[int, int] = {}
    for _, draft in ordered:
        offset = day_sequence.get(draft.days_ago, 0)
        day_sequence[draft.days_ago] = offset + 1
        signed = (
            draft.amount_paise
            if draft.direction is EventDirection.CREDIT
            else -draft.amount_paise
        )
        balance += signed
        if (
            spec.balance_jump is not None
            and not jump_applied
            and draft.days_ago <= spec.balance_jump[0]
        ):
            balance += spec.balance_jump[1]
            jump_applied = True
        if spec.balances_present and balance < 0:
            raise ValueError(f"{spec.ref}: balance went negative at {draft.description}")
        events.append(
            PersonaEvent(
                occurred_at=anchor
                - timedelta(days=draft.days_ago)
                + timedelta(hours=10, minutes=offset),
                direction=draft.direction,
                amount_paise=draft.amount_paise,
                balance_paise=balance if spec.balances_present else None,
                description=draft.description,
                counterparty_hash=counterparty_hash(draft.counterparty),
            )
        )

    oldest = max(draft.days_ago for _, draft in ordered)
    newest = min(draft.days_ago for _, draft in ordered)
    return PersonaCorpus(
        spec=spec,
        events=tuple(events),
        period_start=anchor - timedelta(days=oldest + 2),
        period_end=anchor - timedelta(days=max(newest - 1, 0)),
    )


PERSONAS: tuple[PersonaSpec, ...] = (
    PersonaSpec(
        ref="APL-1093",
        name="Asha Pawar",
        occupation="GIG",
        story=(
            "Gig delivery driver, 7 months of irregular platform income, rent and phone "
            "always paid, one missed electricity bill in the lean month. "
            "Expected: APPROVE_STARTER."
        ),
        months=7,
        requested_amount_paise=3_000_000,
        requested_tenor_months=12,
        opening_balance_paise=700_000,
        income_base_paise=2_600_000,
        income_monthly_permille=(500, 550, 800, 1450, 1500, 1300, 850),
        income_portions=(
            IncomePortion(28, 350, "Swiggy weekly delivery payout", "SWIGGY DELIVERY"),
            IncomePortion(25, 300, "Swiggy weekly delivery payout", "SWIGGY DELIVERY"),
            IncomePortion(13, 200, "Zomato delivery partner payout", "ZOMATO DELIVERY"),
            IncomePortion(6, 150, "Rapido captain weekly payout", "RAPIDO CAPTAIN"),
        ),
        debits=(
            MonthlyDebit(23, 800_000, "House rent paid to landlord", "LAKSHMI NIVAS"),
            MonthlyDebit(21, 300_000, "Navi Finance personal loan EMI", "NAVI FINANCE"),
            MonthlyDebit(
                12, 92_300, "BESCOM electricity bill payment", "BESCOM", skip_months=(0,)
            ),
            MonthlyDebit(10, 39_900, "Airtel prepaid mobile recharge", "AIRTEL"),
        ),
        balance_targets_paise=(300_000, 350_000, 250_000, 500_000, 600_000, 450_000, 400_000),
    ),
    PersonaSpec(
        ref="APL-1104",
        name="Ravi Menon",
        occupation="SALARIED",
        story=(
            "Salaried, clean payroll, but only a 2-month uploaded statement with no "
            "balance column — coverage-limited. Expected: APPROVE_STARTER with "
            "add-a-source recourse."
        ),
        months=2,
        requested_amount_paise=4_000_000,
        requested_tenor_months=12,
        opening_balance_paise=0,
        income_base_paise=4_251_700,
        income_monthly_permille=(1000, 1000),
        income_portions=(
            IncomePortion(50, 1000, "Salary credit - Meridian Textiles", "MERIDIAN TEXTILES"),
        ),
        debits=(
            MonthlyDebit(48, 1_200_000, "House rent paid to landlord", "GOKUL RESIDENCY"),
            MonthlyDebit(45, 110_500, "BESCOM electricity bill payment", "BESCOM"),
            MonthlyDebit(43, 49_900, "Airtel prepaid mobile recharge", "AIRTEL"),
            MonthlyDebit(41, 68_400, "UPI purchase - BigBasket groceries", "BIGBASKET"),
        ),
        balances_present=False,
        tier=SourceTier.DECLARED_DOCUMENT,
    ),
    PersonaSpec(
        ref="APL-1088",
        name="Meera Joshi",
        occupation="SALARIED",
        story=(
            "Stable salary on paper — but the statement carries an unexplained "
            "running-balance jump (D5) and a burst of large transfers right before "
            "applying (D2). Expected: FRAUD_REVIEW."
        ),
        months=6,
        requested_amount_paise=8_000_000,
        requested_tenor_months=18,
        opening_balance_paise=2_500_000,
        income_base_paise=5_483_200,
        income_monthly_permille=(1000, 1000, 1000, 1000, 1000, 1000),
        income_portions=(
            IncomePortion(28, 1000, "Salary credit - Sunrise Infotech payroll", "SUNRISE INFOTECH"),
        ),
        debits=(
            MonthlyDebit(24, 1_850_000, "House rent paid to landlord", "GREEN PARK RESIDENCY"),
            MonthlyDebit(22, 650_000, "Bajaj Finance consumer loan EMI", "BAJAJ FINANCE"),
            MonthlyDebit(18, 134_600, "Tata Power electricity bill payment", "TATA POWER"),
            MonthlyDebit(16, 64_900, "Jio postpaid mobile recharge", "RELIANCE JIO"),
            MonthlyDebit(8, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
        ),
        extra_credits=(
            ExtraCredit(10, 6_000_000, "IMPS fund transfer received", "REMITTER 407221"),
            ExtraCredit(6, 6_000_000, "IMPS fund transfer received", "REMITTER 583114"),
            ExtraCredit(3, 6_000_000, "IMPS fund transfer received", "REMITTER 662937"),
        ),
        balance_targets_paise=(2_200_000, 2_000_000, 2_400_000, 2_100_000, 2_300_000, 2_150_000),
        balance_jump=(54, 6_500_000),
    ),
    PersonaSpec(
        ref="APL-1076",
        name="Kabir Shaikh",
        occupation="SELF_EMPLOYED",
        story=(
            "Self-employed trader with shrinking, volatile settlements, no utility or "
            "telecom footprint and near-empty balances. Expected: DECLINE_RISK — and "
            "the live newly-eligible flip target once verified income arrives."
        ),
        months=6,
        requested_amount_paise=4_000_000,
        requested_tenor_months=12,
        opening_balance_paise=1_200_000,
        income_base_paise=1_500_000,
        income_monthly_permille=(450, 550, 700, 1250, 1600, 1450),
        income_portions=(
            IncomePortion(26, 600, "Client invoice settlement received", "TRADEX DISTRIBUTORS"),
            IncomePortion(12, 400, "Invoice payment received - retail sales", "JK ENTERPRISES"),
        ),
        debits=(
            MonthlyDebit(10, 700_000, "Shop rent paid", "KM PROPERTIES"),
            MonthlyDebit(8, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
            MonthlyDebit(2, 5_900, "SMS alert charges quarterly", "BANK CHARGES"),
        ),
        balance_targets_paise=(120_000, 180_000, 250_000, 400_000, 600_000, 700_000),
        leveler_spend_days=(6, 3),
    ),
    PersonaSpec(
        ref="APL-1112",
        name="Nila Reddy",
        occupation="SALARIED",
        story=(
            "Declared salaried, but the account shows only family transfers — income is "
            "unobservable. Expected: REVIEW_EVIDENCE (evidence needed)."
        ),
        months=4,
        requested_amount_paise=2_500_000,
        requested_tenor_months=12,
        opening_balance_paise=1_500_000,
        income_base_paise=0,
        income_monthly_permille=(0, 0, 0, 0),
        income_portions=(),
        debits=(
            MonthlyDebit(
                20, 850_000, "House rent paid to landlord", "SRI SAI PG", skip_months=(0,)
            ),
            MonthlyDebit(8, 42_700, "UPI purchase - Zepto groceries", "ZEPTO"),
            MonthlyDebit(3, 31_400, "UPI POS purchase - DMart", "DMART"),
        ),
        extra_credits=(
            ExtraCredit(55, 2_237_400, "IMPS fund transfer received - family support", "R SHARMA"),
            ExtraCredit(85, 2_237_400, "IMPS fund transfer received - family support", "R SHARMA"),
            ExtraCredit(105, 2_180_600, "NEFT fund transfer received", "S REDDY"),
        ),
    ),
    PersonaSpec(
        ref="APL-1067",
        name="Arjun Mehta",
        occupation="SALARIED",
        story=(
            "Car salesman: base salary plus commission months, one missed electricity "
            "bill, no telecom on this account. Expected: APPROVE_STANDARD."
        ),
        months=5,
        requested_amount_paise=12_000_000,
        requested_tenor_months=24,
        opening_balance_paise=900_000,
        income_base_paise=5_000_000,
        income_monthly_permille=(650, 1200, 700, 1500, 1350),
        income_portions=(
            IncomePortion(
                28, 1000, "Salary credit with sales incentive - Everest Motors", "EVEREST MOTORS"
            ),
        ),
        debits=(
            MonthlyDebit(24, 1_800_000, "Flat rent - Prestige Apartments", "PRESTIGE APTS"),
            MonthlyDebit(22, 900_000, "ICICI vehicle loan EMI", "ICICI LOAN"),
            MonthlyDebit(
                18, 128_800, "MSEDCL electricity bill payment", "MSEDCL", skip_months=(2,)
            ),
            MonthlyDebit(8, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
            MonthlyDebit(2, 5_900, "Cheque book issuance fee", "BANK CHARGES"),
        ),
        balance_targets_paise=(600_000, 550_000, 650_000, 700_000, 600_000),
        leveler_spend_days=(17, 15),
    ),
    PersonaSpec(
        ref="APL-1055",
        name="Fatima Khan",
        occupation="SALARIED",
        story=(
            "Strong everything: senior salary, 8 months of history, every bill on time, "
            "healthy balances, AND a clean credit-bureau file. Requests above the "
            "mandatory-review ceiling. Expected: APPROVE_ENHANCED, routed to a human by "
            "rule 10; coverage reaches HIGH thanks to the second (bureau) source."
        ),
        has_bureau=True,
        months=8,
        requested_amount_paise=25_000_000,
        requested_tenor_months=24,
        opening_balance_paise=3_500_000,
        income_base_paise=8_532_600,
        income_monthly_permille=(1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000),
        income_portions=(
            IncomePortion(28, 1000, "Salary credit - Nimbus Consulting", "NIMBUS CONSULTING"),
        ),
        debits=(
            MonthlyDebit(24, 2_500_000, "House rent paid - DLF Park Place", "DLF PARK PLACE"),
            MonthlyDebit(22, 800_000, "SBI home loan EMI", "SBI LOAN"),
            MonthlyDebit(18, 176_400, "BSES electricity bill payment", "BSES RAJDHANI"),
            MonthlyDebit(16, 84_900, "Airtel postpaid mobile recharge", "AIRTEL"),
            MonthlyDebit(8, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
        ),
        balance_targets_paise=(
            3_800_000,
            3_600_000,
            3_900_000,
            3_700_000,
            3_650_000,
            3_850_000,
            3_600_000,
            3_500_000,
        ),
    ),
    PersonaSpec(
        ref="APL-1081",
        name="Dev Patel",
        occupation="BUSINESS",
        story=(
            "Wholesale trader with lumpy but healthy settlements and modest balances. "
            "Expected: APPROVE_STANDARD."
        ),
        months=6,
        requested_amount_paise=15_000_000,
        requested_tenor_months=24,
        opening_balance_paise=700_000,
        income_base_paise=4_800_000,
        income_monthly_permille=(1550, 450, 1300, 600, 1500, 600),
        income_portions=(
            IncomePortion(26, 550, "Customer invoice settlement - wholesale", "MEHTA TRADERS"),
            IncomePortion(14, 450, "Invoice payment received - sales", "OM SALES AGENCY"),
        ),
        debits=(
            MonthlyDebit(24, 1_400_000, "Shop rent paid", "CITY CENTRE COMPLEX"),
            MonthlyDebit(12, 600_000, "Tata Capital business loan EMI", "TATA CAPITAL"),
            MonthlyDebit(18, 210_500, "MSEDCL electricity bill payment", "MSEDCL"),
            MonthlyDebit(6, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
            MonthlyDebit(2, 5_900, "SMS alert charges quarterly", "BANK CHARGES"),
        ),
        balance_targets_paise=(450_000, 500_000, 480_000, 550_000, 520_000, 500_000),
        leveler_spend_days=(10, 8),
    ),
    PersonaSpec(
        ref="APL-1049",
        name="Leela Nair",
        occupation="SALARIED",
        story=(
            "Modest government salary, but 8 months of flawless utility and telecom "
            "history and no debt. Alternative data wins. Expected: APPROVE_ENHANCED."
        ),
        months=8,
        requested_amount_paise=6_000_000,
        requested_tenor_months=12,
        opening_balance_paise=1_600_000,
        income_base_paise=3_841_500,
        income_monthly_permille=(1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000),
        income_portions=(
            IncomePortion(28, 1000, "Salary credit - Karnataka treasury", "KARNATAKA TREASURY"),
        ),
        debits=(
            MonthlyDebit(24, 900_000, "House rent paid to landlord", "SHANTI NILAYA"),
            MonthlyDebit(18, 87_600, "BESCOM electricity bill payment", "BESCOM"),
            MonthlyDebit(16, 29_900, "BSNL mobile recharge", "BSNL"),
            MonthlyDebit(8, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
        ),
        balance_targets_paise=(
            1_700_000,
            1_650_000,
            1_750_000,
            1_680_000,
            1_720_000,
            1_700_000,
            1_650_000,
            1_600_000,
        ),
    ),
    PersonaSpec(
        ref="APL-1120",
        name="Mohan Iyer",
        occupation="GIG",
        story=(
            "Urban services gig worker with only 4 months of history and tight "
            "balances. Expected: APPROVE_STARTER."
        ),
        months=4,
        requested_amount_paise=2_000_000,
        requested_tenor_months=12,
        opening_balance_paise=350_000,
        income_base_paise=2_000_000,
        income_monthly_permille=(750, 800, 700, 1900),
        income_portions=(
            IncomePortion(26, 400, "Urban Company service payout", "URBAN COMPANY"),
            IncomePortion(17, 350, "Porter delivery payout", "PORTER"),
            IncomePortion(8, 250, "Dunzo delivery partner payout", "DUNZO"),
        ),
        debits=(
            MonthlyDebit(15, 650_000, "PG rent paid", "SUNSHINE PG"),
            MonthlyDebit(13, 250_000, "KreditBee loan instalment", "KREDITBEE"),
            MonthlyDebit(7, 61_200, "TNEB electricity bill payment", "TANGEDCO"),
            MonthlyDebit(5, 24_900, "Vi prepaid mobile recharge", "VODAFONE IDEA"),
        ),
        balance_targets_paise=(250_000, 300_000, 280_000, 320_000),
    ),
    PersonaSpec(
        ref="APL-1130",
        name="Sara D'Souza",
        occupation="SALARIED",
        story=(
            "Part-time salary plus swinging freelance payouts; one missed electricity "
            "bill. Expected: APPROVE_STANDARD."
        ),
        months=6,
        requested_amount_paise=10_000_000,
        requested_tenor_months=18,
        opening_balance_paise=800_000,
        income_base_paise=3_207_400,
        income_monthly_permille=(1000, 1000, 1000, 1000, 1000, 1000),
        income_portions=(
            IncomePortion(28, 1000, "Salary credit - Ferns Floral Studio payroll", "FERNS FLORAL"),
        ),
        debits=(
            MonthlyDebit(24, 1_300_000, "House rent paid to landlord", "CASA BLANCA APTS"),
            MonthlyDebit(22, 750_000, "HDFC personal loan EMI", "HDFC LOAN"),
            MonthlyDebit(
                18, 118_300, "BESCOM electricity bill payment", "BESCOM", skip_months=(1,)
            ),
            MonthlyDebit(12, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
            MonthlyDebit(2, 5_900, "SMS alert charges quarterly", "BANK CHARGES"),
        ),
        leveler_spend_days=(8, 5),
        extra_credits=(
            ExtraCredit(10, 2_500_600, "Freelance design payout received", "DESIGN CLIENT SVC"),
            ExtraCredit(40, 311_800, "Freelance design payout received", "DESIGN CLIENT SVC"),
            ExtraCredit(70, 2_184_300, "Freelance design payout received", "DESIGN CLIENT SVC"),
            ExtraCredit(100, 623_500, "Freelance design payout received", "DESIGN CLIENT SVC"),
            ExtraCredit(130, 2_339_100, "Freelance design payout received", "DESIGN CLIENT SVC"),
            ExtraCredit(160, 467_700, "Freelance design payout received", "DESIGN CLIENT SVC"),
        ),
        balance_targets_paise=(650_000, 700_000, 680_000, 720_000, 700_000, 690_000),
        level_extra_credits=True,
    ),
    PersonaSpec(
        ref="APL-1042",
        name="Vikram Rao",
        occupation="BUSINESS",
        story=(
            "Small caterer with steady but modest settlements asking for far more than "
            "the cash flow supports. Expected: DECLINE_AFFORDABILITY — then flipped to "
            "newly-eligible by verified income events in the seed."
        ),
        months=7,
        requested_amount_paise=20_000_000,
        requested_tenor_months=12,
        opening_balance_paise=900_000,
        income_base_paise=3_014_800,
        income_monthly_permille=(980, 1020, 1000, 990, 1010, 1000, 1000),
        income_portions=(
            IncomePortion(
                26, 1000, "Invoice settlement received - catering services", "ANNAPURNA CATERERS"
            ),
        ),
        debits=(
            MonthlyDebit(24, 1_100_000, "Shop rent paid", "MARKET YARD COMPLEX"),
            MonthlyDebit(22, 400_000, "Mahindra Finance vehicle loan EMI", "MAHINDRA FINANCE"),
            MonthlyDebit(18, 96_700, "MSEDCL electricity bill payment", "MSEDCL"),
            MonthlyDebit(16, 44_900, "Jio prepaid mobile recharge", "RELIANCE JIO"),
            MonthlyDebit(8, 3_500, "Bank service charge incl GST", "BANK CHARGES"),
        ),
        balance_targets_paise=(
            500_000,
            520_000,
            480_000,
            550_000,
            510_000,
            530_000,
            500_000,
        ),
    ),
)

# The seed's transition story (verified income events → newly eligible) targets this
# persona; the live demo flip targets Kabir (APL-1076) instead.
TRANSITION_REF = "APL-1042"
LIVE_FLIP_REF = "APL-1076"
