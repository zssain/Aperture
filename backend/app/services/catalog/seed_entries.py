"""Curated Indian merchant/employer/biller corpus with source provenance."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedEntry:
    canonical_name: str
    category: str
    aliases: tuple[str, ...]
    source_note: str


_GROUPS = {
    "GIG_INCOME": (
        "Swiggy",
        "Zomato",
        "Uber",
        "Ola",
        "Rapido",
        "Urban Company",
        "Porter",
        "Dunzo",
        "Zepto",
        "Blinkit",
    ),
    "TELECOM": (
        "Airtel",
        "Reliance Jio",
        "Vodafone Idea",
        "BSNL",
        "ACT Fibernet",
        "Tata Play",
        "Hathway",
    ),
    "UTILITY": (
        "BESCOM",
        "Tata Power",
        "Adani Electricity",
        "MSEDCL",
        "BSES Rajdhani",
        "CESC",
        "TANGEDCO",
        "BWSSB",
        "Indraprastha Gas",
        "Mahanagar Gas",
    ),
    "EMI": (
        "Bajaj Finance",
        "HDFC Loan",
        "ICICI Loan",
        "SBI Loan",
        "Axis Loan",
        "Tata Capital",
        "Mahindra Finance",
        "Lendingkart",
        "KreditBee",
        "Navi Finance",
    ),
    "MERCHANT": (
        "Amazon India",
        "Flipkart",
        "Myntra",
        "BigBasket",
        "DMart",
        "Reliance Retail",
        "PhonePe Merchant",
        "Paytm Merchant",
        "Razorpay",
        "Juspay",
        "Nykaa",
        "Meesho",
    ),
    "SALARY": (
        "Infosys Payroll",
        "TCS Payroll",
        "Wipro Payroll",
        "HCL Payroll",
        "Tech Mahindra Payroll",
        "Accenture Payroll",
        "Government Salary",
        "Employer Payroll",
    ),
    "RENT": ("House Rent", "Apartment Lease", "PG Rent", "Office Lease", "Commercial Rent"),
}
_FORMS = ("payment", "upi settlement", "bank narration", "monthly credit", "bill desk")

SEED_ENTRIES: tuple[SeedEntry, ...] = tuple(
    SeedEntry(
        canonical_name=f"{name} {form}",
        category=category,
        aliases=(name, f"{name}/{form}", f"{form} {name}"),
        source_note=(
            "Curated from public biller/merchant names and synthetic bank-narration "
            "variants; no applicant data."
        ),
    )
    for category, names in _GROUPS.items()
    for name in names
    for form in _FORMS
)
