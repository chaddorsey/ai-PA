"""Pure parser: rendered daily-briefing markdown -> free blocks (24h). No I/O."""
import re
from typing import Dict, List

# Matches: "• **8:00 AM–10:00 AM** - (2h)"  (en-dash between the times)
_BULLET_RE = re.compile(r"^[•\-\*]\s*\*\*(.+?)\*\*\s*-\s*\(.+?\)\s*$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$")


def _to_minutes_12h(s: str) -> int:
    """'8:00 AM' -> 480, '1:30 PM' -> 810, '12:00 AM' -> 0, '12:00 PM' -> 720."""
    m = _TIME_RE.match(s.strip().upper().replace(".", ""))
    if not m:
        raise ValueError(f"bad 12h time: {s!r}")
    h, mm, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "AM":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return h * 60 + mm


def _fmt_hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def parse_available_blocks(markdown: str) -> List[Dict]:
    """Return [{'start':'HH:MM','end':'HH:MM','duration_min':int}, ...] in 24h.

    Empty list if the day is fully booked / has no bullets. Duration is computed
    from start/end (the rendered '(2h)' string is ignored for robustness).
    """
    blocks: List[Dict] = []
    for line in markdown.splitlines():
        m = _BULLET_RE.match(line.strip())
        if not m:
            continue
        inside = m.group(1)
        parts = re.split(r"\s*–\s*", inside)  # split on en-dash U+2013
        if len(parts) != 2:
            continue
        try:
            start, end = _to_minutes_12h(parts[0]), _to_minutes_12h(parts[1])
        except ValueError:
            continue
        if end <= start:
            continue
        blocks.append({"start": _fmt_hhmm(start), "end": _fmt_hhmm(end),
                       "duration_min": end - start})
    return blocks


def filter_blocks(blocks: List[Dict], min_minutes: int) -> List[Dict]:
    """Keep only blocks at least `min_minutes` long."""
    return [b for b in blocks if b["duration_min"] >= min_minutes]
