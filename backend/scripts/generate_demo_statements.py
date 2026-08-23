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
from datetime import UTC, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.enums import EventDirection
from app.services.demo.personas import PERSONAS, PersonaCorpus, PersonaSpec, build_corpus

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "demo" / "statements"

_PDF_LINES_PER_PAGE = 52


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

    for name in sorted(path.name for path in OUT.iterdir()):
        print(f"wrote demo/statements/{name}")


if __name__ == "__main__":
    main()
