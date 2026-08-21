"""Document-upload adapter (CSV + PDF). Treat every file as hostile.

Validation: magic bytes, size cap (10MB), row cap (20,000), and per-row schema. Rejected
rows are counted and returned with reasons — never silently dropped. Provenance checks
run and are attached to the snapshot. The tier is always ``DECLARED_DOCUMENT``.
"""

import csv
import hashlib
import io
import itertools
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pypdf import PdfReader

from app.models.enums import EventDirection, SourceTier
from app.services.sources.base import NormalizedEvent
from app.services.sources.provenance import check_csv_provenance, check_pdf_provenance

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20_000
MAX_PDF_PAGES = 50
REQUIRED_COLUMNS = ("Date", "Description", "Amount")
OPTIONAL_COLUMNS = ("Balance",)

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%m/%d/%Y",
)
# A PDF statement line: ISO date, description, signed amount, optional balance.
_PDF_LINE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<desc>.+?)\s+(?P<amount>[-+]?[\d,]+\.\d{2})"
    r"(?:\s+(?P<balance>[-+]?[\d,]+\.\d{2}))?\s*$"
)


class DocumentError(Exception):
    """Base for document parse failures (translated to 4xx; no snapshot is created)."""


class DocumentTooLargeError(DocumentError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or f"File exceeds the {MAX_BYTES // (1024 * 1024)}MB size limit.")


class RowCapExceededError(DocumentError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message or f"File exceeds the {MAX_ROWS:,}-row limit. Upload a shorter period."
        )
        self.limit = MAX_ROWS


