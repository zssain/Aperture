"""Versioned feature schema + validation.

A violation (missing feature, wrong dtype, out-of-range value, or a null without a
reason) is a HARD FAILURE — never a coercion. Bumping the feature set or a range
requires bumping ``SCHEMA_VERSION``.
"""

from typing import Any

from app.services.features.registry import REGISTRY, FeatureSpec

SCHEMA_VERSION = "features-v1"


class SchemaViolationError(Exception):
    pass


def validate(
    values: dict[str, Any],
    null_map: dict[str, Any],
    specs: tuple[FeatureSpec, ...] = REGISTRY,
) -> None:
    keys = {spec.key for spec in specs}

    for spec in specs:
        in_values = spec.key in values
        in_null = spec.key in null_map
        if not in_values and not in_null:
            raise SchemaViolationError(f"feature {spec.key!r} is absent from the snapshot")
        if in_values and in_null:
            raise SchemaViolationError(f"feature {spec.key!r} is both a value and null")

        if in_null:
            if not null_map[spec.key]:
                raise SchemaViolationError(f"feature {spec.key!r} is null without a reason")
            continue

        value = values[spec.key]
        if spec.dtype == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise SchemaViolationError(f"feature {spec.key!r} must be int, got {value!r}")
        elif spec.dtype == "float":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise SchemaViolationError(f"feature {spec.key!r} must be float, got {value!r}")
        else:  # pragma: no cover - registry only declares int/float
            raise SchemaViolationError(f"feature {spec.key!r} has unknown dtype {spec.dtype!r}")

        low, high = spec.allowed_range
        if not (low <= float(value) <= high):
            raise SchemaViolationError(
                f"feature {spec.key!r}={value!r} outside allowed range [{low}, {high}]"
            )

    extra = set(values) - keys
    if extra:
        raise SchemaViolationError(f"unexpected feature keys in values: {sorted(extra)}")
    extra_null = set(null_map) - keys
    if extra_null:
        raise SchemaViolationError(f"unexpected feature keys in null_map: {sorted(extra_null)}")
