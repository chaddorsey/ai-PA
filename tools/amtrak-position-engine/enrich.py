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


ENRICHERS = {'towns': enrich_towns}


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
