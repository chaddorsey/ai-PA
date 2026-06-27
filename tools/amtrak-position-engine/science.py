#!/usr/bin/env python3
"""
Scientific substrate for the narration layer. Samples earth-science layers along
each leg → data/route_science.json (continuous milepost profiles), the raw material
for the dual-granularity (micro stories + macro gradients) narrator.

Layers (build-time, network, keyless; cached in .cache/science.json):
  geology   — Macrostrat mapped unit: formation, age (Ma), lithology, description
  ecoregion — EPA Level III/IV ecoregion hierarchy (biome)
  fossils   — Paleobiology Database taxa near the track (where present)

  python3 science.py                  # all layers, all legs
  python3 science.py geology 3        # one layer, one leg
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import position_engine as E   # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'
CACHE = Path(__file__).resolve().parent / '.cache'
SCI = DATA / 'route_science.json'
UA = {'User-Agent': 'amtrak-route-guide/1.0 (personal trip project; github.com/chaddorsey)'}

STEP_MI = 10.0          # geology + ecoregion sampling
FOSSIL_STEP_MI = 25.0   # fossils are sparse — coarser
EPA = ("https://gispub.epa.gov/arcgis/rest/services/ORD/USEPA_Ecoregions_Level_III_and_IV"
       "/MapServer/7/query")

_CP = None
_FETCHES = 0


def _tick(cache):
    global _FETCHES
    _FETCHES += 1
    if _CP is not None and _FETCHES % 20 == 0:
        _CP.write_text(json.dumps(cache))


def _get(url, tries=3):
    import urllib.error
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and t < tries - 1:
                time.sleep(2 * (t + 1))
                continue
            raise
        except Exception:
            if t < tries - 1:
                time.sleep(1.5 * (t + 1))
                continue
            raise


def _cache():
    CACHE.mkdir(exist_ok=True)
    p = CACHE / 'science.json'
    return p, (json.loads(p.read_text()) if p.exists() else {})


def _clean_lith(s):
    # "Major:{conglomerate,sandstone,shale}; Minor:{coal}" -> "conglomerate, sandstone, shale, coal"
    out = []
    for part in (s or '').replace('Major:', '').replace('Minor:', '').replace('Incidental:', '').split('}'):
        out += [w.strip() for w in part.replace('{', '').split(',') if w.strip()]
    seen, uniq = set(), []
    for w in out:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return ', '.join(uniq[:5])


def _macrostrat(lat, lon, cache):
    k = f"geo:{lat:.3f},{lon:.3f}"
    if k not in cache:
        try:
            data = _get(f"https://macrostrat.org/api/v2/geologic_units/map?lat={lat:.4f}&lng={lon:.4f}")
            d = (data.get('success', {}).get('data') or [])
            if d:
                u = d[0]
                cache[k] = {'unit': u.get('name'), 'b_age': u.get('b_age'), 't_age': u.get('t_age'),
                            'period': u.get('b_int_name') or u.get('age'),
                            'lith': _clean_lith(u.get('lith', '')),
                            'descrip': (u.get('descrip') or '')[:200]}
            else:
                cache[k] = None
        except Exception:
            cache[k] = None
        _tick(cache)
        time.sleep(0.1)
    return cache[k]


def _ecoregion(lat, lon, cache):
    k = f"eco:{lat:.3f},{lon:.3f}"
    if k not in cache:
        url = (EPA + f"?geometry={lon:.4f},{lat:.4f}&geometryType=esriGeometryPoint&inSR=4326"
               "&spatialRel=esriSpatialRelIntersects"
               "&outFields=US_L4NAME,US_L3NAME,NA_L2NAME,NA_L1NAME&returnGeometry=false&f=json")
        try:
            fs = _get(url).get('features', [])
            if fs:
                a = fs[0]['attributes']
                cache[k] = {'l4': a.get('US_L4NAME'), 'l3': a.get('US_L3NAME'),
                            'l2': (a.get('NA_L2NAME') or '').title(), 'l1': (a.get('NA_L1NAME') or '').title()}
            else:
                cache[k] = None
        except Exception:
            cache[k] = None
        _tick(cache)
        time.sleep(0.1)
    return cache[k]


def _fossils(lat, lon, cache, d=0.3):
    k = f"fos:{lat:.3f},{lon:.3f}"
    if k not in cache:
        url = (f"https://paleobiodb.org/data1.2/occs/list.json?lngmin={lon - d:.3f}&lngmax={lon + d:.3f}"
               f"&latmin={lat - d:.3f}&latmax={lat + d:.3f}&limit=40&show=time")
        try:
            recs = _get(url).get('records', [])
            taxa, seen = [], set()
            for r in recs:
                t = r.get('tna')
                if t and ' ' in t and t not in seen:   # species-level, deduped
                    seen.add(t)
                    taxa.append({'taxon': t, 'age': r.get('oei', ''), 'ma': r.get('eag')})
            cache[k] = taxa[:8]
        except Exception:
            cache[k] = []
        _tick(cache)
        time.sleep(0.1)
    return cache[k]


HUC2_REGIONS = {
    '01': 'New England', '02': 'Mid-Atlantic', '03': 'South Atlantic-Gulf', '04': 'Great Lakes',
    '05': 'Ohio', '06': 'Tennessee', '07': 'Upper Mississippi', '08': 'Lower Mississippi',
    '09': 'Souris-Red-Rainy', '10': 'Missouri', '11': 'Arkansas-White-Red', '12': 'Texas-Gulf',
    '13': 'Rio Grande', '14': 'Upper Colorado', '15': 'Lower Colorado', '16': 'Great Basin',
    '17': 'Pacific Northwest', '18': 'California',
}


def _hydrology(lat, lon, cache):
    k = f"hyd:{lat:.3f},{lon:.3f}"
    if k not in cache:
        url = ("https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/4/query?"
               f"geometry={lon:.4f},{lat:.4f}&geometryType=esriGeometryPoint&inSR=4326"
               "&spatialRel=esriSpatialRelIntersects&outFields=huc8,name&returnGeometry=false&f=json")
        try:
            a = (_get(url).get('features') or [{}])[0].get('attributes', {})
            h = a.get('huc8') or ''
            cache[k] = ({'huc8': h, 'basin': a.get('name'), 'region': h[:2],
                         'region_name': HUC2_REGIONS.get(h[:2])} if h else None)
        except Exception:
            cache[k] = None
        _tick(cache)
        time.sleep(0.1)
    return cache[k]


def sample(layer, leg, poly, cache, step):
    out, mile = [], 0.0
    legmi = poly[-1][0]
    fn = {'geology': _macrostrat, 'ecoregion': _ecoregion,
          'fossils': _fossils, 'hydrology': _hydrology}[layer]
    while mile <= legmi:
        la, lo = E._milepost_latlon(poly, mile)
        v = fn(la, lo, cache)
        if v:
            out.append([round(mile, 1), v])
        mile += step
    return out


def main():
    args = sys.argv[1:]
    valid = ('geology', 'ecoregion', 'fossils', 'hydrology')
    layers = [a for a in args if a in valid] or list(valid)
    only_leg = next((a for a in args if a not in layers), None)
    guide = json.loads((DATA / 'route_guide.json').read_text())
    shapes = json.loads((DATA / 'leg_shapes.json').read_text())
    cp, cache = _cache()
    global _CP
    _CP = cp
    sci = json.loads(SCI.read_text()) if SCI.exists() else {}
    for leg, poly in shapes.items():
        if leg not in guide or (only_leg and leg != only_leg):
            continue
        sci.setdefault(leg, {})
        for layer in layers:
            step = FOSSIL_STEP_MI if layer == 'fossils' else STEP_MI
            prof = sample(layer, leg, poly, cache, step)
            sci[leg][layer] = prof
            cp.write_text(json.dumps(cache))
            SCI.write_text(json.dumps(sci))
            print(f"  leg {leg} {layer}: {len(prof)} samples")
    print(f"Wrote {SCI}")


if __name__ == '__main__':
    main()
