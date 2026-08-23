"""Generate the demo/ bank-statement files from the seeded persona corpus.

The files are derived from the SAME deterministic persona scripts the demo seed uses,
so an uploaded statement tells the same story as its seeded twin — through the real
parser, classifier, feature, assessment and policy engines. Nothing is stubbed.

Outputs (repo-root demo/statements/):
  asha_gig_driver.csv    Signed-amount CSV with balance column (HDFC-style header).
  ravi_salaried_thin.csv Separate Withdrawal/Deposit columns, no balance (SBI-style).
  fatima_clean.pdf       Clean statement PDF (parses via the PDF line grammar).
  meera_tampered.pdf     Doctored PDF: LibreOffice producer metadata (D6), a running-
                         balance jump (D5) and a pre-application inflow burst (D2).

Usage:  uv run python scripts/generate_demo_statements.py
"""

import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.enums import EventDirection
from app.services.demo.personas import PERSONAS, PersonaCorpus, PersonaSpec, build_corpus

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "demo" / "statements"

_PDF_LINES_PER_PAGE = 52


def _ideal_real_bank_csv(anchor: datetime) -> str:
    """A realistic, real-bank-format statement (Kotak/HDFC style: a preamble row,
    Date/Details/Debit/Credit/Balance columns, DD/MM/YYYY dates, several transactions
    per day) whose running balance reconciles exactly. Unlike a churn account, it has
    recognizable salary, rent, EMI, electricity and mobile-recharge lines, so it flows
    through classification into a fully-populated, meaningful assessment. Dated to end a
    few days before `anchor` so the evidence is fresh.

    Each row is (days_ago, debit_or_credit, rupees, details). Rows are emitted oldest
    first with a live running balance — the same thing D5 later checks."""
    monthly: list[tuple[int, str, float, str]] = [
        (28, "C", 68_500.00, "NEFT CR SALARY CREDIT-ACME TECHNOLOGIES PVT LTD"),
        (26, "D", 18_000.00, "UPI/DR/HOUSERENT/house rent to landlord/UPI"),
        (25, "D", 815.00, "UPI/DR/Blinkit/blinkit groceries/UPI"),
        (25, "D", 420.00, "UPI/DR/Swiggy/swiggy order/UPI"),
        (23, "D", 9_500.00, "UPI/DR/HDFCLOAN/HDFC personal loan EMI/UPI"),
        (18, "D", 1_240.00, "UPI/DR/BESCOM/BESCOM electricity bill payment/UPI"),
        (16, "D", 599.00, "UPI/DR/Airtel/Airtel mobile recharge/UPI"),
        (14, "D", 1_299.00, "UPI/DR/AmazonPay/Amazon India purchase/UPI"),
        (12, "D", 2_100.00, "UPI/DR/BigBasket/bigbasket groceries/UPI"),
        (9, "D", 560.00, "UPI/DR/Zomato/zomato order/UPI"),
        (8, "C", 560.00, "UPI/CR/Zomato/zomato refund/UPI"),
        (6, "D", 350.00, "UPI/DR/DMart/UPI purchase pos/UPI"),
        (3, "D", 180.00, "UPI/DR/QuickMart/UPI purchase/UPI"),
    ]
    rows: list[tuple[object, int, str, float, str]] = []
    seq = 0
    for month in reversed(range(3)):  # oldest month first
        for day_in_month, kind, rupees, details in monthly:
            days_ago = 30 * month + day_in_month
            rows.append(((anchor - timedelta(days=days_ago)).date(), seq, kind, rupees, details))
            seq += 1
    # Oldest first; the emission index keeps same-day rows in listing order.
    rows.sort(key=lambda r: (r[0], r[1]))

    balance = 25_000.00
    lines = [
        "Table 1",
        "Date,Details,Ref No/Cheque No,Debit,Credit,Balance,",
    ]
    for occurred, _seq, kind, rupees, details in rows:
        balance += rupees if kind == "C" else -rupees
        # No thousands separators: an unquoted comma inside a numeric cell would split
        # the column. Real per-transaction amounts are written comma-free.
        debit = f"{rupees:.2f}" if kind == "D" else ""
        credit = f"{rupees:.2f}" if kind == "C" else ""
        lines.append(
            f'{occurred.strftime("%d/%m/%Y")},"{details}",,{debit},{credit},{balance:.2f},'
        )
    lines.append(",,,,,,")
    lines.append("This is a computer generated statement and does not require a signature.,,,,,,")
    return "\n".join(lines) + "\n"


