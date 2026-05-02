"""Fox-likelihood scoring.

Foxes are crepuscular — most active at dawn and dusk, also through the
night. Daytime dog/cat detections are more likely to be a neighbor's pet
or a stray cat. We don't auto-discard anything; we just tag with a
likelihood score so the viewer + assistant can filter.

Once we add zones (e.g. mark the actual den area), we'll layer in a
zone-overlap factor here. For now, time-of-day only.
"""
from __future__ import annotations

import datetime as _dt


# Score by hour-of-day. Indexed 0–23 (local time).
_HOURLY_SCORE = {
    # 21:00–05:00 — peak fox activity, almost certainly a fox
    21: 1.00, 22: 1.00, 23: 1.00,
    0: 1.00, 1: 1.00, 2: 1.00, 3: 1.00, 4: 1.00,
    # 05:00–08:00 — dawn, foxes returning to den
    5: 0.85, 6: 0.80, 7: 0.70,
    # 08:00–17:00 — daytime, much more likely a pet
    8: 0.30, 9: 0.25, 10: 0.20, 11: 0.20,
    12: 0.20, 13: 0.20, 14: 0.20, 15: 0.20, 16: 0.25, 17: 0.30,
    # 18:00–21:00 — dusk, foxes emerging
    18: 0.55, 19: 0.75, 20: 0.90,
}


def fox_likelihood(start_time: float, label: str, score: float) -> float:
    """Return 0.0–1.0 likelihood that this Frigate event is a fox.

    Args:
        start_time: unix epoch seconds (event start in Frigate)
        label: Frigate-detected label ("dog", "cat", "person", ...)
        score: Frigate's own detection confidence (0–1)

    Returns:
        Combined score. Higher = more likely fox.
    """
    if label not in {"dog", "cat"}:
        return 0.0  # person etc. — never a fox

    hour = _dt.datetime.fromtimestamp(start_time).hour
    time_factor = _HOURLY_SCORE.get(hour, 0.5)

    # Confidence sanity check — very low Frigate scores down-weight.
    confidence_factor = min(1.0, score / 0.6)  # 0.6 score → factor 1.0

    return round(time_factor * confidence_factor, 3)
