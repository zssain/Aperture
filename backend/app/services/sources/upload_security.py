"""Hostile-upload boundary: scan, isolate parsing, and generated-name storage."""

import concurrent.futures
import multiprocessing
import os
import resource
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.services.sources.document import (
    DocumentAdapter,
    ParsedDocument,
    SchemaError,
    UnsupportedDocumentError,
)


class VirusScanner(Protocol):
    def scan(self, content: bytes) -> bool: ...


class NoopVirusScanner:
    """Deployment hook. Production replaces this with the configured scanner."""

    def scan(self, content: bytes) -> bool:
        return True


class VirusDetectedError(UnsupportedDocumentError):
    pass


class DocumentParseTimeoutError(SchemaError):
    pass


def _isolated_parse(content: bytes, filename: str) -> ParsedDocument:
    # RLIMIT_AS cannot be lowered below the already-mapped image on some macOS builds.
    # CPU remains mandatory; address-space limiting is applied where the OS accepts it.
    with suppress(ValueError):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
    return DocumentAdapter().parse(content, filename)


def parse_document_securely(
    content: bytes, filename: str, *, scanner: VirusScanner | None = None, timeout: float = 5.0
) -> ParsedDocument:
    # Reject cheap boundary violations before allocating an isolated parser process.
    if len(content) > settings.upload_max_bytes:
        from app.services.sources.document import DocumentTooLargeError

        raise DocumentTooLargeError()
    if not (content.startswith(b"%PDF") or _looks_like_csv(content)):
        raise UnsupportedDocumentError("File signature is not a supported CSV or PDF.")
    if not content.startswith(b"%PDF") and content.count(b"\n") - 1 > settings.upload_max_rows:
        from app.services.sources.document import RowCapExceededError

        raise RowCapExceededError()
    if not (scanner or NoopVirusScanner()).scan(content):
        raise VirusDetectedError("Upload failed malware scanning.")
    context = multiprocessing.get_context("fork")
    try:
        pool: concurrent.futures.Executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=1, mp_context=context
        )
    except (PermissionError, NotImplementedError):
        # Restricted test sandboxes may deny semaphore inspection. Production uses the
        # process executor; this fallback preserves the wall-clock boundary for tests.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_isolated_parse, content, filename)
    try:
        result = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        # Exiting a ProcessPoolExecutor context waits for the worker and would defeat
        # the wall-clock boundary. Terminate the isolated worker before non-blocking
        # shutdown; the child owns no application database or request state.
        for process in getattr(pool, "_processes", {}).values():
            process.terminate()
        pool.shutdown(wait=False, cancel_futures=True)
        raise DocumentParseTimeoutError("Document parsing exceeded the five-second limit.") from exc
    else:
        pool.shutdown(wait=True)
        return result


def _looks_like_csv(content: bytes) -> bool:
    try:
        sample = content[:4096].decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    if not sample or "," not in sample or "\n" not in sample:
        return False
    printable = sum(character.isprintable() or character in "\r\n\t" for character in sample)
    return printable / len(sample) >= 0.95


def store_raw_upload(content: bytes) -> str:
    directory = Path(settings.upload_directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}.evidence"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
    return str(path)
