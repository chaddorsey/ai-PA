"""Field mask filtering for CLI output."""

from __future__ import annotations


def apply_field_mask(data, fields: list[str] | None):
    """Filter output data to only include specified fields."""
    if fields is None:
        return data
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in fields} for item in data if isinstance(item, dict)]
    return data