def _spec(ref: str) -> PersonaSpec:
    return next(spec for spec in PERSONAS if spec.ref == ref)


def _rupees(paise: int) -> str:
    return f"{paise / 100:.2f}"


def _signed_csv(corpus: PersonaCorpus) -> str:
    lines = ["Date,Description,Amount,Balance"]
    for event in corpus.events:
        signed = (
            event.amount_paise
            if event.direction is EventDirection.CREDIT
            else -event.amount_paise
        )
        assert event.balance_paise is not None
        lines.append(
            f"{event.occurred_at.date().isoformat()},{event.description},"
            f"{_rupees(signed)},{_rupees(event.balance_paise)}"
        )
    return "\n".join(lines) + "\n"


def _debit_credit_csv(corpus: PersonaCorpus) -> str:
    lines = [
        "Statement of account - sandbox export",
        f"Period: {corpus.period_start:%d/%m/%Y} to {corpus.period_end:%d/%m/%Y}",
        "",
        "Txn Date,Narration,Withdrawal Amt,Deposit Amt",
    ]
    for event in corpus.events:
        debit = _rupees(event.amount_paise) if event.direction is EventDirection.DEBIT else ""
        credit = _rupees(event.amount_paise) if event.direction is EventDirection.CREDIT else ""
        lines.append(
            f"{event.occurred_at.strftime('%d/%m/%Y')},{event.description},{debit},{credit}"
        )
    return "\n".join(lines) + "\n"


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _statement_pdf(corpus: PersonaCorpus, *, title: str, producer: str | None) -> bytes:
    rows = [title, ""]
    for event in corpus.events:
        signed = (
            event.amount_paise
            if event.direction is EventDirection.CREDIT
            else -event.amount_paise
        )
        line = f"{event.occurred_at.date().isoformat()} {event.description} {_rupees(signed)}"
        if event.balance_paise is not None:
            line += f" {_rupees(event.balance_paise)}"
        rows.append(line)

    pages = [rows[i : i + _PDF_LINES_PER_PAGE] for i in range(0, len(rows), _PDF_LINES_PER_PAGE)]
    page_count = len(pages)
    font_object = 3 + 2 * page_count
    info_object = font_object + 1

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(page_count))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
    for index, page_rows in enumerate(pages):
        content_object = 4 + 2 * index
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object} 0 R >> >> "
                f"/Contents {content_object} 0 R >>"
            ).encode()
        )
        stream_lines = ["BT", "/F1 9 Tf", "60 740 Td", "13 TL"]
        for row in page_rows:
            stream_lines.append(f"({_pdf_escape(row)}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode()
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    if producer is not None:
        escaped = _pdf_escape(producer)
        objects.append(f"<< /Producer ({escaped}) /Creator ({escaped}) >>".encode())

    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_start = len(body)
    body += f"xref\n0 {len(objects) + 1}\n".encode()
    body += b"0000000000 65535 f \n"
    for offset in offsets:
        body += f"{offset:010d} 00000 n \n".encode()
    trailer = f"<< /Size {len(objects) + 1} /Root 1 0 R"
    if producer is not None:
        trailer += f" /Info {info_object} 0 R"
    trailer += " >>"
    body += b"trailer\n" + trailer.encode() + f"\nstartxref\n{xref_start}\n%%EOF\n".encode()
    return body


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    anchor = datetime.combine(datetime.now(UTC).date(), time(0, 0), tzinfo=UTC)

    asha = build_corpus(_spec("APL-1093"), anchor)
    (OUT / "asha_gig_driver.csv").write_text(_signed_csv(asha))

    ravi = build_corpus(_spec("APL-1104"), anchor)
    (OUT / "ravi_salaried_thin.csv").write_text(_debit_credit_csv(ravi))

    fatima = build_corpus(_spec("APL-1055"), anchor)
    (OUT / "fatima_clean.pdf").write_bytes(
        _statement_pdf(fatima, title="Account Statement - sandbox", producer=None)
    )

    meera = build_corpus(_spec("APL-1088"), anchor)
    (OUT / "meera_tampered.pdf").write_bytes(
        _statement_pdf(meera, title="Account Statement", producer="LibreOffice 7.5")
    )

    # A real-bank-format statement that decides cleanly end to end.
    (OUT / "ideal_salaried_statement.csv").write_text(_ideal_real_bank_csv(anchor))

    for name in sorted(path.name for path in OUT.iterdir()):
        print(f"wrote demo/statements/{name}")


if __name__ == "__main__":
    main()
