"""Input validation for Slack CLI."""
import re

# Slack ID prefixes: C=channel, U=user, D=DM, G=group, W=workspace, T=team, B=bot, F=file, E=enterprise
VALID_ID_PREFIXES = {"C", "U", "D", "G", "W", "T", "B", "F", "E"}
SLACK_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{8,12}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{10}\.\d{6}$")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
FORBIDDEN_ID_CHARS = re.compile(r"[?#%]")


def validate_slack_id(value: str) -> str | None:
    """Validate a Slack ID. Returns error message or None if valid."""
    if not value:
        return "empty ID"
    if FORBIDDEN_ID_CHARS.search(value):
        return f"ID contains forbidden characters: {value}"
    if CONTROL_CHAR_PATTERN.search(value):
        return f"ID contains control characters: {value!r}"
    if value[0] not in VALID_ID_PREFIXES:
        return f"unknown ID prefix '{value[0]}' (expected one of {sorted(VALID_ID_PREFIXES)})"
    if not SLACK_ID_PATTERN.match(value):
        return f"malformed Slack ID: {value}"
    return None


def validate_timestamp(value: str) -> str | None:
    """Validate a Slack timestamp. Returns error message or None if valid."""
    if not value:
        return "empty timestamp"
    if not TIMESTAMP_PATTERN.match(value):
        return f"invalid timestamp format: {value} (expected NNNNNNNNNN.NNNNNN)"
    return None


def sanitize_value(value: str, allow_newlines: bool = False) -> str | None:
    """Check a string value for control characters. Returns error or None if clean."""
    pattern = CONTROL_CHAR_PATTERN if not allow_newlines else re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    if pattern.search(value):
        return "value contains control characters"
    return None


def validate_body(body: dict, schema_params: dict) -> list[dict]:
    """Validate a --body JSON dict against schema parameters.

    Returns list of {"field": ..., "error": ...} dicts. Empty list means valid.
    """
    errors = []
    for name, spec in schema_params.items():
        if spec.get("required") and name not in body:
            errors.append({"field": name, "error": "required field missing"})
    for name in body:
        if name not in schema_params:
            errors.append({"field": name, "error": "unknown field"})
    return errors


def validate_semantic(body: dict, schema_params: dict) -> list[dict]:
    """Run semantic validation on field values based on naming conventions."""
    errors = []
    for name, value in body.items():
        if not isinstance(value, str):
            continue
        spec = schema_params.get(name, {})
        field_type = spec.get("semantic_type", "")
        is_id_field = (
            field_type == "slack_id"
            or name in ("channel", "user")
            or name.endswith("_id")
        )
        is_ts_field = field_type == "timestamp" or name.endswith("_ts")
        if is_id_field:
            err = validate_slack_id(value)
            if err:
                errors.append({"field": name, "error": err})
        elif is_ts_field:
            err = validate_timestamp(value)
            if err:
                errors.append({"field": name, "error": err})
    return errors
