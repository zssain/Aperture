import time

import pytest
from app.services.sources.document import (
    MAX_BYTES,
    MAX_ROWS,
    DocumentTooLargeError,
    RowCapExceededError,
    UnsupportedDocumentError,
)
from app.services.sources.upload_security import (
    DocumentParseTimeoutError,
    VirusDetectedError,
    parse_document_securely,
)


class RejectScanner:
    def scan(self, content: bytes) -> bool:
        return False


def test_wrong_magic_bytes_rejected() -> None:
    with pytest.raises(UnsupportedDocumentError):
        parse_document_securely(b"\x00\x01not a document", "fake.pdf")


def test_virus_hook_rejects_before_parse() -> None:
    with pytest.raises(VirusDetectedError):
        parse_document_securely(b"Date,Description,Amount\n", "a.csv", scanner=RejectScanner())


def test_oversize_upload_is_rejected() -> None:
    with pytest.raises(DocumentTooLargeError):
        parse_document_securely(b"x" * (MAX_BYTES + 1), "large.csv")


def test_too_many_rows_are_rejected() -> None:
    row = b"2026-01-01,Transfer,1\n"
    content = b"Date,Description,Amount\n" + row * (MAX_ROWS + 1)
    with pytest.raises(RowCapExceededError):
        parse_document_securely(content, "rows.csv")


def _slow_parse(_content: bytes, _filename: str) -> None:
    time.sleep(0.2)


def test_parser_wall_clock_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.sources.upload_security._isolated_parse", _slow_parse)
    with pytest.raises(DocumentParseTimeoutError):
        parse_document_securely(b"Date,Description,Amount\n", "slow.csv", timeout=0.01)
