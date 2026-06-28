"""Plan1 T7 — Predicted-position table + ETA table for one leg.

Callables:
    export_position_table(leg, step_min=2) -> list[[elapsed_min, mile, lat, lon]]
    export_eta_table(leg) -> list[{station_code, p10_min, p50_min, p90_min}]

STDLIB only; no third-party imports at module level.
"""
from __future__ import annotations

from typing import List


# ---------------------------------------------------------------------------
# Helpers shared by both functions
# ---------------------------------------------------------------------------

def _load_engine_ctx(leg: str):
    """Load and return a minimal engine context for the given leg key."""
    import sys
    import json
    from pathlib import Path

    engine_dir = Path(__file__).resolve().parent.parent
    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))

    from position_engine import (
        load_station_catalog,
        load_mileposts,
        build_station_geo,
        parse_timetable,
        compute_schedule,
        build_route_sched,
        load_asmad_runs,
        _load_leg_shapes,
        TIMETABLE_TEXT,
        ITINERARY,
    )

    station_lookup = load_station_catalog()
    mileposts_raw = load_mileposts()
    get_geo = build_station_geo(station_lookup, mileposts_raw)
    tts = {k: parse_timetable(v) for k, v in TIMETABLE_TEXT.items()}
    route_sched = build_route_sched()
    all_runs = load_asmad_runs()
    leg_shapes = _load_leg_shapes()

    all_schedules = {
        k: compute_schedule(k, dep, tts, get_geo)
        for _n, k, _a, dep, _t in ITINERARY
    }

    return {
        "all_runs": all_runs,
        "all_schedules": all_schedules,
        "route_sched": route_sched,
        "leg_shapes": leg_shapes,
        "station_lookup": station_lookup,
    }


# ---------------------------------------------------------------------------
# export_position_table
# ---------------------------------------------------------------------------

def export_position_table(leg: str, step_min: int = 2) -> List[list]:
    """Return [[elapsed_min, mile, lat, lon], ...] at step_min intervals.

    Uses the engine's _weighted_pick / trajectory machinery, sampling the
    p50 position at each elapsed-minute offset across the leg.  Falls back
    to linear interpolation on the timetable when trajectories are sparse.

    Args:
        leg: Timetable key, e.g. "58".
        step_min: Sampling interval in minutes (default 2).

    Returns:
        List of [elapsed_min, mile, lat, lon] rows, monotonic in elapsed_min
        and non-decreasing in mile.
    """
    import sys
    from pathlib import Path

    engine_dir = Path(__file__).resolve().parent.parent
    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))

    from position_engine import (
        _build_trajectories,
        _pos_at,
        _apply_weights,
        _weighted_pick,
        _milepost_latlon,
    )

    ctx = _load_engine_ctx(leg)
    sched = ctx["all_schedules"].get(leg, [])
    if len(sched) < 2:
        return []

    leg_shapes = ctx["leg_shapes"]
    poly = leg_shapes.get(leg)

    built = _build_trajectories(leg, sched, ctx["all_runs"], ctx["route_sched"])
    if not built:
        # Fallback: interpolate schedule directly
        return _schedule_position_table(sched, poly, step_min)

    _anchor, anchor_utc, _anchor_mi, frame, trajs = built

    dep_utc = sched[0]["utc"]
    arr_utc = sched[-1]["utc"]
    total_min = max(1, round((arr_utc - dep_utc) / 60))

    rows = []
    prev_mile = -1.0

    for elapsed_min in range(0, total_min + step_min, step_min):
        off_h = elapsed_min / 60.0

        positions = []
        for t in trajs:
            pr = _pos_at(t["pts"], off_h)
            if pr is not None:
                positions.append({"miles": pr[0], "lat": pr[1], "lon": pr[2], "dhist": None})

        if len(positions) >= 3:
            _apply_weights(positions, None)
            p50 = _weighted_pick(positions, 0.5)
            mile = round(max(p50["miles"], prev_mile), 2)
            lat, lon = p50["lat"], p50["lon"]
            # Snap to polyline if available
            if poly:
                ll = _milepost_latlon(poly, mile)
                if ll:
                    lat, lon = ll
        else:
            # Linear fallback via schedule
            seg = _schedule_interp(sched, dep_utc + elapsed_min * 60)
            if seg is None:
                continue
            mile = round(max(seg[0], prev_mile), 2)
            lat, lon = seg[1], seg[2]
            if poly:
                ll = _milepost_latlon(poly, mile)
                if ll:
                    lat, lon = ll

        rows.append([elapsed_min, mile, round(lat, 5), round(lon, 5)])
        prev_mile = mile

    return rows


