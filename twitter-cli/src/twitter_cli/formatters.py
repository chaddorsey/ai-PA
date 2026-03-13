"""Output formatting for twitter-cli."""
import json
import sys


def format_output(data, fmt: str = "json") -> str:
    """Format data for output.

    Args:
        data: Dict or list to format.
        fmt: 'json' or 'text'.
    """
    if fmt == "json":
        indent = 2 if sys.stdout.isatty() else None
        return json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    if fmt == "text":
        return _format_text(data)
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _format_text(data) -> str:
    """Human-readable text output."""
    if isinstance(data, list):
        return "\n---\n".join(_format_item(item) for item in data)
    if isinstance(data, dict):
        return _format_item(data)
    return str(data)


def _format_item(item: dict) -> str:
    """Format a single item as key: value lines."""
    lines = []
    for key, value in item.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=str, ensure_ascii=False)
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
