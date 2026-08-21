"""Canonical JSON serialisation for audit hashing.

THIS FORMAT IS FROZEN. Every stored ``payload_hash`` depends on it, so it must be
byte-for-byte stable forever and identical across processes.

Rules:
- UTF-8, object keys sorted, no whitespace.
- bool → ``true`` / ``false``; int → decimal digits.
- float → rounded to 10 decimal places, fixed (non-scientific) notation; ``-0``
  normalised to ``0``; non-finite floats are rejected.
- ``datetime`` → UTC ISO-8601 with a literal ``Z`` and 6-digit microseconds.
- ``None`` is omitted (never emitted as ``null``) — dropped from objects and arrays.
- ``str`` via JSON string escaping; ``uuid.UUID`` and ``Enum`` by their string value.
- unsupported types raise ``TypeError``.
"""

import json
import math
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _format_datetime(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _format_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("non-finite floats cannot be serialised canonically")
    if value == 0.0:
        value = 0.0  # normalise -0.0
    return format(round(value, 10), ".10f")


def _canonical(value: Any) -> str | None:
    """Canonical fragment for ``value``, or None if it must be omitted."""
    if value is None:
        return None
    # bool must precede int (bool is an int subclass).
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, uuid.UUID):
        return json.dumps(str(value), ensure_ascii=False)
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, datetime):
        return json.dumps(_format_datetime(value), ensure_ascii=False)
    if isinstance(value, dict):
        return _canonical_object(value)
    if isinstance(value, list | tuple):
        items = [frag for item in value if (frag := _canonical(item)) is not None]
        return "[" + ",".join(items) + "]"
    raise TypeError(f"unsupported type for canonical JSON: {type(value).__name__}")


def _canonical_object(obj: dict[Any, Any]) -> str:
    parts: list[str] = []
    for key in sorted(obj):
        if not isinstance(key, str):
            raise TypeError("canonical JSON object keys must be strings")
        fragment = _canonical(obj[key])
        if fragment is None:
            continue
        parts.append(json.dumps(key, ensure_ascii=False) + ":" + fragment)
    return "{" + ",".join(parts) + "}"


def canonical_json(payload: Any) -> str:
    """Serialise ``payload`` to its canonical string form."""
    fragment = _canonical(payload)
    # A top-level None (or an object whose values are all None) is the empty object.
    return "{}" if fragment is None else fragment
