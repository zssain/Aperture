"""Structured JSON logging via structlog.

A single ``configure_logging`` call wires structlog to emit one JSON object per line
to stdout. ``merge_contextvars`` pulls in any context bound for the current request
(notably the correlation id set by the middleware), so every log line emitted while
handling a request carries that id.
"""

import logging
from typing import cast

import structlog
from structlog.contextvars import merge_contextvars

from app.core.pii_filter import pii_allowlist_processor


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog to render newline-delimited JSON at ``log_level``."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            pii_allowlist_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
