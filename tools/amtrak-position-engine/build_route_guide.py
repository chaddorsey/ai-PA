#!/usr/bin/env python3
"""
Compile the curated corridor guides (guides/*.yml) + stations into the committed
data/route_guide.json — projecting every feature onto its leg's milepost axis,
computing left/right side from geometry, and validating the §3 schema invariants.

Build-time only (needs PyYAML). Runtime (route_guide.py) reads the JSON, stdlib-only.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import position_engine as E  # noqa: E402

ENGINE_DIR = Path(__file__).resolve().parent
GUIDE_FILES = {
    '3': 'southwest-chief.yml', '2': 'sunset-limited.yml', '58': 'city-of-new-orleans.yml',
    '27': 'empire-builder.yml', '11': 'coast-starlight.yml', '422': 'texas-eagle.yml',
}


def _compile_feature(f, poly):
    lat, lon = float(f['lat']), float(f['lon'])
    peak_mi, offtrack, comp_side = E.project_to_leg(poly, lat, lon)
    if 'from_latlon' in f and 'to_latlon' in f:
        a = E.project_to_leg(poly, *f['from_latlon'])[0]
        b = E.project_to_leg(poly, *f['to_latlon'])[0]
        from_mi, to_mi = sorted((a, b))
    else:
        from_mi = to_mi = peak_mi
    peak_mi = min(max(peak_mi, from_mi), to_mi)
    out = {
        'id': f['id'], 'name': f['name'], 'kind': f['kind'], 'class': f['class'],
        'from_mi': round(from_mi, 1), 'to_mi': round(to_mi, 1), 'peak_mi': round(peak_mi, 1),
        'lat': round(lat, 5), 'lon': round(lon, 5),
        'side': f.get('side', comp_side),
        'salience': int(f['salience']), 'blurb': f.get('blurb', ''),
        'source': 'curated', 'tags': f.get('tags', []),
    }
    if 'elev_ft' in f:
        out['elev_ft'] = f['elev_ft']
    if offtrack and offtrack > 0.5:
        out['offtrack_mi'] = offtrack
    return out


def _stations(tt_key, sched, route_sched, catalog):
    frame = E.build_leg_frame(tt_key, sched, route_sched)
    anchor = next((s['code'] for s in sched if s['code'] in frame), None)
    if not anchor:
        return [], 0.0
    amile = frame[anchor]['miles']
    feats = []
    for code, fr in frame.items():
        si = catalog.get(code, {})
        mi = round(fr['miles'] - amile, 1)
        feats.append({
            'id': f'stn-{code}', 'name': f"{si.get('city', code)}, {si.get('state', '')}".strip(', '),
            'kind': 'station', 'class': 'station',
            'from_mi': mi, 'to_mi': mi, 'peak_mi': mi,
            'lat': round(fr['lat'], 5), 'lon': round(fr['lon'], 5), 'side': 'both',
            'salience': 3 if si.get('major_station') else 2, 'blurb': '', 'source': 'gtfs', 'tags': ['station'],
        })
    leg_miles = max((v['miles'] for v in frame.values()), default=0.0) - amile
    return feats, round(leg_miles, 1)


def _coverage_gaps(feats, leg_miles, min_sal=3, reach=20.0, thresh=40.0):
    """Stretches (mi) with no salience≥min_sal feature span within `reach`. Explicitly
    recorded so the guide is honest about where Phase A is thin (Phase B/C worklist)."""
    cov = []
    for f in feats:
        if f['salience'] >= min_sal:
            a = min(f['from_mi'], f['peak_mi']) - reach
            b = max(f['to_mi'], f['peak_mi']) + reach
            cov.append((max(0.0, a), b))
    cov.sort()
    gaps, cur = [], 0.0
    for a, b in cov:
        if a > cur + thresh:
            gaps.append([round(cur, 0), round(a, 0)])
        cur = max(cur, b)
    if leg_miles - cur > thresh:
        gaps.append([round(cur, 0), round(leg_miles, 0)])
    return gaps


def _validate(leg, feats):
    ids = set()
    last = -1e9
    for f in feats:
        assert f['from_mi'] <= f['peak_mi'] <= f['to_mi'], f"{leg}:{f['id']} milepost order"
        assert 1 <= f['salience'] <= 5, f"{leg}:{f['id']} salience"
        assert f['id'] not in ids, f"{leg}:{f['id']} duplicate id"
        ids.add(f['id'])
        assert f['peak_mi'] >= last - 1e-6, f"{leg}:{f['id']} not sorted"
        last = f['peak_mi']


def main():
    import yaml
    ctx = E.load_engine()
    catalog = ctx['station_lookup']
    out = {}
    for tt_key, fname in GUIDE_FILES.items():
        poly = ctx['leg_shapes'].get(tt_key)
        sched = ctx['all_schedules'].get(tt_key, [])
        if not poly or len(sched) < 2:
            print(f"  leg {tt_key}: skipped (no polyline/schedule)")
            continue
        g = yaml.safe_load((ENGINE_DIR / 'guides' / fname).read_text())
        curated = [_compile_feature(f, poly) for f in g.get('features', [])]
        stations, leg_miles = _stations(tt_key, sched, ctx['route_sched'], catalog)
        feats = sorted(curated + stations, key=lambda x: x['peak_mi'])
        _validate(tt_key, feats)
        gaps = _coverage_gaps(feats, leg_miles)
        out[tt_key] = {'corridor': g.get('corridor', ''), 'leg_miles': leg_miles,
                       'coverage_gaps': gaps, 'features': feats}
        print(f"  leg {tt_key} ({g.get('corridor','')}): {len(stations)} stations + {len(curated)} curated "
              f"= {len(feats)} features; {len(gaps)} salience≥3 gap(s) "
              f"(max {max((b-a for a,b in gaps), default=0):.0f} mi)")
    (E.DATA_DIR / 'route_guide.json').write_text(json.dumps(out))
    print(f"Wrote {E.DATA_DIR / 'route_guide.json'} ({len(out)} legs)")


if __name__ == '__main__':
    main()
