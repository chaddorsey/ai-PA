"""Output formatting for Slack CLI."""
import csv
import io
import json
import sys

import yaml


def should_use_json(format_flag: str | None) -> bool:
    """Determine if output should be JSON. Default: JSON when piped, text when TTY."""
    if format_flag == "json":
        return True
    if format_flag in ("text", "csv", "yaml"):
        return False
    return not sys.stdout.isatty()


def apply_field_mask(data, fields: list[str] | None):
    """Filter dict or list of dicts to only include specified fields."""
    if fields is None:
        return data
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [
            {k: v for k, v in item.items() if k in fields}
            for item in data
            if isinstance(item, dict)
        ]
    return data


def format_output(data, format_flag: str | None) -> str:
    """Format data according to the requested format."""
    fmt = format_flag or "json"

    if fmt == "json":
        if sys.stdout.isatty():
            return json.dumps(data, indent=2, ensure_ascii=False)
        return json.dumps(data, ensure_ascii=False)

    if fmt == "yaml":
        return yaml.dump(data, default_flow_style=False, allow_unicode=True).rstrip()

    if fmt == "csv":
        return _format_csv(data)

    if fmt == "text":
        return _format_text(data)

    return json.dumps(data, indent=2, ensure_ascii=False)


def _format_csv(data) -> str:
    """Format data as CSV."""
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return ""
    output = io.StringIO()
    keys = list(data[0].keys())
    writer = csv.DictWriter(output, fieldnames=keys)
    writer.writeheader()
    for row in data:
        writer.writerow({k: row.get(k, "") for k in keys})
    return output.getvalue().rstrip()


def _format_text(data) -> str:
    """Format data as human-readable text."""
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if isinstance(data, list):
        return "\n---\n".join(_format_text(item) for item in data)
    return str(data)


def output(data, format_flag: str | None = None, fields: list[str] | None = None) -> None:
    """Apply field mask, format, and print to stdout."""
    masked = apply_field_mask(data, fields)
    print(format_output(masked, format_flag))
