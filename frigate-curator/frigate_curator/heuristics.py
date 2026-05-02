"""Fox-likelihood scoring.

Foxes are crepuscular — most active at dawn and dusk, also through the
night. The detector's "animal" label (MegaDetector) covers any animal
including the neighbor's pet, raccoons, deer, etc. We don't auto-
discard anything; we just tag with a likelihood score so the viewer +
assistant can filter.

This version supports both:
  - MegaDetector labels (animal/person/vehicle) — primary path, after
    the v5a swap. "animal" gets the full time-weighting curve.
  - Legacy COCO labels (dog/cat) — fallback if model is reverted to
    the YOLO11-S COCO-80 setup. dog/cat both proxy "animal".

Once we add zones (e.g. mark the actual den area), we'll layer in a
zone-overlap factor here. For now, time-of-day only.
"""
from __future__ import annotations

import datetime as _dt


# Score by hour-of-day. Indexed 0–23 (local time).
# Foxes ARE more nocturnal/crepuscular but they also den under porches and
# come out during the day, especially with kits in spring/summer. The
# previous heavily-daytime-penalized curve was hiding too many real fox
# events. Tuned now to favor night/twilight without zeroing out daytime.
_HOURLY_SCORE = {
    # 21:00–05:00 — peak fox activity
    21: 1.00, 22: 1.00, 23: 1.00,
    0: 1.00, 1: 1.00, 2: 1.00, 3: 1.00, 4: 1.00,
    # 05:00–08:00 — dawn, foxes returning to den
    5: 0.90, 6: 0.85, 7: 0.75,
    # 08:00–17:00 — daytime: less common but absolutely possible.
    # Score floor of 0.5 — daytime fox events still surface in the UI's
    # default "All" view; users can filter by time-of-day if they only
    # want the high-confidence-nocturnal set.
    8: 0.55, 9: 0.50, 10: 0.50, 11: 0.50,
    12: 0.50, 13: 0.50, 14: 0.50, 15: 0.50, 16: 0.55, 17: 0.65,
    # 18:00–21:00 — dusk, foxes emerging
    18: 0.80, 19: 0.90, 20: 0.95,
}


# Labels that could plausibly be a fox under the active model.
_ANIMAL_LABELS = {"animal", "dog", "cat"}


def fox_likelihood(start_time: float, label: str, score: float) -> float:
    """Return 0.0–1.0 likelihood that this Frigate event is a fox.

    Args:
        start_time: unix epoch seconds (event start in Frigate)
        label: Frigate-detected label
            ("animal" with MegaDetector; "dog"/"cat" with COCO models)
        score: Frigate's own detection confidence (0–1)

    Returns:
        Combined score. Higher = more likely fox.
    """
    if label not in _ANIMAL_LABELS:
        return 0.0  # person/vehicle/etc. — never a fox

    hour = _dt.datetime.fromtimestamp(start_time).hour
    time_factor = _HOURLY_SCORE.get(hour, 0.5)

    # Confidence sanity check — very low Frigate scores down-weight.
    confidence_factor = min(1.0, score / 0.6)  # 0.6 score → factor 1.0

    return round(time_factor * confidence_factor, 3)
