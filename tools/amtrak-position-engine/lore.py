#!/usr/bin/env python3
"""
F.1 — facts/lore layer. Builds data/route_lore.json (sibling of route_guide.json):
  • lore points discovered along each leg via Wikipedia GeoSearch (noise-filtered,
    with lead summaries), projected onto the milepost axis;
  • a Wikipedia summary for each county span (color for the `profile` command).

Build-time + network (Wikipedia, keyless — descriptive User-Agent per their policy).
Cached in .cache/wiki.json. Runtime reads the JSON (stdlib). Sources: Wikipedia
(CC BY-SA) — keep excerpts short and attributed.

  python3 lore.py            # both lore points + county notes
  python3 lore.py lore       # just the geosearch lore points
  python3 lore.py counties   # just the county summaries
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import position_engine as E   # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'
CACHE = Path(__file__).resolve().parent / '.cache'
LORE = DATA / 'route_lore.json'
UA = {'User-Agent': 'amtrak-route-guide/1.0 (personal trip project; github.com/chaddorsey)'}

GEO_STEP_MI = 8.0        # dense enough to populate every ~10-mi bin
GEO_RADIUS_M = 10000     # Wikipedia gsradius hard max
GEO_LIMIT = 30
BIN_MI = 8.0             # "always something": ~1 lore point per 8-mi cell
# Wikidata P31 types to drop (clutter): building, skyscraper, school, university,
# radio station, TV station, sculpture, road
P31_DENY = {'Q41176', 'Q11303', 'Q3914', 'Q3918', 'Q14350', 'Q1616075', 'Q860861', 'Q34442'}

_CP = None       # cache path, set by main() — enables incremental saves
_FETCHES = 0


def _tick(cache):
    global _FETCHES
    _FETCHES += 1
    if _CP is not None and _FETCHES % 20 == 0:
        _CP.write_text(json.dumps(cache))

# titles that are almost never "interesting place color"
_NOISE = re.compile(
    r'^[KW][A-Z]{2,3}(-(FM|TV|LP|CD|AM|HD\d?|DT))?$'          # radio/TV call signs
    r'|\((AM|FM|TV)\)$|disambiguation|^List of|^Geography of'
    r'|High School|Elementary School|Middle School'
    r'|^(U\.S\.|Interstate|California State|Texas State) (Route|Highway)'
    r'|^[A-Z]{1,3}-\d+$', re.I)

STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts',
    'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana',
    'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico',
    'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
    'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
}


def _cache():
    CACHE.mkdir(exist_ok=True)
    p = CACHE / 'wiki.json'
    return p, (json.loads(p.read_text()) if p.exists() else {})


def _get(url, tries=4):
    import urllib.error
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and t < tries - 1:
                time.sleep(3 * (t + 1))
                continue
            raise


def _geosearch(lat, lon, cache):
    k = f"gs:{lat:.3f},{lon:.3f}"
    if k not in cache:
        url = ("https://en.wikipedia.org/w/api.php?action=query&list=geosearch&format=json"
               f"&gscoord={lat:.4f}%7C{lon:.4f}&gsradius={GEO_RADIUS_M}&gslimit={GEO_LIMIT}")
        try:
            cache[k] = [{'pageid': g['pageid'], 'title': g['title'], 'lat': g['lat'],
                         'lon': g['lon'], 'dist': g['dist']} for g in _get(url)['query']['geosearch']]
        except Exception:
            cache[k] = []
        _tick(cache)
        time.sleep(0.1)
    return cache[k]


def _summary(title, cache):
    k = "sum:" + title
    if k not in cache:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title, safe='')
        try:
            d = _get(url)
            cache[k] = {'extract': d.get('extract', ''), 'type': d.get('type', ''),
                        'url': d.get('content_urls', {}).get('desktop', {}).get('page', '')}
        except Exception:
            cache[k] = {'extract': '', 'type': 'error', 'url': ''}
        _tick(cache)
        time.sleep(0.1)
    return cache[k]


def _qids(pageids, cache):
    """Batch pageid → Wikidata Q-id via pageprops (50/call)."""
    todo = [p for p in pageids if f"pp:{p}" not in cache]
    for i in range(0, len(todo), 50):
        b = todo[i:i + 50]
        url = ("https://en.wikipedia.org/w/api.php?action=query&format=json"
               "&prop=pageprops&ppprop=wikibase_item&pageids=" + "|".join(map(str, b)))
        try:
            for pid, pg in _get(url)['query']['pages'].items():
                cache[f"pp:{pid}"] = pg.get('pageprops', {}).get('wikibase_item')
        except Exception:
            for p in b:
                cache[f"pp:{p}"] = None
        _tick(cache)
        time.sleep(0.1)
    return {p: cache.get(f"pp:{p}") for p in pageids}


def _wd(qids, cache):
    """Batch Q-id → ([P31 type ids], sitelink_count) via wbgetentities (50/call)."""
    todo = [q for q in qids if q and f"wd:{q}" not in cache]
    for i in range(0, len(todo), 50):
        b = todo[i:i + 50]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
               "&props=claims%7Csitelinks&ids=" + "|".join(b))
        try:
            for q, e in _get(url)['entities'].items():
                p31 = [c['mainsnak']['datavalue']['value']['id']
                       for c in e.get('claims', {}).get('P31', [])
                       if c.get('mainsnak', {}).get('datavalue')]
                cache[f"wd:{q}"] = [p31, len(e.get('sitelinks', {}))]
        except Exception:
            for q in b:
                cache[f"wd:{q}"] = [[], 0]
        _tick(cache)
        time.sleep(0.1)
    return {q: cache.get(f"wd:{q}", [[], 0]) for q in qids if q}


def discover_lore(guide, shapes, cache, cp=None):
    """'Always something' selection: geosearch candidates → drop title/type clutter →
    bin to ~BIN_MI cells → keep the most-notable (sitelinks) place per cell."""
    out = {}
    for leg, poly in shapes.items():
        if leg not in guide:
            continue
        legmi = poly[-1][0]
        cand = {}
        mile = 0.0
        while mile <= legmi:
            la, lo = E._milepost_latlon(poly, mile)
            for g in _geosearch(la, lo, cache):
                if g['pageid'] not in cand or g['dist'] < cand[g['pageid']]['dist']:
                    cand[g['pageid']] = g
            mile += GEO_STEP_MI
        cands = []
        for g in cand.values():
            if _NOISE.search(g['title']):
                continue
            m, off, side = E.project_to_leg(poly, g['lat'], g['lon'])
            g.update(mi=m, off=off, side=side)
            cands.append(g)
        qmap = _qids([g['pageid'] for g in cands], cache)
        wd = _wd([q for q in qmap.values() if q], cache)
        bins = {}
        for g in cands:
            q = qmap.get(g['pageid'])
            p31, sl = wd.get(q, [[], 0]) if q else ([], 0)
            if any(t in P31_DENY for t in p31):
                continue
            g['sitelinks'] = sl
            bins.setdefault(int(g['mi'] // BIN_MI), []).append(g)
        points = []
        for b in sorted(bins):
            g = max(bins[b], key=lambda x: (x['sitelinks'], -x['off']))
            s = _summary(g['title'], cache)
            if s['type'] != 'standard' or len(s['extract']) < 80:
                continue
            points.append({'id': f"w{g['pageid']}", 'title': g['title'], 'kind': 'lore',
                           'peak_mi': round(g['mi'], 1), 'lat': round(g['lat'], 5),
                           'lon': round(g['lon'], 5), 'side': g['side'], 'offtrack_mi': g['off'],
                           'summary': s['extract'], 'url': s['url']})
        points.sort(key=lambda x: x['peak_mi'])
        out[leg] = points
        if cp:
            cp.write_text(json.dumps(cache))
        gaps = [points[i + 1]['peak_mi'] - points[i]['peak_mi'] for i in range(len(points) - 1)]
        print(f"  leg {leg}: {len(points)} points | avg gap {legmi / max(len(points), 1):.0f}mi "
              f"| max gap {max(gaps) if gaps else 0:.0f}mi")
    return out


def annotate_counties(guide, cache, cp=None):
    out = {}
    seen = {}
    for leg in guide:
        out[leg] = {}
        if cp:
            cp.write_text(json.dumps(cache))
        for f in guide[leg].get('features', []):
            if f.get('kind') != 'county':
                continue
            geo = f['stats'].get('geo', f['name'])      # "Ford County, KS"
            name, _, abbr = geo.partition(',')
            title = f"{name.strip()}, {STATES.get(abbr.strip(), abbr.strip())}"
            if title not in seen:
                s = _summary(title, cache)
                seen[title] = {'summary': s['extract'], 'url': s['url']} if (
                    s['type'] == 'standard' and s['extract']) else None
            if seen[title]:
                out[leg][f['id']] = {'title': title, **seen[title]}
    n = sum(len(v) for v in out.values())
    print(f"  county notes: {n}")
    return out


# ── GNIS gap-fill: named landforms/places in the empty stretches ───
GNIS_LAYERS = (5, 3, 7)   # Landforms, Populated Places, Other Hydrographic
GNIS_SKIP = {'Well', 'Tank', 'Bar', 'Channel', 'Crossing', 'Census', 'Area', 'Bench'}


def _gnis_near(lat, lon, cache):
    k = f"gn:{lat:.3f},{lon:.3f}"
    if k not in cache:
        feats = []
        for layer in GNIS_LAYERS:
            url = (f"https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer/{layer}/query?"
                   f"geometry={lon:.4f},{lat:.4f}&geometryType=esriGeometryPoint&inSR=4326&outSR=4326"
                   "&distance=10000&units=esriSRUnit_Meter"
                   "&outFields=gaz_name,gaz_featureclass,county_name,state_alpha&returnGeometry=true&f=geojson")
            try:
                for ff in _get(url).get('features', []):
                    p = ff.get('properties', {})
                    coords = ff.get('geometry', {}).get('coordinates') or []
                    if not coords:
                        continue
                    c = coords[len(coords) // 2] if isinstance(coords[0], list) else coords
                    feats.append({'name': p.get('gaz_name'), 'cls': p.get('gaz_featureclass'),
                                  'county': p.get('county_name'), 'state': p.get('state_alpha'),
                                  'lon': c[0], 'lat': c[1]})
            except Exception:
                pass
            time.sleep(0.05)
        cache[k] = feats
        _tick(cache)
    return cache[k]


def gnis_gapfill(guide, shapes, cache, cp=None, gap=20.0):
    lore = json.loads(LORE.read_text()) if LORE.exists() else {}
    for leg, poly in shapes.items():
        if leg not in lore:
            continue
        legmi = poly[-1][0]
        wiki = [p for p in lore[leg].get('lore', []) if not str(p['id']).startswith('g')]
        edges = [0.0] + sorted(p['peak_mi'] for p in wiki) + [legmi]
        adds, used = [], set()
        for i in range(len(edges) - 1):
            a, b = edges[i], edges[i + 1]
            if b - a <= gap:
                continue
            m = a + BIN_MI
            while m < b - 4:
                la, lo = E._milepost_latlon(poly, m)
                best = None
                for ft in _gnis_near(la, lo, cache):
                    if not ft['lat'] or ft['cls'] in GNIS_SKIP:
                        continue
                    mm, off, side = E.project_to_leg(poly, ft['lat'], ft['lon'])
                    if not (a < mm < b):
                        continue
                    if best is None or off < best['off']:
                        best = {'ft': ft, 'off': off, 'mi': mm, 'side': side}
                if best and best['ft']['name'] not in used:
                    ft = best['ft']
                    used.add(ft['name'])
                    cls = (ft['cls'] or 'place').lower()
                    adds.append({'id': f"g{leg}-{round(best['mi'])}", 'title': ft['name'], 'kind': cls,
                                 'peak_mi': round(best['mi'], 1), 'lat': round(ft['lat'], 5),
                                 'lon': round(ft['lon'], 5), 'side': best['side'], 'offtrack_mi': best['off'],
                                 'summary': f"{ft['name']} — a {cls} in {ft['county']} County, {ft['state']}.",
                                 'url': '', 'source': 'gnis'})
                m += BIN_MI
        allpts = sorted(wiki + adds, key=lambda x: x['peak_mi'])
        lore[leg]['lore'] = allpts
        if cp:
            cp.write_text(json.dumps(cache))
        g2 = [allpts[i + 1]['peak_mi'] - allpts[i]['peak_mi'] for i in range(len(allpts) - 1)]
        print(f"  leg {leg}: +{len(adds)} GNIS → {len(allpts)} total | max gap {max(g2) if g2 else 0:.0f}mi")
    LORE.write_text(json.dumps(lore))


def main():
    phases = sys.argv[1:] or ['lore', 'counties']
    guide = json.loads((DATA / 'route_guide.json').read_text())
    shapes = json.loads((DATA / 'leg_shapes.json').read_text())
    cp, cache = _cache()
    global _CP
    _CP = cp
    lore = json.loads(LORE.read_text()) if LORE.exists() else {}
    if 'lore' in phases:
        print("== lore points ==")
        for leg, pts in discover_lore(guide, shapes, cache, cp).items():
            lore.setdefault(leg, {})['lore'] = pts
        cp.write_text(json.dumps(cache))
    if 'counties' in phases:
        print("== county notes ==")
        for leg, notes in annotate_counties(guide, cache, cp).items():
            lore.setdefault(leg, {})['counties'] = notes
        cp.write_text(json.dumps(cache))
    if 'lore' in phases or 'counties' in phases:
        LORE.write_text(json.dumps(lore))
        print(f"Wrote {LORE}")
    if 'gnis' in phases:
        print("== gnis gap-fill ==")
        gnis_gapfill(guide, shapes, cache, cp)
        print(f"Wrote {LORE}")


if __name__ == '__main__':
    main()
