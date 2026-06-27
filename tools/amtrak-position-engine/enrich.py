#!/usr/bin/env python3
"""
Route-guide enrichment (Phases B/C/E) — adds features to data/route_guide.json from
external sources, projected onto each leg's milepost axis. Build-time + network;
the committed route_guide.json is the result. Re-run after build_route_guide.py.

Each enricher is idempotent: it removes its own prior features (by `source`) before
re-adding, so `enrich.py towns counties` can be run repeatedly.

  python3 enrich.py towns                 # Phase C: GeoNames populated places
  python3 enrich.py towns counties        # + county-name spans (FCC, keyless)
  python3 enrich.py all

Downloads are cached in .cache/ (gitignored). Runtime stays stdlib-only; this build
tool uses only stdlib too (urllib/zipfile/json).
"""
import json
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import zipfile
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import position_engine as E   # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'
CACHE = Path(__file__).resolve().parent / '.cache'
GUIDE = DATA / 'route_guide.json'
UA = {'User-Agent': 'amtrak-route-guide-enrich/1.0'}


def _load():
    guide = json.loads(GUIDE.read_text())
    shapes = json.loads((DATA / 'leg_shapes.json').read_text())
    return guide, shapes


def _save(guide):
    for leg in guide:
        guide[leg]['features'].sort(key=lambda f: f['peak_mi'])
    GUIDE.write_text(json.dumps(guide))


def _drop_source(guide, src):
    for leg in guide:
        guide[leg]['features'] = [f for f in guide[leg]['features'] if f.get('source') != src]


def _bbox(poly, margin=0.6):
    las = [p[1] for p in poly]
    los = [p[2] for p in poly]
    return min(las) - margin, max(las) + margin, min(los) - margin, max(los) + margin


def _cache_get(name, url, unzip_member=None):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / name
    if not p.exists():
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
        if unzip_member:
            raw = zipfile.ZipFile(io.BytesIO(raw)).read(unzip_member)
        p.write_bytes(raw)
    return p


# ── Phase C: populated places (GeoNames, keyless) ──────────────────

def _pop_salience(pop):
    return 4 if pop >= 50000 else 3 if pop >= 10000 else 2 if pop >= 2000 else 1


def _offtrack_limit(pop):
    return 25.0 if pop >= 50000 else 12.0 if pop >= 10000 else 6.0


def enrich_towns(guide, shapes):
    src = 'geonames'
    path = _cache_get('cities1000.txt', 'https://download.geonames.org/export/dump/cities1000.zip',
                      unzip_member='cities1000.txt')
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        c = line.split('\t')
        if len(c) < 15 or c[8] != 'US' or c[6] != 'P':
            continue
        try:
            rows.append((c[1], float(c[4]), float(c[5]), int(c[14] or 0)))
        except ValueError:
            continue
    _drop_source(guide, src)
    total = 0
    for leg, poly in shapes.items():
        if leg not in guide:
            continue
        la0, la1, lo0, lo1 = _bbox(poly)
        existing_mi = [f['peak_mi'] for f in guide[leg]['features'] if f['class'] in ('station', 'place')]
        added = []
        for name, lat, lon, pop in rows:
            if not (la0 <= lat <= la1 and lo0 <= lon <= lo1):
                continue
            mile, off, side = E.project_to_leg(poly, lat, lon)
            if off > _offtrack_limit(pop):
                continue
            if any(abs(mile - m) < 3.0 for m in existing_mi):  # dedupe vs stations & kept towns
                continue
            existing_mi.append(mile)
            kind = 'city' if pop >= 50000 else 'town'
            feat = {'id': f'geo-{leg}-{round(mile)}-{name[:12].lower().replace(" ", "-")}',
                    'name': name, 'kind': kind, 'class': 'place',
                    'from_mi': mile, 'to_mi': mile, 'peak_mi': mile,
                    'lat': round(lat, 5), 'lon': round(lon, 5), 'side': side,
                    'salience': _pop_salience(pop), 'blurb': f'pop. {pop:,}',
                    'source': src, 'tags': ['town']}
            if off > 0.5:
                feat['offtrack_mi'] = off
            added.append(feat)
        guide[leg]['features'].extend(added)
        total += len(added)
        print(f"  leg {leg}: +{len(added)} towns")
    print(f"  towns total: +{total}")