class SchemaError(DocumentError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.expected_columns = list(REQUIRED_COLUMNS)


class UnsupportedDocumentError(DocumentError):
    pass


@dataclass
class RejectedRow:
    row: int
    reason: str


@dataclass
class ParsedDocument:
    events: list[NormalizedEvent]
    rejected: list[RejectedRow] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    content_hash: str = ""
    row_count: int = 0


class DocumentAdapter:
    tier: SourceTier = SourceTier.DECLARED_DOCUMENT

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        if len(file_bytes) > MAX_BYTES:
            raise DocumentTooLargeError()
        if file_bytes[:4] == b"%PDF":
            return self._parse_pdf(file_bytes)
        if filename.lower().endswith(".csv") or _looks_like_text(file_bytes):
            return self._parse_csv(file_bytes)
        raise UnsupportedDocumentError("Unsupported document type; upload CSV or PDF.")

    # --- CSV ---------------------------------------------------------------- #
    def _parse_csv(self, file_bytes: bytes) -> ParsedDocument:
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SchemaError("File is not valid UTF-8 text.") from exc

        reader = csv.reader(io.StringIO(text))
        try:
            header = next(reader)
        except StopIteration as exc:
            raise SchemaError("File is empty.") from exc

        index = _column_index(header)

        events: list[NormalizedEvent] = []
        rejected: list[RejectedRow] = []
        balances: list[tuple[int, int]] = []  # (amount_signed_paise, balance_paise)
        row_count = 0

        for line_number, raw_row in enumerate(reader, start=2):
            row_count += 1
            if row_count > MAX_ROWS:
                raise RowCapExceededError()
            if not any(cell.strip() for cell in raw_row):
                rejected.append(RejectedRow(line_number, "blank row"))
                continue
            parsed = _parse_csv_row(raw_row, index, line_number)
            if isinstance(parsed, RejectedRow):
                rejected.append(parsed)
                continue
            event, balance_pair = parsed
            events.append(event)
            if balance_pair is not None:
                balances.append(balance_pair)

        has_balance = index.balance is not None
        provenance = check_csv_provenance(
            has_balance_column=has_balance,
            balance_consistent=_balances_reconcile(balances),
        )
        return ParsedDocument(
            events=events,
            rejected=rejected,
            provenance=provenance,
            content_hash=hashlib.sha256(file_bytes).hexdigest(),
            row_count=row_count,
        )

    # --- PDF ---------------------------------------------------------------- #
    def _parse_pdf(self, file_bytes: bytes) -> ParsedDocument:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
        except Exception as exc:
            raise SchemaError("File is not a readable PDF.") from exc

        if len(reader.pages) > MAX_PDF_PAGES:
            raise RowCapExceededError()

        lines: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            lines.extend(line.strip() for line in text.splitlines() if line.strip())

        events: list[NormalizedEvent] = []
        rejected: list[RejectedRow] = []
        row_count = 0
        for line_number, line in enumerate(lines, start=1):
            match = _PDF_LINE.match(line)
            if match is None:
                continue  # header/footer/prose — not a transaction line
            row_count += 1
            if row_count > MAX_ROWS:
                raise RowCapExceededError()
            try:
                amount_paise, direction = _parse_amount(match.group("amount"))
                occurred_at = _parse_date(match.group("date"))
            except ValueError as exc:
                rejected.append(RejectedRow(line_number, str(exc)))
                continue
            balance_raw = match.group("balance")
            events.append(
                NormalizedEvent(
                    occurred_at=occurred_at,
                    direction=direction,
                    amount_paise=amount_paise,
                    description=match.group("desc").strip(),
                    counterparty=None,
                    balance_paise=_parse_amount(balance_raw)[0] if balance_raw else None,
                    external_id=None,
                )
            )

        metadata = {str(k): str(v) for k, v in (dict(reader.metadata or {})).items()}
        provenance = check_pdf_provenance(metadata, is_signed=_pdf_is_signed(file_bytes))
        return ParsedDocument(
            events=events,
            rejected=rejected,
            provenance=provenance,
            content_hash=hashlib.sha256(file_bytes).hexdigest(),
            row_count=row_count,
        )


@dataclass(frozen=True)
class _ColumnIndex:
    date: int
    description: int
    amount: int
    balance: int | None


def _column_index(header: list[str]) -> _ColumnIndex:
    normalized = [cell.strip().lower() for cell in header]
    lookup = {name: normalized.index(name.lower()) for name in normalized}

    def find(name: str) -> int | None:
        key = name.lower()
        return lookup.get(key)

    missing = [name for name in REQUIRED_COLUMNS if find(name) is None]
    if missing:
        raise SchemaError(
            "Missing required column(s): "
            f"{', '.join(missing)}. Expected columns: {', '.join(REQUIRED_COLUMNS)} "
            f"(optional: {', '.join(OPTIONAL_COLUMNS)})."
        )
    date_i = find("Date")
    desc_i = find("Description")
    amount_i = find("Amount")
    assert date_i is not None and desc_i is not None and amount_i is not None
    return _ColumnIndex(date_i, desc_i, amount_i, find("Balance"))


def _parse_csv_row(
    row: list[str], index: _ColumnIndex, line_number: int
) -> tuple[NormalizedEvent, tuple[int, int] | None] | RejectedRow:
    max_needed = max(index.date, index.description, index.amount)
    if len(row) <= max_needed:
        return RejectedRow(line_number, "too few columns")

    date_raw = row[index.date].strip()
    if not date_raw:
        return RejectedRow(line_number, "missing date (occurred_at is mandatory)")
    try:
        occurred_at = _parse_date(date_raw)
    except ValueError as exc:
        return RejectedRow(line_number, str(exc))

    try:
        amount_paise, direction = _parse_amount(row[index.amount])
    except ValueError as exc:
        return RejectedRow(line_number, str(exc))

    balance_paise: int | None = None
    balance_pair: tuple[int, int] | None = None
    if index.balance is not None and index.balance < len(row) and row[index.balance].strip():
        try:
            balance_paise = _parse_amount(row[index.balance])[0]
            signed = amount_paise if direction is EventDirection.CREDIT else -amount_paise
            balance_pair = (signed, balance_paise)
        except ValueError:
            balance_paise = None

    event = NormalizedEvent(
        occurred_at=occurred_at,
        direction=direction,
        amount_paise=amount_paise,
        description=row[index.description].strip(),
        counterparty=None,
        balance_paise=balance_paise,
        external_id=None,
    )
    return event, balance_pair


def _parse_date(raw: str) -> datetime:
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"unparseable date: {raw!r}")


def _parse_amount(raw: str) -> tuple[int, EventDirection]:
    text = raw.strip().replace(",", "").replace("₹", "").replace("INR", "").strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    for suffix, is_debit in (("Dr", True), ("DR", True), ("Cr", False), ("CR", False)):
        if text.endswith(suffix):
            negative, text = is_debit, text[: -len(suffix)].strip()
    if text.startswith("-"):
        negative, text = True, text[1:]
    elif text.startswith("+"):
        text = text[1:]
    value = float(text)  # raises ValueError on garbage → caller rejects the row
    paise = abs(round(value * 100))
    return paise, EventDirection.DEBIT if negative else EventDirection.CREDIT


def _balances_reconcile(pairs: list[tuple[int, int]]) -> bool:
    """True if successive balances differ by exactly the signed amount."""
    for (_, prev_balance), (amount, balance) in itertools.pairwise(pairs):
        if balance - prev_balance != amount:
            return False
    return True


def _looks_like_text(data: bytes) -> bool:
    sample = data[:2048]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return True


def _pdf_is_signed(file_bytes: bytes) -> bool:
    return b"/Sig" in file_bytes or b"adbe.pkcs7" in file_bytes