def _schedule_interp(sched: list, utc: int):
    """Interpolate (mile, lat, lon) at utc between schedule stations."""
    for i in range(len(sched) - 1):
        s1, s2 = sched[i], sched[i + 1]
        if s1["utc"] <= utc <= s2["utc"]:
            span = s2["utc"] - s1["utc"]
            f = (utc - s1["utc"]) / span if span > 0 else 0.0
            m1, m2 = s1.get("miles") or 0, s2.get("miles") or 0
            la1, lo1 = s1.get("lat") or 0, s1.get("lon") or 0
            la2, lo2 = s2.get("lat") or 0, s2.get("lon") or 0
            return (
                m1 + f * (m2 - m1),
                la1 + f * (la2 - la1),
                lo1 + f * (lo2 - lo1),
            )
    if sched and utc >= sched[-1]["utc"]:
        s = sched[-1]
        return s.get("miles") or 0, s.get("lat") or 0, s.get("lon") or 0
    return None


def _schedule_position_table(sched: list, poly, step_min: int) -> List[list]:
    """Pure-schedule fallback position table."""
    from position_engine import _milepost_latlon

    dep_utc = sched[0]["utc"]
    arr_utc = sched[-1]["utc"]
    total_min = max(1, round((arr_utc - dep_utc) / 60))

    rows = []
    prev_mile = -1.0
    for elapsed_min in range(0, total_min + step_min, step_min):
        seg = _schedule_interp(sched, dep_utc + elapsed_min * 60)
        if seg is None:
            continue
        mile = round(max(seg[0], prev_mile), 2)
        lat, lon = seg[1], seg[2]
        if poly:
            ll = _milepost_latlon(poly, mile)
            if ll:
                lat, lon = ll
        rows.append([elapsed_min, mile, round(lat, 5), round(lon, 5)])
        prev_mile = mile
    return rows


# ---------------------------------------------------------------------------
# export_eta_table
# ---------------------------------------------------------------------------

def export_eta_table(leg: str) -> List[dict]:
    """Return ETA ensemble for every station on leg.

    Uses the engine's eta_to() function to compute p10/p50/p90 ETAs,
    then converts to minutes-from-departure so the app can compute
    absolute timestamps from the actual departure.

    Args:
        leg: Timetable key, e.g. "58".

    Returns:
        List of {station_code, p10_min, p50_min, p90_min} dicts, one per
        intermediate and terminal station, with p10_min <= p50_min <= p90_min.
    """
    import sys
    from pathlib import Path

    engine_dir = Path(__file__).resolve().parent.parent
    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))

    from position_engine import eta_to

    ctx = _load_engine_ctx(leg)
    sched = ctx["all_schedules"].get(leg, [])
    if not sched:
        return []

    dep_utc = sched[0]["utc"]
    rows = []

    for station in sched[1:]:  # skip departure station
        code = station["code"]
        sched_utc = station["utc"]
        eta = eta_to(ctx, code, leg_key=leg)
        if eta is None or "error" in eta:
            # Fallback: use scheduled time as a degenerate p10=p50=p90
            elapsed = round((sched_utc - dep_utc) / 60)
            rows.append({
                "station_code": code,
                "p10_min": elapsed,
                "p50_min": elapsed,
                "p90_min": elapsed,
            })
            continue

        p10_ts = int(eta["p10"].timestamp())
        p50_ts = int(eta["p50"].timestamp())
        p90_ts = int(eta["p90"].timestamp())

        # Convert to minutes from departure
        p10_min = round((p10_ts - dep_utc) / 60)
        p50_min = round((p50_ts - dep_utc) / 60)
        p90_min = round((p90_ts - dep_utc) / 60)

        # Enforce p10 <= p50 <= p90 (engine should already do this, but guard)
        p10_min = min(p10_min, p50_min)
        p90_min = max(p90_min, p50_min)

        rows.append({
            "station_code": code,
            "p10_min": p10_min,
            "p50_min": p50_min,
            "p90_min": p90_min,
        })

    return rows