# ── Phase C/E: county-traversal spans (FCC, keyless) + ACS stats ───

def _latlon_at(poly, mile):
    if mile <= poly[0][0]:
        return poly[0][1], poly[0][2]
    if mile >= poly[-1][0]:
        return poly[-1][1], poly[-1][2]
    for i in range(len(poly) - 1):
        m1, la1, lo1 = poly[i]
        m2, la2, lo2 = poly[i + 1]
        if m1 <= mile <= m2:
            f = (mile - m1) / (m2 - m1) if m2 != m1 else 0.0
            return la1 + f * (la2 - la1), lo1 + f * (lo2 - lo1)
    return poly[-1][1], poly[-1][2]


def _fcc_county(lat, lon):
    try:
        url = f"https://geo.fcc.gov/api/census/area?lat={lat:.4f}&lon={lon:.4f}&format=json"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            res = json.load(r).get('results') or []
        if res:
            a = res[0]
            return [a['county_fips'], a['county_name'], a['state_code']]
    except Exception:
        pass
    return None


def enrich_counties(guide, shapes, step_mi=12.0):
    src = 'fcc-county'
    CACHE.mkdir(exist_ok=True)
    cf = CACHE / 'fcc.json'
    cache = json.loads(cf.read_text()) if cf.exists() else {}
    _drop_source(guide, src)
    for leg, poly in shapes.items():
        if leg not in guide:
            continue
        legmi = poly[-1][0]
        spans, mile = [], 0.0
        while mile <= legmi:
            la, lo = _latlon_at(poly, mile)
            k = f"{la:.3f},{lo:.3f}"
            if k not in cache:
                cache[k] = _fcc_county(la, lo)
                time.sleep(0.03)
            co = cache[k]
            if co:
                if spans and spans[-1]['fips'] == co[0]:
                    spans[-1]['to'] = mile
                else:
                    spans.append({'fips': co[0], 'name': co[1], 'state': co[2], 'from': mile, 'to': mile})
            mile += step_mi
        for s in spans:
            mid = (s['from'] + s['to']) / 2
            la, lo = _latlon_at(poly, mid)
            guide[leg]['features'].append({
                'id': f"co-{leg}-{s['fips']}-{round(s['from'])}", 'name': f"{s['name']}, {s['state']}",
                'kind': 'county', 'class': 'area',
                'from_mi': round(s['from'], 1), 'to_mi': round(s['to'], 1), 'peak_mi': round(mid, 1),
                'lat': round(la, 5), 'lon': round(lo, 5), 'side': 'both', 'salience': 1,
                'blurb': '', 'source': src, 'tags': ['county'],
                'stats': {'geo': f"{s['name']}, {s['state']}", 'fips': s['fips']}})
        cf.write_text(json.dumps(cache))
        print(f"  leg {leg}: {len(spans)} county spans")


# ACS Data-Profile variables → labels
_DEMO = {'population': 'DP05_0001E', 'median_age': 'DP05_0018E',
         'median_hh_income': 'DP03_0062E', 'poverty_pct': 'DP03_0128PE', 'ba_plus_pct': 'DP02_0068PE'}
_OCC = [('management/business/science/arts', 'DP03_0027PE'), ('service', 'DP03_0028PE'),
        ('sales/office', 'DP03_0029PE'), ('natural resources/construction', 'DP03_0030PE'),
        ('production/transportation', 'DP03_0031PE')]
