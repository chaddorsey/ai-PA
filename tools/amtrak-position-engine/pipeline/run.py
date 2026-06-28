"""Plan1 CLI orchestrator — Tasks 4, 6, 7.

Subcommands:
    estimate               — print cost gate (chars + $low-$high) for full corpus
    bundle <leg>           — assemble a proxy bundle for one leg
    postable <leg>         — print position/eta table stats for a leg
    proxy <leg>            — alias for `bundle <leg>` with proxy=True (default)
    validate <leg>         — run validate_bundle and print results

Usage:
    python3 -m pipeline.run estimate
    python3 -m pipeline.run proxy 58
    python3 -m pipeline.run bundle 58
    python3 -m pipeline.run postable 58
    python3 -m pipeline.run validate 58
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ENGINE_ROOT = Path(__file__).resolve().parent.parent
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

# ── Cost constants ─────────────────────────────────────────────────────────
_CHIRP3_USD_PER_M_LOW = 30.0   # $30/1M chars (low estimate)
_CHIRP3_USD_PER_M_HIGH = 45.0  # $45/1M chars (high estimate)

# ── Leg order for full-corpus display ─────────────────────────────────────
_ALL_LEGS = ["3", "2", "58", "27", "11", "422"]

_LEG_NAMES = {
    "3": "Southwest Chief",
    "2": "Sunset Limited",
    "58": "City of New Orleans",
    "27": "Empire Builder",
    "11": "Coast Starlight",
    "422": "Texas Eagle",
}


# ---------------------------------------------------------------------------
# estimate
# ---------------------------------------------------------------------------

def cmd_estimate():
    """Print char count + cost estimate for the full corpus and per-leg."""
    narr_path = _ENGINE_ROOT / "data" / "route_narration.json"
    with open(narr_path) as f:
        narr = json.load(f)

    print("=" * 62)
    print("  CORPUS COST ESTIMATE — Chirp3-HD MP3")
    print("=" * 62)
    print(f"  {'Leg':<6} {'Name':<24} {'Units':>6} {'Chars':>9} {'$low':>7} {'$high':>7}")
    print(f"  {'-'*6} {'-'*24} {'-'*6} {'-'*9} {'-'*7} {'-'*7}")

    total_chars = 0
    for leg in _ALL_LEGS:
        units = narr.get(leg, [])
        chars = sum(len(u.get("text", "")) for u in units)
        total_chars += chars
        usd_low = chars * _CHIRP3_USD_PER_M_LOW / 1_000_000
        usd_high = chars * _CHIRP3_USD_PER_M_HIGH / 1_000_000
        name = _LEG_NAMES.get(leg, leg)
        print(f"  {leg:<6} {name:<24} {len(units):>6,} {chars:>9,} ${usd_low:>6.2f} ${usd_high:>6.2f}")

    usd_low_total = total_chars * _CHIRP3_USD_PER_M_LOW / 1_000_000
    usd_high_total = total_chars * _CHIRP3_USD_PER_M_HIGH / 1_000_000
    print(f"  {'':6} {'TOTAL':<24} {'':>6} {total_chars:>9,} ${usd_low_total:>6.2f} ${usd_high_total:>6.2f}")
    print("=" * 62)
    print()
    print(f"  ⚠  switch GCP billing card before a full render")
    print()


# ---------------------------------------------------------------------------
# bundle / proxy
# ---------------------------------------------------------------------------

def cmd_bundle(leg: str, proxy: bool = True):
    """Assemble a bundle for one leg (proxy mode by default)."""
    from pipeline.bundle import build_bundle

    bundles_dir = _ENGINE_ROOT / "bundles"
    bundles_dir.mkdir(exist_ok=True)

    print(f"Building {'proxy ' if proxy else ''}bundle for leg {leg} ({_LEG_NAMES.get(leg, leg)})…")
    bundle = build_bundle(leg, bundles_dir, proxy=proxy)

    unit_count = len(bundle["units"])
    station_count = len(bundle["stations"])
    geo_pts = len(bundle["geometry"]["coordinates"])
    eta_count = len(bundle["eta_table"])
    pos_rows = len(bundle["position_table"])

    # Compute approximate bundle.json size
    bundle_path = bundles_dir / f"leg{leg}" / "bundle.json"
    bundle_mb = bundle_path.stat().st_size / 1_048_576

    # Audio dir size
    audio_dir = bundles_dir / f"leg{leg}" / "audio"
    audio_mb = 0.0
    if audio_dir.exists():
        audio_mb = sum(f.stat().st_size for f in audio_dir.glob("*.mp3")) / 1_048_576

    print(f"  proxy       : {bundle['proxy']}")
    print(f"  units       : {unit_count}")
    print(f"  stations    : {station_count}")
    print(f"  geometry pts: {geo_pts}")
    print(f"  eta table   : {eta_count} stations")
    print(f"  pos table   : {pos_rows} rows")
    print(f"  bundle.json : {bundle_mb:.2f} MB")
    print(f"  audio/      : {audio_mb:.2f} MB  (placeholder)")
    print(f"  total       : {bundle_mb + audio_mb:.2f} MB")
    print(f"  written to  : {bundle_path}")
    return bundle


# ---------------------------------------------------------------------------
# postable
# ---------------------------------------------------------------------------

def cmd_postable(leg: str):
    """Print position/eta table stats for a leg."""
    from pipeline.position_table import export_position_table, export_eta_table

    print(f"Position table for leg {leg} ({_LEG_NAMES.get(leg, leg)})…")
    rows = export_position_table(leg, step_min=2)
    print(f"  rows: {len(rows)}")
    if rows:
        print(f"  first: elapsed={rows[0][0]}min  mile={rows[0][1]}  lat={rows[0][2]}  lon={rows[0][3]}")
        print(f"  last:  elapsed={rows[-1][0]}min  mile={rows[-1][1]}  lat={rows[-1][2]}  lon={rows[-1][3]}")

    print(f"ETA table for leg {leg}…")
    eta = export_eta_table(leg)
    print(f"  stations: {len(eta)}")
    for row in eta[:3]:
        print(f"    {row['station_code']}: p10={row['p10_min']}min p50={row['p50_min']}min p90={row['p90_min']}min")
    if len(eta) > 3:
        print(f"    … ({len(eta)-3} more)")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def cmd_validate(leg: str):
    """Validate a bundle and print results."""
    from pipeline.bundle import validate_bundle

    bundles_dir = _ENGINE_ROOT / "bundles"
    print(f"Validating leg {leg} bundle…")
    problems = validate_bundle(leg, outdir=bundles_dir)
    if not problems:
        print(f"  OK — bundle is clean (0 problems)")
    else:
        print(f"  {len(problems)} problem(s):")
        for p in problems:
            print(f"    - {p}")
    return problems


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0].lower()

    if cmd == "estimate":
        cmd_estimate()

    elif cmd in ("proxy", "bundle"):
        if len(args) < 2:
            print(f"Usage: python3 -m pipeline.run {cmd} <leg>")
            sys.exit(1)
        leg = args[1]
        cmd_bundle(leg, proxy=True)

    elif cmd == "postable":
        if len(args) < 2:
            print("Usage: python3 -m pipeline.run postable <leg>")
            sys.exit(1)
        cmd_postable(args[1])

    elif cmd == "validate":
        if len(args) < 2:
            print("Usage: python3 -m pipeline.run validate <leg>")
            sys.exit(1)
        problems = cmd_validate(args[1])
        sys.exit(1 if problems else 0)

    else:
        print(f"Unknown command: {cmd!r}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
