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


def mark_seen(ids, path) -> None:
    """Add ids to the seen set and persist (atomic write)."""
    data = _load(path)
    merged = set(data.get("seen_ids", [])) | set(ids)
    data["seen_ids"] = sorted(merged)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, p)
