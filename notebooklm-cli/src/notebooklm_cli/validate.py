"""Input validation for NotebookLM CLI requests.

Validates bodies and paths before they reach notebooklm-py calls.
"""

from __future__ import annotations

import re

from notebooklm_cli.schema import get_schema

# Type-check dispatch table: type string -> (check function, human label)
_TYPE_CHECKS: dict[str, tuple] = {
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


def validate_path(path_str: str) -> str | None:
    """Return an error message if *path_str* contains path traversal components, else None."""
    import os

    parts = path_str.replace("\\", "/").split("/")
    for part in parts:
        if part == "..":
            return "path must not contain '..' components"
    return None
