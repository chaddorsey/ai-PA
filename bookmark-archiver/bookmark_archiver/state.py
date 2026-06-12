"""Seen-bookmark-ID dedup state (JSON file)."""
import json
import os
from pathlib import Path


def _load(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"seen_ids": []}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"seen_ids": []}


def new_bookmarks(items: list[dict], path) -> list[dict]:
    """Return items whose 'id' is not in the seen set, preserving order."""
    seen = set(_load(path).get("seen_ids", []))
    return [b for b in items if b.get("id") not in seen]


def _save(data: dict, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, p)


def mark_seen(ids, path) -> None:
    """Add ids to the seen set and persist (atomic write)."""
    data = _load(path)
    merged = set(data.get("seen_ids", [])) | set(ids)
    data["seen_ids"] = sorted(merged)
    _save(data, path)


def get_meta(key: str, path, default=None):
    """Read a non-seen metadata value (e.g. backfill cursor/done flag)."""
    return _load(path).get(key, default)


def set_meta(key: str, value, path) -> None:
    """Set a metadata value alongside the seen set (atomic write)."""
    data = _load(path)
    data[key] = value
    _save(data, path)