_IND = [('agriculture/mining', 'DP03_0033PE'), ('construction', 'DP03_0034PE'),
        ('manufacturing', 'DP03_0035PE'), ('wholesale', 'DP03_0036PE'), ('retail', 'DP03_0037PE'),
        ('transport/utilities', 'DP03_0038PE'), ('information', 'DP03_0039PE'),
        ('finance/real estate', 'DP03_0040PE'), ('professional/mgmt', 'DP03_0041PE'),
        ('education/health', 'DP03_0042PE'), ('arts/food/hospitality', 'DP03_0043PE'),
        ('other services', 'DP03_0044PE'), ('public administration', 'DP03_0045PE')]


def _census_key():
    import os
    k = os.environ.get('CENSUS_API_KEY')
    if k:
        return k
    envf = Path(__file__).resolve().parents[2] / '.env'
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith('CENSUS_API_KEY='):
                return line.split('=', 1)[1].strip()
    return None


def _num(v):
    try:
        f = float(v)
        return None if f < -1e6 else (int(f) if f == int(f) else round(f, 1))
    except (TypeError, ValueError):
        return None


def _build_stats(m):
    st = {}
    for label, var in _DEMO.items():
        v = _num(m.get(var))
        if v is not None:
            st[label] = v
    occ = sorted(((lbl, _num(m.get(var)) or 0) for lbl, var in _OCC), key=lambda x: -x[1])
    ind = sorted(((lbl, _num(m.get(var)) or 0) for lbl, var in _IND), key=lambda x: -x[1])
    st['top_occupations'] = [lbl for lbl, _ in occ[:2]]
    st['top_industries'] = [lbl for lbl, _ in ind[:3]]
    st['source'] = 'ACS 2022 5-yr (Census Data Profiles)'
    st['vintage'] = 2022
    return st


def _county_blurb(s):
    bits = []
    if s.get('population'):
        p = s['population']
        bits.append(f"~{p//1000}k people" if p >= 1000 else f"{p} people")
    if s.get('top_industries'):
        bits.append("mostly " + ", ".join(s['top_industries'][:2]))
    if s.get('median_hh_income'):
        bits.append(f"median HH income ~${s['median_hh_income']//1000}k")
    return "; ".join(bits)


def enrich_acs(guide, shapes):
    key = _census_key()
    if not key:
        print("  no CENSUS_API_KEY in env/.env — skipping ACS stats")
        return
    by_state = {}
    for leg in guide:
        for f in guide[leg]['features']:
            if f.get('kind') == 'county':
                by_state.setdefault(f['stats']['fips'][:2], True)
    getlist = 'NAME,' + ','.join(list(_DEMO.values()) + [v for _, v in _OCC] + [v for _, v in _IND])
    data = {}
    for st in sorted(by_state):
        url = (f"https://api.census.gov/data/2022/acs/acs5/profile?get={getlist}"
               f"&for=county:*&in=state:{st}&key={key}")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                rows = json.load(r)
            hdr = rows[0]
            for row in rows[1:]:
                mm = dict(zip(hdr, row))
                data[mm['state'] + mm['county']] = _build_stats(mm)
        except Exception as e:
            print(f"  state {st}: ACS pull failed ({e})")
    filled = 0
    for leg in guide:
        for f in guide[leg]['features']:
            if f.get('kind') == 'county' and f['stats']['fips'] in data:
                f['stats'].update(data[f['stats']['fips']])
                f['blurb'] = _county_blurb(f['stats'])
                filled += 1
    print(f"  ACS stats filled: {filled} county features across {len(by_state)} states")


# ── Phase B: elevation profile + auto passes/summits (open-meteo, keyless) ──

def _elev_batch(points, tries=5):
    lats = ','.join(f"{la:.4f}" for la, lo in points)
    lons = ','.join(f"{lo:.4f}" for la, lo in points)
    url = f"https://api.open-meteo.com/v1/elevation?latitude={lats}&longitude={lons}"
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r).get('elevation', [])
        except urllib.error.HTTPError as e:
            if e.code == 429 and t < tries - 1:
                time.sleep(4 * (t + 1))
                continue
            raise
    return []


