"""Structlog processor that emits only explicitly safe fields."""

from collections.abc import MutableMapping
from typing import Any

SAFE_LOG_FIELDS = frozenset(
    {
        "event",
        "level",
        "timestamp",
        "logger",
        "correlation_id",
        "method",
        "path",
        "status",
        "code",
        "reason",
        "duration_ms",
        "job_id",
        "job_type",
        "count",
        "n",
        "minimum_n",
        "error",
    }
)
_FORBIDDEN_NAMES = frozenset(
    {
        "description",
        "narration",
        "normalized_narration",
        "embedding",
        "vector",
        "counterparty",
        "account_number",
        "applicant_name",
        "display_name",
        "file",
        "file_contents",
        "session",
        "session_token",
        "password",
        "token",
    }
)


def pii_allowlist_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in event_dict.items():
        lowered = key.casefold()
        if lowered in _FORBIDDEN_NAMES or any(name in lowered for name in _FORBIDDEN_NAMES):
            continue
        if key in SAFE_LOG_FIELDS:
            # Exception text may contain attacker-controlled PII; keep only the class/name.
            safe[key] = "redacted" if key == "error" else value
    return safe
