"""Plan1 T6 — Per-leg bundle assembly + validation.

Callables:
    build_bundle(leg, outdir, proxy=False) -> dict
        Assembles bundles/leg<leg>/bundle.json from narration, timetable,
        leg_shapes, station catalog, data layers, position/eta tables.
        In proxy mode writes a placeholder .mp3 (reuses smoke clip if available).

    validate_bundle(leg, outdir=None) -> list[str]
        Returns [] for a valid bundle; one problem string per issue found.

STDLIB only (no pip). All imports inside functions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, List


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_ENGINE_ROOT = Path(__file__).resolve().parent.parent   # tools/amtrak-position-engine/

# Minimal valid ID3v2 header for a 0-second MP3 placeholder.
# ID3v2.3, no flags, 0-byte payload (syncsafe size=0).
_MINIMAL_MP3_HEADER = (
    b"ID3\x03\x00\x00"   # ID3v2.3, no flags
    b"\x00\x00\x00\x00"  # syncsafe size = 0
)

# July 2026 itinerary dates per leg
_LEG_DATES = {
    "3":   "2026-07-06",
    "2":   "2026-07-08",
    "58":  "2026-07-11",
    "27":  "2026-07-12",
    "11":  "2026-07-16",
    "422": "2026-07-19",
}


# ---------------------------------------------------------------------------
# Public: build_bundle
# ---------------------------------------------------------------------------

def build_bundle(leg: str, outdir, proxy: bool = False) -> dict:
    """Assemble a Plan-0-compliant bundle.json for one leg.

    Args:
        leg: Timetable key (e.g. "58").
        outdir: Path-like base directory; bundle written to outdir/leg<leg>/.
        proxy: If True, write placeholder .mp3 audio instead of real renders.

    Returns:
        The bundle dict (also written to outdir/leg<leg>/bundle.json).
    """
    import json
    import sys

    outdir = Path(outdir)
    leg_dir = outdir / f"leg{leg}"
    audio_dir = leg_dir / "audio"
    leg_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(exist_ok=True)

    if str(_ENGINE_ROOT) not in sys.path:
        sys.path.insert(0, str(_ENGINE_ROOT))

    from position_engine import (
        load_station_catalog,
        load_mileposts,
        build_station_geo,
        parse_timetable,
        compute_schedule,
        build_route_sched,
        _load_leg_shapes,
        TIMETABLE_TEXT,
        ITINERARY,
        DATA_DIR,
    )

    # ── Load engine data ──────────────────────────────────────────────────────
    station_lookup = load_station_catalog()
    mileposts_raw = load_mileposts()
    get_geo = build_station_geo(station_lookup, mileposts_raw)
    tts = {k: parse_timetable(v) for k, v in TIMETABLE_TEXT.items()}
    route_sched = build_route_sched()
    leg_shapes = _load_leg_shapes()

    dep_date = _LEG_DATES.get(leg, "2026-07-11")
    sched = compute_schedule(leg, dep_date, tts, get_geo)

    # ── Narration units ───────────────────────────────────────────────────────
    narr_path = DATA_DIR / "route_narration.json"
    with open(narr_path) as f:
        narr = json.load(f)
    raw_units = narr.get(leg, [])

    # ── Proxy audio or locate smoke clip ─────────────────────────────────────
    smoke_dir = _ENGINE_ROOT / "bundles" / "_smoke"
    smoke_mp3 = next(smoke_dir.glob("*.mp3"), None) if smoke_dir.exists() else None

    def _write_proxy_audio(unit_id: str, text: str) -> tuple:
        """Return (relative_path, dur_s) for a proxy audio file."""
        fname = f"{unit_id}.mp3"
        dest = audio_dir / fname
        if not dest.exists():
            if smoke_mp3 and smoke_mp3.exists():
                import shutil
                shutil.copy2(smoke_mp3, dest)
            else:
                dest.write_bytes(_MINIMAL_MP3_HEADER)
        # Estimate duration: ~2.5 words per second, 1 word ≈ 5 chars
        word_count = max(1, len(text.split()))
        dur_s = round(word_count / 2.5, 1)
        return f"audio/{fname}", dur_s

    # ── Build units list ──────────────────────────────────────────────────────
    units = []
    for idx, raw in enumerate(raw_units):
        uid = f"{leg}-{idx}"
        text = raw.get("text", "")

        if proxy:
            audio_rel, dur_s = _write_proxy_audio(uid, text)
        else:
            # Non-proxy: audio produced by render pipeline; look for cached file
            import hashlib
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            audio_rel = f"audio/{content_hash}.mp3"
            dur_s = round(max(1, len(text.split())) / 2.5, 1)

        unit = {
            "id": uid,
            "kind": raw.get("kind", "squib"),
            "salience": int(raw.get("salience", 3)),
            "theme": raw.get("theme", ""),
            "text": text,
            "lat": raw.get("lat"),
            "lon": raw.get("lon"),
            "side": raw.get("side"),
            "place": raw.get("place"),
            "audio": audio_rel,
            "dur_s": dur_s,
        }
        # squib-specific
        if raw.get("kind") == "squib":
            unit["mile"] = raw.get("mile")
            unit["poi_lat"] = raw.get("poi_lat")
            unit["poi_lon"] = raw.get("poi_lon")
            unit["offtrack_mi"] = raw.get("offtrack_mi")
        # interstitial-specific
        if raw.get("kind") == "interstitial":
            unit["from_mi"] = raw.get("from_mi")
            unit["to_mi"] = raw.get("to_mi")
        units.append(unit)

    # ── Stations list (from schedule + timetable JSON) ────────────────────────
    tt_raw_path = DATA_DIR / "amtrak_published_timetables.json"
    with open(tt_raw_path) as f:
        tt_raw = json.load(f)
    tt_entries = {e["code"]: e for e in tt_raw.get(leg, [])}

    dep_utc = sched[0]["utc"] if sched else 0
    stations = []
    for s in sched:
        code = s["code"]
        raw_tt = tt_entries.get(code, {})
        kind = raw_tt.get("kind", "intermediate")

        # Build ISO timestamps from epoch
        sched_arr = None
        sched_dep = None
        if kind == "departure":
            sched_dep = _epoch_to_iso(s["utc"], s.get("tz", "America/Chicago"))
        elif kind == "arrival":
            sched_arr = _epoch_to_iso(s["utc"], s.get("tz", "America/Chicago"))
        else:
            sched_arr = _epoch_to_iso(s["utc"], s.get("tz", "America/Chicago"))
            sched_dep = sched_arr  # intermediate: same time for arr/dep (published)

        # Dwell: difference between arr and dep in published timetable
        dwell_min = 0
        if kind == "intermediate":
            # Try to find a dep time in the TIMETABLE_TEXT parse
            dep_row = _find_dep_time(leg, code)
            if dep_row and dep_row != s["utc"]:
                dwell_min = max(0, round((dep_row - s["utc"]) / 60))

        stations.append({
            "code": code,
            "name": raw_tt.get("name", f"{s.get('city','')}, {s.get('state','')}").strip(", "),
            "mile": round(s["miles"], 1) if s.get("miles") is not None else None,
            "lat": round(s["lat"], 5) if s.get("lat") else None,
            "lon": round(s["lon"], 5) if s.get("lon") else None,
            "sched_arr": sched_arr,
            "sched_dep": sched_dep,
            "dwell_min": dwell_min,
        })

    # ── Geometry from leg_shapes ──────────────────────────────────────────────
    poly = leg_shapes.get(leg, [])
    # GeoJSON LineString: coordinates = [[lon, lat], ...]
    coords = [[round(pt[2], 5), round(pt[1], 5)] for pt in poly]
    geometry = {"type": "LineString", "coordinates": coords}

    # ── Schedule basis ────────────────────────────────────────────────────────
    valid_date = _LEG_DATES.get(leg)
    schedule_basis = {
        "kind": "trip-actual" if valid_date else "generic-scheduled",
        "valid_dates": [valid_date] if valid_date else [],
    }

    # ── Data layers ───────────────────────────────────────────────────────────
    layers = _load_layers(leg, DATA_DIR)

    # ── Position table ────────────────────────────────────────────────────────
    from pipeline.position_table import export_position_table, export_eta_table

    position_table = export_position_table(leg, step_min=2)
    eta_table = export_eta_table(leg)

    # ── Assemble bundle ───────────────────────────────────────────────────────
    bundle = {
        "leg": leg,
        "proxy": proxy,
        "schedule_basis": schedule_basis,
        "stations": stations,
        "geometry": geometry,
        "units": units,
        "layers": layers,
        "position_table": position_table,
        "eta_table": eta_table,
    }

    bundle_path = leg_dir / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2))
    return bundle


# ---------------------------------------------------------------------------
# Public: validate_bundle
# ---------------------------------------------------------------------------

def validate_bundle(leg: str, outdir=None) -> List[str]:
    """Validate an assembled bundle.json for leg.

    Args:
        leg: Timetable key (e.g. "58").
        outdir: Directory containing leg<leg>/bundle.json.  Defaults to the
                standard bundles/ dir inside the engine root.

    Returns:
        [] for a clean bundle; list of problem strings otherwise.
    """
    import json

    if outdir is None:
        outdir = _ENGINE_ROOT / "bundles"
    else:
        outdir = Path(outdir)

    bundle_path = outdir / f"leg{leg}" / "bundle.json"
    if not bundle_path.exists():
        return [f"bundle.json not found at {bundle_path}"]

    try:
        bundle = json.loads(bundle_path.read_text())
    except Exception as e:
        return [f"bundle.json parse error: {e}"]

    problems = []
    leg_dir = bundle_path.parent

    # Top-level fields
    required_fields = {
        "leg", "schedule_basis", "stations", "geometry", "units",
        "layers", "position_table", "eta_table", "proxy",
    }
    for f in required_fields:
        if f not in bundle:
            problems.append(f"missing top-level field: '{f}'")

    # Stations
    stations = bundle.get("stations", [])
    if not stations:
        problems.append("stations list is empty")
    for s in stations:
        for k in ("code", "name", "mile", "lat", "lon", "sched_arr", "sched_dep", "dwell_min"):
            if k not in s:
                problems.append(f"station {s.get('code','?')} missing key '{k}'")

    # Geometry
    geom = bundle.get("geometry", {})
    coords = geom.get("coordinates", [])
    if len(coords) < 2:
        problems.append(f"geometry has {len(coords)} coordinates (need >= 2)")

    # Units
    units = bundle.get("units", [])
    if not units:
        problems.append("units list is empty")
    for u in units:
        uid = u.get("id", "?")
        if "audio" not in u:
            problems.append(f"unit {uid}: missing 'audio' field")
            continue
        audio_path = leg_dir / u["audio"]
        if not audio_path.exists():
            problems.append(f"unit {uid}: audio file missing: {u['audio']}")
        if "dur_s" not in u:
            problems.append(f"unit {uid}: missing 'dur_s'")
        salience = u.get("salience")
        if salience is not None and (not isinstance(salience, int) or not (1 <= salience <= 5)):
            problems.append(f"unit {uid}: salience must be int 1-5, got {salience!r}")

    # Layers
    layers = bundle.get("layers", {})
    for k in ("guide", "lore", "science", "connections", "themes"):
        if k not in layers:
            problems.append(f"layers missing key '{k}'")

    # Position table
    pt = bundle.get("position_table", [])
    if not pt:
        problems.append("position_table is empty")

    # ETA table
    eta = bundle.get("eta_table", [])
    for row in eta:
        if row.get("p10_min", 0) > row.get("p50_min", 0):
            problems.append(f"eta_table {row.get('station_code')}: p10 > p50")
        if row.get("p50_min", 0) > row.get("p90_min", 0):
            problems.append(f"eta_table {row.get('station_code')}: p50 > p90")

    return problems


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _epoch_to_iso(utc_epoch: int, tz_name: str) -> str:
    """Convert a UTC epoch to an ISO-8601 string in the given timezone."""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(utc_epoch, tz=timezone.utc).astimezone(ZoneInfo(tz_name))
    except Exception:
        try:
            import pytz
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(utc_epoch, tz=timezone.utc).astimezone(pytz.timezone(tz_name))
        except Exception:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(utc_epoch, tz=timezone.utc)
    return dt.isoformat()


def _find_dep_time(leg: str, code: str) -> Optional[int]:
    """Parse the departure time for an intermediate station from TIMETABLE_TEXT.

    Returns UTC epoch for the departure row, or None if not found.
    """
    import sys
    if str(_ENGINE_ROOT) not in sys.path:
        sys.path.insert(0, str(_ENGINE_ROOT))

    try:
        from position_engine import TIMETABLE_TEXT, parse_timetable, _LEG_DATES  # type: ignore
    except ImportError:
        return None

    # _LEG_DATES is defined here, not in engine
    dep_date = _LEG_DATES.get(leg, "2026-07-11")
    try:
        from position_engine import parse_timetable, parse_time_str
        text = TIMETABLE_TEXT.get(leg, "")
        import re
        for line in text.strip().split("\n"):
            # Match: "arr_time | dep_time - Name (CODE)"
            m = re.match(
                r"(\d{1,2}:\d{2}[ap])\s*\|\s*(\d{1,2}:\d{2}[ap])\s*-\s*.+\s+\(([A-Z]{2,4})\)",
                line.strip(), re.I,
            )
            if m and m.group(3) == code:
                dep_time_str = m.group(2)
                # Determine timezone from station catalog
                tz_str = "America/Chicago"  # safe default for CONO leg
                return int(parse_time_str(dep_time_str, tz_str, dep_date))
    except Exception:
        pass
    return None


def _load_layers(leg: str, data_dir: Path) -> dict:
    """Load the data layer slices for this leg from data/ JSON files."""
    import json

    def _load_json(name: str) -> dict:
        p = data_dir / name
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return {}
        return {}

    guide = _load_json("route_guide.json")
    lore = _load_json("route_lore.json")
    science = _load_json("route_science.json")
    connections = _load_json("route_connections.json")
    themes = _load_json("route_themes.json")

    return {
        "guide": guide.get(leg, {}),
        "lore": lore.get(leg, {}),
        "science": science.get(leg, {}),
        "connections": connections.get(leg, {}),
        "themes": themes.get(leg, {}),
    }