def _detect_passes(prof, window=8, prominence_ft=500):
    """Local maxima in [(mile,ft),...] that rise ≥ prominence above the lower side
    within ±window samples → passes/summits."""
    out = []
    for i in range(len(prof)):
        lo = max(0, i - window)
        hi = min(len(prof), i + window + 1)
        seg = prof[lo:hi]
        peak = max(s[1] for s in seg)
        if prof[i][1] == peak and prof[i][1] - min(s[1] for s in seg) >= prominence_ft:
            if not out or prof[i][0] - out[-1][0] > window:  # space them out
                out.append(prof[i])
    return out


def enrich_elevation(guide, shapes, step_mi=5.0):
    src = 'elevation'
    CACHE.mkdir(exist_ok=True)
    cf = CACHE / 'elev.json'
    cache = json.loads(cf.read_text()) if cf.exists() else {}
    _drop_source(guide, src)
    M2FT = 3.28084
    for leg, poly in shapes.items():
        if leg not in guide:
            continue
        if leg not in cache:
            legmi = poly[-1][0]
            miles, m = [], 0.0
            while m <= legmi:
                miles.append(round(m, 1))
                m += step_mi
            pts = [_latlon_at(poly, mm) for mm in miles]
            elevs = []
            for i in range(0, len(pts), 100):
                elevs += _elev_batch(pts[i:i + 100])
                time.sleep(1.5)
            cache[leg] = [[mi, round(e * M2FT)] for mi, e in zip(miles, elevs) if e is not None]
            cf.write_text(json.dumps(cache))
        prof = cache[leg]
        guide[leg]['elevation_ft'] = prof[::2]   # ~6-mi downsample, for renderers/altitude display
        existing = [f['peak_mi'] for f in guide[leg]['features'] if f['kind'] in ('pass', 'summit')]
        added = 0
        for mile, elev in _detect_passes(prof):
            if any(abs(mile - e) < 15 for e in existing):
                continue
            existing.append(mile)
            la, lo = _latlon_at(poly, mile)
            guide[leg]['features'].append({
                'id': f"elev-{leg}-{round(mile)}", 'name': f"Summit (~{elev:,} ft)",
                'kind': 'summit', 'class': 'natural',
                'from_mi': mile, 'to_mi': mile, 'peak_mi': mile,
                'lat': round(la, 5), 'lon': round(lo, 5), 'side': 'both', 'salience': 3,
                'elev_ft': elev, 'blurb': f"high point, ~{elev:,} ft", 'source': src, 'tags': ['summit', 'grade']})
            added += 1
        print(f"  leg {leg}: elevation profile ({len(prof)} pts) + {added} auto-summits")


# ── recompute coverage gaps after enrichment ───────────────────────

def recompute_gaps(guide, min_sal=3, reach=20.0, thresh=40.0):
    for leg, d in guide.items():
        cov = []
        for f in d['features']:
            if f['salience'] >= min_sal:
                cov.append((max(0.0, min(f['from_mi'], f['peak_mi']) - reach),
                            max(f['to_mi'], f['peak_mi']) + reach))
        cov.sort()
        gaps, cur = [], 0.0
        for a, b in cov:
            if a > cur + thresh:
                gaps.append([round(cur), round(a)])
            cur = max(cur, b)
        if d['leg_miles'] - cur > thresh:
            gaps.append([round(cur), round(d['leg_miles'])])
        d['coverage_gaps'] = gaps


ENRICHERS = {'towns': enrich_towns, 'counties': enrich_counties,
             'acs': enrich_acs, 'elevation': enrich_elevation}


def main():
    phases = sys.argv[1:] or ['all']
    if phases == ['all']:
        phases = list(ENRICHERS)
    guide, shapes = _load()
    for ph in phases:
        if ph not in ENRICHERS:
            print(f"  unknown phase: {ph} (have: {', '.join(ENRICHERS)})")
            continue
        print(f"== {ph} ==")
        ENRICHERS[ph](guide, shapes)
    recompute_gaps(guide)
    _save(guide)
    print(f"Wrote {GUIDE}")


if __name__ == '__main__':
    main()
