#!/usr/bin/env python3
"""
Generate golden projection fixtures by running the real Python position engine.

Run from the repo root (or from tools/amtrak-position-engine):
  cd tools/amtrak-position-engine && python3 -m pipeline.gen_projection_fixtures

Writes:
  packages/companion-core/test/fixtures/projection-leg58.json

Format:
  {
    "polyline": [[mile, lat, lon], ...],          # first 20 verts + last vert (for readability)
    "milepost_cases": [{"mile": m, "lat": lat, "lon": lon}, ...],
    "project_cases":  [{"lat": ..., "lon": ..., "mile": ..., "offtrackMi": ..., "side": ...}, ...]
  }

side vocabulary: 'left' | 'right' | 'ahead'  (Plan 0 §E engine lowercase).
"""
import json
import sys
from math import radians, cos
from pathlib import Path

# Allow running as `python3 pipeline/gen_projection_fixtures.py` or as `-m`
ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from position_engine import _milepost_latlon, project_to_leg, _load_leg_shapes  # noqa: E402

# ── Load leg 58 polyline ───────────────────────────────────────────────────────
shapes = _load_leg_shapes()
if "58" not in shapes:
    raise RuntimeError("leg_shapes.json missing leg 58 — run from tools/amtrak-position-engine")

poly = shapes["58"]
print(f"Loaded leg 58 polyline: {len(poly)} vertices "
      f"[{poly[0][0]}–{poly[-1][0]} mi]")

# ── milepost_cases: test at a spread of miles ─────────────────────────────────
span = poly[-1][0] - poly[0][0]
start_mi = poly[0][0]

miles_to_test = [
    # boundary / clamp cases
    start_mi,                           # exact start
    start_mi - 5.0,                     # below-start clamp
    poly[-1][0],                        # exact end
    poly[-1][0] + 10.0,                 # above-end clamp
]
# Interior samples at 5%, 10%, 25%, 50%, 75%, 90%, 95% of span
for pct in [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]:
    miles_to_test.append(round(start_mi + pct * span, 2))

# Also hit a few vertex anchors directly
for i in [1, 100, 500, 1000, 2000, len(poly) - 2]:
    if 0 <= i < len(poly):
        miles_to_test.append(poly[i][0])

milepost_cases = []
for m in miles_to_test:
    result = _milepost_latlon(poly, m)
    if result is not None:
        lat, lon = result
        milepost_cases.append({
            "mile": round(m, 4),
            "lat":  round(lat, 8),
            "lon":  round(lon, 8),
        })

print(f"Generated {len(milepost_cases)} milepost_cases")

# ── project_cases: on-track, left-offset, right-offset, far-off, deadband ─────
# Sample at ~10 segments evenly spread across the polyline.
n_segs = min(10, len(poly) - 1)
step = max(1, (len(poly) - 1) // n_segs)

project_cases = []

for i in range(0, len(poly) - 1, step):
    m1, la1, lo1 = poly[i]
    m2, la2, lo2 = poly[i + 1]
    mid_lat = (la1 + la2) / 2.0
    mid_lon = (lo1 + lo2) / 2.0

    # Compute a perpendicular offset direction in lat/lon space.
    # Travel vector (equirectangular):
    kx = cos(radians((la1 + la2) / 2.0))
    vx = (lo2 - lo1) * kx   # eastward component
    vy = la2 - la1           # northward component
    v_len = (vx ** 2 + vy ** 2) ** 0.5
    if v_len == 0:
        continue
    # Perpendicular (left): rotate 90° CCW → (-vy, vx) in (east, north)
    # Convert back to (dlat, dlon)
    perp_lat = -vy / v_len   # unit perp in north direction
    perp_lon = vx / v_len    # unit perp in east direction (undone by kx below)
    perp_lon_deg = perp_lon / kx if kx > 0 else 0.0

    for label, dlat, dlon in [
        ("on_track",      0.0,                    0.0),               # exactly on track → ahead
        ("left_small",    perp_lat * 0.02,         perp_lon_deg * 0.02),   # ~1 mi left
        ("right_small",  -perp_lat * 0.02,        -perp_lon_deg * 0.02),   # ~1 mi right
        ("left_large",    perp_lat * 0.15,         perp_lon_deg * 0.15),   # ~7 mi left
        ("right_large",  -perp_lat * 0.15,        -perp_lon_deg * 0.15),   # ~7 mi right
    ]:
        qlat = mid_lat + dlat
        qlon = mid_lon + dlon
        result = project_to_leg(poly, qlat, qlon)
        if result is None:
            continue
        mile, offtrack_mi, side = result
        project_cases.append({
            "_label": f"seg{i}_{label}",
            "lat":         round(qlat, 8),
            "lon":         round(qlon, 8),
            "mile":        round(mile, 4),
            "offtrackMi":  round(offtrack_mi, 4),
            "side":        side,   # 'left' | 'right' | 'ahead' (engine lowercase)
        })

print(f"Generated {len(project_cases)} project_cases "
      f"({sum(1 for c in project_cases if c['side'] == 'ahead')} 'ahead', "
      f"{sum(1 for c in project_cases if c['side'] == 'left')} 'left', "
      f"{sum(1 for c in project_cases if c['side'] == 'right')} 'right')")

# ── Write output ───────────────────────────────────────────────────────────────
# Include the FULL polyline so TS tests use the same vertex set as Python.
# (~2394 vertices, ~71KB — acceptable for a committed golden fixture.)
out = {
    "polyline": poly,
    "milepost_cases": milepost_cases,
    "project_cases":  project_cases,
}

out_path = (
    Path(__file__).resolve().parents[3]
    / "packages" / "companion-core" / "test" / "fixtures" / "projection-leg58.json"
)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(out, indent=2))
print(f"Wrote fixture to {out_path}")
