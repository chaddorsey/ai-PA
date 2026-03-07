"""Input validation for OmniFocus CLI requests.

Validates bodies, UUIDs, dates, and names before they reach osascript calls.
"""

from __future__ import annotations

import re
from datetime import datetime

from omnifocus_cli.schema import get_schema

# Regex for accepted ISO 8601 date formats
_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)?)?$"
)

# Type-check dispatch table: type string -> (check function, human label)
_TYPE_CHECKS: dict[str, tuple[callable, str]] = {
    "string": (lambda v: isinstance(v, str), "string"),
    "boolean": (lambda v: isinstance(v, bool), "boolean"),
    "integer": (lambda v: isinstance(v, int) and not isinstance(v, bool), "integer"),
    "array[string]": (
        lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
        "array[string]",
    ),
    "object": (lambda v: isinstance(v, dict), "object"),
}


def validate_body(schema_key: str, body: dict) -> list[dict]:
    """Validate *body* against the schema registered under *schema_key*.

    Returns a list of ``{"field": ..., "error": ...}`` dicts.
    An empty list means the body is valid.
    """
    schema = get_schema(schema_key)
    if schema is None:
        return [{"field": "_schema", "error": f"unknown schema: {schema_key}"}]

    errors: list[dict] = []
    params = schema.get("params", {})
    known_fields = set(params.keys())

    # Check for required fields
    for field_name, field_meta in params.items():
        if field_meta.get("required") and field_name not in body:
            errors.append({"field": field_name, "error": f"{field_name} is required"})

    # Check for unknown fields
    for field_name in body:
        if field_name not in known_fields:
            errors.append({"field": field_name, "error": f"unknown field: {field_name}"})

    # Type-check provided fields
    for field_name, value in body.items():
        if field_name not in known_fields:
            continue
        expected_type = params[field_name]["type"]
        check_fn, label = _TYPE_CHECKS.get(expected_type, (None, expected_type))
        if check_fn is not None and not check_fn(value):
            errors.append(
                {"field": field_name, "error": f"expected {label}, got {type(value).__name__}"}
            )

    return errors


def validate_uuid(value: str) -> str | None:
    """Return an error message if *value* is not a safe identifier, else None."""
    if not value:
        return "UUID must not be empty"
    if any(ch in value for ch in ("?", "#", "%")):
        return "UUID contains forbidden character (?, #, or %)"
    if ".." in value:
        return "UUID must not contain '..'"
    for ch in value:
        code = ord(ch)
        if code < 0x20 or code == 0x7F:
            return "UUID contains control characters"
        if ch in (" ", "\t", "\n", "\r"):
            return "UUID contains whitespace"
    return None


def validate_date(value: str) -> str | None:
    """Return an error message if *value* is not a valid ISO 8601 date, else None."""
    if not value:
        return "date must not be empty"
    if not _DATE_RE.match(value):
        return f"invalid date format: {value}"
    # Also verify it parses as a real date
    try:
        parseable = value.replace("Z", "+00:00") if value.endswith("Z") else value
        datetime.fromisoformat(parseable)
    except ValueError:
        return f"unparseable date: {value}"
    return None


def validate_name(value: str) -> str | None:
    """Return an error message if *value* is not a valid name, else None."""
    if not value:
        return "name must not be empty"
    for ch in value:
        code = ord(ch)
        if code < 0x20 or code == 0x7F:
            return "name contains control characters"
    return None
