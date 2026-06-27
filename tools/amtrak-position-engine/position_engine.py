#!/usr/bin/env python3
"""
Amtrak Position Query Engine — July 2026 Trainstravaganza.

Answers: "Where will I be on July XX at HH:MM Eastern time?"
Uses atomic historical-vector sampling with time-since-departure normalization.

Runtime deps: none (stdlib only; zoneinfo). Building the bundle needs beautifulsoup4.

Data files expected in ../letta-shared-files/amtrak-data/:
  AM3-full.html  AM2-full.html  AM58-full.html  AM7-full.html
  AM27-full.html  AM11-full.html  AM22-full.html

Cached artifacts in /tmp/:
  amtrak_published_timetables.json  amtrak_station_catalog.json
  amtrak_route_mileposts.json       amtrak_milepost_2.json
"""

import json, re, math, os
from pathlib import Path
from typing import Optional
from datetime import datetime
from calendar import timegm

# Timezone handling: prefer stdlib zoneinfo (Python 3.9+, zero third-party deps);
# fall back to pytz if zoneinfo is unavailable.
try:
    from zoneinfo import ZoneInfo

    def _tz(name):
        return ZoneInfo(name)

    def _localize(naive_dt, name):
        return naive_dt.replace(tzinfo=ZoneInfo(name))
except ImportError:  # pragma: no cover
    import pytz

    def _tz(name):
        return pytz.utc if name == 'UTC' else pytz.timezone(name)

    def _localize(naive_dt, name):
        return pytz.timezone(name).localize(naive_dt)

# ── 1. PARSE ASMAD FULL-HISTORY HTML ──────────────────────────────

ENGINE_DIR = Path(__file__).resolve().parent
DATA_DIR = ENGINE_DIR / 'data'            # committed: pre-parsed runs bundle + geo/schedule JSONs
# Raw ASMAD HTML lives here; used ONLY when (re)building the bundle (`--build`).
SRC_DIR = Path(os.environ.get(
    'AMTRAK_SRC', Path.home() / 'Dropbox' / 'letta-shared-files' / 'amtrak-data'))
ASMAD_FILES = {
    '3': 'AM3-full.html', '2': 'AM2-full.html', '58': 'AM58-full.html',
    '27': 'AM27-full.html', '7': 'AM7-full.html', '11': 'AM11-full.html',
    '22': 'AM22-full.html',
}


def parse_delay(comment: str) -> Optional[int]:
    """Parse ASMAD comment like 'Ar: 1 hr, 23 min late.' into signed minutes."""
    m = re.search(r'Ar:\s*(.*?)(?:\||$)', comment)
    if not m:
        return None
    s = m.group(1).strip()
    if 'On time' in s or 'on time' in s:
        return 0
    hrs = mins = 0
    mh = re.search(r'(\d+)\s*hr', s)
    mm = re.search(r'(\d+)\s*min', s)
    if mh:
        hrs = int(mh.group(1))
    if mm:
        mins = int(mm.group(1))
    return -(hrs * 60 + mins) if 'early' in s else hrs * 60 + mins


def parse_sch_ts(s: str) -> Optional[int]:
    """Parse '06/25/2026 8:12 AM (Th)' into Unix timestamp."""
    m = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d{1,2}:\d{2})\s*(AM|PM)', s)
    if not m:
        return None
    try:
        dt = datetime.strptime(
            f'{m.group(1)} {m.group(2)} {m.group(3)}', '%m/%d/%Y %I:%M %p'
        )
        return int(timegm(dt.timetuple()))
    except ValueError:
        return None


# Supplementary per-station delay histories merged into a train's runs (union of
# stations per origin_date). AM27-delay2 adds ~1867 PSC/PDX runs, the WIH/BNG/VAN
# Gorge intermediates, and 23 runs reporting BOTH Spokane and Pasco — which bridge
# the otherwise non-stop SPK→PSC segment with real end-to-end delays.
DELAY_FILES = {
    '27': 'AM27-delay2.html',
}


def _parse_asmad_file(path) -> dict:
    """Parse one ASMAD history/delay HTML → {origin_date: {station: {sch, delay, act}}}."""
    from bs4 import BeautifulSoup  # lazy: only needed when (re)building the bundle
    html = Path(path).read_text(errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')
    runs_by_date = {}
    current_origin = None
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 10:
            continue
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(['th', 'td'])]
            if not cells or len(cells) < 3:
                continue
            origin_date = cells[0] or current_origin
            if not origin_date or cells[1] == 'Station':
                continue
            current_origin = origin_date
            station = cells[1]
            ts = parse_sch_ts(cells[2])
            delay = parse_delay(cells[4] if len(cells) > 4 else '')
            if ts is None or delay is None:
                continue
            runs_by_date.setdefault(origin_date, {}).setdefault(
                station, {'sch': ts, 'delay': delay, 'act': ts + delay * 60})
        break  # first sizable table only
    return runs_by_date


def _parse_all(src: Path) -> dict:
    """Parse every ASMAD HTML in src → {train: [[origin_date, {station: {...}}], ...]},
    merging supplementary DELAY_FILES (union of stations per origin_date)."""
    runs = {}
    for train, fname in ASMAD_FILES.items():
        rbd = _parse_asmad_file(src / fname)
        sup = DELAY_FILES.get(train)
        if sup and (src / sup).exists():
            for od, stns in _parse_asmad_file(src / sup).items():
                tgt = rbd.setdefault(od, {})
                for st, v in stns.items():
                    tgt.setdefault(st, v)
        runs[train] = [[od, rbd[od]] for od in sorted(rbd.keys()) if len(rbd[od]) >= 2]
    return runs


def load_asmad_runs() -> dict:
    """Load the committed pre-parsed runs bundle (data/asmad_runs.json). Falls back to
    parsing raw HTML from SRC_DIR if the bundle hasn't been built yet."""
    bundle = DATA_DIR / 'asmad_runs.json'
    if bundle.exists():
        return json.loads(bundle.read_text())
    return _parse_all(SRC_DIR)


GEO_JSONS = [
    'amtrak_route_mileposts.json', 'amtrak_milepost_2.json',
    'amtrak_station_catalog.json', 'amtrak_published_timetables.json',
]


def build_bundle(src_dir) -> None:
    """(Re)build the committed data/ bundle from raw ASMAD HTML + geo JSONs in src_dir
    (falls back to /tmp for the JSONs). Run after adding/refreshing ASMAD pulls."""
    src = Path(src_dir)
    DATA_DIR.mkdir(exist_ok=True)
    runs = _parse_all(src)
    (DATA_DIR / 'asmad_runs.json').write_text(json.dumps(runs))
    for name in GEO_JSONS:
        for cand in (src / name, Path('/tmp') / name):
            if cand.exists():
                (DATA_DIR / name).write_text(cand.read_text())
                break
    total = sum(len(v) for v in runs.values())
    print(f"Built bundle in {DATA_DIR}: {total} runs across {len(runs)} trains; "
          f"copied {sum((DATA_DIR/n).exists() for n in GEO_JSONS)}/{len(GEO_JSONS)} geo JSONs")
    try:
        st = load_station_catalog()
        gg = build_station_geo(st, load_mileposts())
        tts = {k: parse_timetable(v) for k, v in TIMETABLE_TEXT.items()}
        scheds = {tt: compute_schedule(tt, dep, tts, gg) for _n, tt, _a, dep, _t in ITINERARY}
        n = build_shapes(src, scheds, build_route_sched())
        print(f"  + built data/leg_shapes.json ({n} legs with on-track geometry)")
    except Exception as e:
        print(f"  ! leg_shapes build skipped ({e}); engine will straight-line between stations")
    try:
        import build_route_guide
        build_route_guide.main()
    except Exception as e:
        print(f"  ! route_guide build skipped ({e}); run build_route_guide.py separately")


# ── 1b. GTFS TRACK GEOMETRY (on-track lat/lon between stations) ────

GTFS_URL = 'https://content.amtrak.com/content/gtfs/GTFS.zip'
ROUTE_NAMES = {
    '3': 'Southwest Chief', '2': 'Sunset Limited', '58': 'City of New Orleans',
    '27': 'Empire Builder', '11': 'Coast Starlight', '422': 'Texas Eagle',
}
MATCH_TOL_MI = 3.0   # max station→shape-vertex distance to trust a match


def _haversine_mi(a, b):
    from math import radians, sin, cos, asin, sqrt
    dlat, dlon = radians(b[0] - a[0]), radians(b[1] - a[1])
    h = sin(dlat / 2) ** 2 + cos(radians(a[0])) * cos(radians(b[0])) * sin(dlon / 2) ** 2
    return 2 * 3958.7613 * asin(min(1.0, sqrt(h)))


def _load_gtfs(src):
    """Return (routes_by_id→name, trips, shapes_by_id→[(lat,lon),...]).
    Uses src/GTFS.zip if present, else downloads the live Amtrak feed."""
    import csv, io, zipfile, urllib.request
    zpath = Path(src) / 'GTFS.zip'
    if zpath.exists():
        raw = zpath.read_bytes()
    else:
        req = urllib.request.Request(GTFS_URL, headers={'User-Agent': 'amtrak-position-engine'})
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
    z = zipfile.ZipFile(io.BytesIO(raw))

    def rows(name):
        with z.open(name) as f:
            return list(csv.DictReader(io.TextIOWrapper(f, 'utf-8-sig')))

    routes = {r['route_id']: r.get('route_long_name', '') for r in rows('routes.txt')}
    trips = rows('trips.txt')
    shapes = {}
    for s in rows('shapes.txt'):
        shapes.setdefault(s['shape_id'], []).append(
            (int(s['shape_pt_sequence']), float(s['shape_pt_lat']), float(s['shape_pt_lon'])))
    for sid in shapes:
        shapes[sid] = [(la, lo) for _seq, la, lo in sorted(shapes[sid])]
    return routes, trips, shapes


def build_shapes(src, all_schedules, route_sched) -> int:
    """Build data/leg_shapes.json: per leg, a dense [[anchor_mile, lat, lon], ...] polyline
    that follows the actual track between stations (vs straight lines). Returns #legs built."""
    routes, trips, shapes = _load_gtfs(src)
    name_to_routeids = {}
    for rid, nm in routes.items():
        name_to_routeids.setdefault(nm, []).append(rid)
    routeid_to_shapeids = {}
    for t in trips:
        routeid_to_shapeids.setdefault(t['route_id'], set()).add(t.get('shape_id'))

    def candidate_shapes(corridor_names):
        ids = set()
        for nm in corridor_names:
            for rid in name_to_routeids.get(nm, []):
                ids |= routeid_to_shapeids.get(rid, set())
        return [(sid, shapes[sid]) for sid in ids if sid in shapes and len(shapes[sid]) > 5]

    def nearest(lat, lon, cands):
        best = (None, None, 9e9)
        for sid, poly in cands:
            for i, v in enumerate(poly):
                d = _haversine_mi((lat, lon), v)
                if d < best[2]:
                    best = (sid, i, d)
        return best

    leg_shapes = {}
    for tt_key, corridor in ROUTE_NAMES.items():
        names = [corridor] + (['Sunset Limited'] if tt_key == '422' else [])
        cands = candidate_shapes(names)
        sched = all_schedules.get(tt_key, [])
        if not cands or len(sched) < 2:
            continue
        frame = build_leg_frame(tt_key, sched, route_sched)
        anchor = next((s['code'] for s in sched if s['code'] in frame), None)
        if not anchor:
            continue
        amile = frame[anchor]['miles']
        stations = sorted(([frame[c]['miles'] - amile, frame[c]['lat'], frame[c]['lon']]
                           for c in frame), key=lambda x: x[0])
        out = []
        for k in range(len(stations) - 1):
            m1, la1, lo1 = stations[k]
            m2, la2, lo2 = stations[k + 1]
            out.append([round(m1, 2), round(la1, 5), round(lo1, 5)])
            s1, s2 = nearest(la1, lo1, cands), nearest(la2, lo2, cands)
            if s1[0] and s1[0] == s2[0] and s1[2] < MATCH_TOL_MI and s2[2] < MATCH_TOL_MI:
                poly = shapes[s1[0]]
                i1, i2 = s1[1], s2[1]
                seg = poly[i1:i2 + 1] if i1 <= i2 else poly[i2:i1 + 1][::-1]
                if len(seg) >= 3:
                    cum = [0.0]
                    for j in range(1, len(seg)):
                        cum.append(cum[-1] + _haversine_mi(seg[j - 1], seg[j]))
                    total = cum[-1] or 1.0
                    for j in range(1, len(seg) - 1):
                        f = cum[j] / total
                        out.append([round(m1 + f * (m2 - m1), 2),
                                    round(seg[j][0], 5), round(seg[j][1], 5)])
        last = stations[-1]
        out.append([round(last[0], 2), round(last[1], 5), round(last[2], 5)])
        leg_shapes[tt_key] = out
    (DATA_DIR / 'leg_shapes.json').write_text(json.dumps(leg_shapes))
    return len(leg_shapes)


def _load_leg_shapes() -> dict:
    p = DATA_DIR / 'leg_shapes.json'
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _milepost_latlon(poly, mile):
    """Interpolate on-track (lat, lon) at an anchor-relative milepost along a leg polyline."""
    if not poly:
        return None
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


def _project_point_seg(qlat, qlon, lat1, lon1, lat2, lon2):
    """Project (qlat,qlon) onto segment 1→2 (equirectangular). Return (t∈[0,1], footlat, footlon)."""
    from math import radians, cos
    kx = cos(radians((lat1 + lat2) / 2.0))
    ax, ay = (lon2 - lon1) * kx, (lat2 - lat1)
    bx, by = (qlon - lon1) * kx, (qlat - lat1)
    denom = ax * ax + ay * ay
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (ax * bx + ay * by) / denom))
    return t, lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)


def project_to_leg(poly, lat, lon):
    """Nearest point on a leg polyline [[mile,lat,lon],...] to (lat,lon).
    Returns (mile, offtrack_mi, side) where side ∈ {left,right,ahead} relative to the
    direction of travel (increasing milepost). Used to key any feature to the leg axis."""
    from math import radians, cos
    best = None  # (dist_mi, mile, side)
    for i in range(len(poly) - 1):
        m1, la1, lo1 = poly[i]
        m2, la2, lo2 = poly[i + 1]
        t, fla, flo = _project_point_seg(lat, lon, la1, lo1, la2, lo2)
        d = _haversine_mi((lat, lon), (fla, flo))
        if best is None or d < best[0]:
            mile = m1 + t * (m2 - m1)
            kx = cos(radians((la1 + la2) / 2.0))
            vx, vy = (lo2 - lo1) * kx, (la2 - la1)          # travel direction
            wx, wy = (lon - flo) * kx, (lat - fla)          # toward the feature
            cross = vx * wy - vy * wx                        # >0 ⇒ feature is to the LEFT
            side = 'ahead' if d < 0.3 else ('left' if cross > 0 else 'right')
            best = (d, mile, side)
    if best is None:
        return None
    return round(best[1], 2), round(best[0], 2), best[2]


# ── 2. LOAD STATION GEOGRAPHY ─────────────────────────────────────

def _data_path(name: str) -> str:
    """Path to a geo/schedule JSON inside the committed data/ bundle (/tmp fallback)."""
    p = DATA_DIR / name
    return str(p if p.exists() else Path('/tmp') / name)


def load_station_catalog() -> dict:
    """Load Transitdocs station catalog (lat/lon/timezone)."""
    with open(_data_path('amtrak_station_catalog.json')) as f:
        catalog = json.load(f)
    return {s['code']: s for s in catalog}


def load_mileposts() -> dict:
    """Load route mileposts from Transitdocs backend."""
    with open(_data_path('amtrak_route_mileposts.json')) as f:
        mp = json.load(f)
    with open(_data_path('amtrak_milepost_2.json')) as f:
        d = json.load(f)
        mp['2'] = {'stations': [{'code': s['code'], 'miles': s.get('miles')} for s in d['stops']]}
    return mp


def build_route_sched() -> dict:
    """{asm_train: {code: {'miles','arr','dep'}}} with tz-correct ABSOLUTE epochs.

    Used to normalize each historical run's offset to
    scheduled-elapsed-from-anchor + measured-delay (the corrected method) —
    fixing the previous bug where offsets were taken relative to each run's
    first ASMAD-reported station and computed with timegm (local-as-UTC)."""
    with open(_data_path('amtrak_route_mileposts.json')) as f:
        mp = json.load(f)
    with open(_data_path('amtrak_milepost_2.json')) as f:
        m2 = json.load(f)
    out = {}
    for t, d in mp.items():
        codes = {}
        for s in d.get('stations', []):
            codes[s['code']] = {
                'miles': s.get('miles'),
                'arr': s.get('sch_arrive_epoch') or s.get('sch_depart_epoch'),
                'dep': s.get('sch_depart_epoch') or s.get('sch_arrive_epoch'),
            }
        out[t] = codes
    codes = {}
    for s in m2.get('stops', []):
        codes[s['code']] = {
            'miles': s.get('miles'),
            'arr': s.get('sched_arrive') or s.get('sched_depart'),
            'dep': s.get('sched_depart') or s.get('sched_arrive'),
        }
    out['2'] = codes
    return out


def build_station_geo(station_lookup, mileposts_raw):
    """Return a lookup function: get_station_geo(train_num, code) → {lat, lon, miles, city, state}."""

    def get_geo(tt_key: str, code: str) -> dict:
        for tkey in [tt_key, '7', '3', '22']:
            mp = mileposts_raw.get(tkey, {})
            for s in mp.get('stations', []):
                if s['code'] == code:
                    si = station_lookup.get(code, {})
                    return {
                        'code': code,
                        'miles': s.get('miles'),
                        'lat': si.get('latitude'),
                        'lon': si.get('longitude'),
                        'city': si.get('city', ''),
                        'state': si.get('state', ''),
                    }
        si = station_lookup.get(code, {})
        return {
            'code': code, 'miles': None,
            'lat': si.get('latitude'), 'lon': si.get('longitude'),
            'city': si.get('city', ''), 'state': si.get('state', ''),
        }

    return get_geo


# ── 3. PARSE PUBLISHED TIMETABLES ─────────────────────────────────

def parse_time_str(time_str: str, tz_str: str, dep_date_str: str) -> int:
    """Convert '1:30p' in timezone to UTC unix timestamp on departure date."""
    ts = time_str.strip().lower()
    if ts.endswith('p'):
        ts = ts[:-1] + ' PM'
    elif ts.endswith('a'):
        ts = ts[:-1] + ' AM'
    dt = datetime.strptime(f'{dep_date_str} {ts}', '%Y-%m-%d %I:%M %p')
    dt = _localize(dt, tz_str)
    return int(dt.timestamp())


def compute_schedule(tt_key: str, dep_date_str: str, timetables: dict, get_geo) -> list:
    """Convert published timetable to UTC timestamps anchored to departure date."""
    tt = timetables.get(tt_key, [])
    if not tt:
        return []
    dep_station = tt[0]
    dep_utc = parse_time_str(dep_station['time'], dep_station['tz'], dep_date_str)
    schedule = []
    prev = dep_utc
    for s in tt:
        ts = parse_time_str(s['time'], s['tz'], dep_date_str)
        # Enforce monotonic UTC along the route (handles multi-day legs that
        # cross more than one midnight — a single ">dep_utc" check mis-dates
        # late stations to the wrong day).
        while ts < prev:
            ts += 86400
        prev = ts
        geo = get_geo(tt_key, s['code'])
        schedule.append({
            'code': s['code'], 'utc': ts,
            'miles': geo.get('miles'),
            'lat': geo.get('lat'), 'lon': geo.get('lon'),
            'city': geo.get('city'), 'state': geo.get('state'),
            'tz': s['tz'],
        })
    return schedule


# ── 4. PUBLISHED TIMETABLE TEXT (pasted by Chad 2026-06-25) ───────

TIMETABLE_TEXT = {
    '3': """Departs Chicago, IL (CHI) - 1:30p
2:00p | 2:03p - Naperville, IL (NPV)
2:53p | 2:54p - Mendota, IL (MDT)
3:14p | 3:16p - Princeton, IL (PCT)
4:06p | 4:09p - Galesburg, IL (GBB)
5:05p | 5:10p - Fort Madison, IA (FMD)
6:22p | 6:24p - La Plata, MO (LAP)
8:53p | 9:37p - Kansas City, MO (KCY)
10:45p | 10:47p - Lawrence, KS (LRC)
11:21p | 11:24p - Topeka, KS (TOP)
1:36a | 1:40a - Newton, KS (NEW)
2:13a | 2:15a - Hutchinson, KS (HUT)
4:08a | 4:14a - Dodge City, KS (DDG)
5:03a | 5:05a - Garden City, KS (GCK)
5:31a | 5:33a - Lamar, CO (LMR)
6:35a | 6:50a - La Junta, CO (LAJ)
8:10a | 8:10a - Trinidad, CO (TRI)
9:07a | 9:12a - Raton, NM (RAT)
10:57a | 10:57a - Las Vegas, NM (LSV)
12:49p | 12:53p - Lamy, NM (LMY)
2:24p | 3:14p - Albuquerque, NM (ABQ)
5:54p | 5:54p - Gallup, NM (GLP)
6:41p | 6:43p - Winslow, AZ (WLO)
7:49p | 7:55p - Flagstaff, AZ (FLG)
10:42p | 10:49p - Kingman, AZ (KNG)
11:49p | 11:54p - Needles, CA (NDL)
3:18a | 3:23a - Barstow, CA (BAR)
4:00a | 4:02a - Victorville, CA (VRV)
5:26a | 5:26a - San Bernardino, CA (SNB)
5:50a | 5:52a - Riverside, CA (RIV)
7:24a | 7:24a - Fullerton, CA (FUL)
Arrives Los Angeles, CA (LAX) - 8:12a""",
    '2': """Departs Los Angeles, CA (LAX) - 10:00p
10:41p | 10:41p - Pomona, CA (POS)
10:54p | 10:54p - Ontario, CA (ONA)
12:36a | 12:36a - Palm Springs, CA (PSN)
2:47a | 2:47a - Yuma, AZ (YUM)
5:35a | 5:55a - Maricopa, AZ (MRC)
7:38a | 7:53a - Tucson, AZ (TUS)
8:53a | 8:53a - Benson, AZ (BEN)
11:53a | 11:53a - Lordsburg, NM (LDB)
12:48p | 12:48p - Deming, NM (DEM)
3:00p | 3:45p - El Paso, TX (ELP)
8:45p | 8:55p - Alpine, TX (ALP)
10:46p | 10:46p - Sanderson, TX (SND)
1:12a | 1:12a - Del Rio, TX (DRT)
5:00a | 6:25a - San Antonio, TX (SAS)
11:10a | 12:10p - Houston, TX (HOS)
1:53p | 2:05p - Beaumont, TX (BMT)
3:29p | 3:29p - Lake Charles, LA (LCH)
5:12p | 5:15p - Lafayette, LA (LFT)
5:41p | 5:41p - New Iberia, LA (NIB)
7:03p | 7:03p - Schriever, LA (SCH)
Arrives New Orleans, LA (NOL) - 9:40p""",
    '58': """Departs New Orleans, LA (NOL) - 3:45p
4:51p | 4:54p - Hammond, LA (HMD)
5:44p | 5:46p - McComb, MS (MCB)
6:08p | 6:10p - Brookhaven, MS (BRH)
6:29p | 6:31p - Hazlehurst, MS (HAZ)
7:24p | 7:40p - Jackson, MS (JAN)
8:36p | 8:38p - Yazoo City, MS (YAZ)
9:33p | 9:38p - Greenwood, MS (GWD)
10:33p | 10:35p - Marks, MS (MKS)
12:25a | 12:45a - Memphis, TN (MEM)
2:26a | 2:28a - Newbern-Dyersburg, TN (NBN)
3:08a | 3:10a - Fulton, KY (FTN)
5:13a | 5:18a - Carbondale, IL (CDL)
6:11a | 6:13a - Centralia, IL (CEN)
7:09a | 7:10a - Effingham, IL (EFG)
7:36a | 7:38a - Mattoon, IL (MAT)
8:25a | 8:30a - Champaign-Urbana, IL (CHM)
9:31a | 9:33a - Kankakee, IL (KKI)
10:08a | 10:11a - Homewood, IL (HMW)
Arrives Chicago, IL (CHI) - 11:15a""",
    '27': """Departs Chicago, IL (CHI) - 3:05p
3:29p | 3:29p - Glenview, IL (GLN)
4:35p | 4:45p - Milwaukee-Downtown, WI (MKE)
5:55p | 5:55p - Columbus, WI (CBS)
6:24p | 6:24p - Portage, WI (POG)
6:42p | 6:42p - Wisconsin Dells, WI (WDL)
7:20p | 7:20p - Tomah, WI (TOH)
8:04p | 8:04p - La Crosse, WI (LSE)
8:34p | 8:40p - Winona, MN (WIN)
9:42p | 9:42p - Red Wing, MN (RDW)
10:56p | 11:13p - St. Paul-Minneapolis, MN (MSP)
1:09a | 1:09a - St. Cloud, MN (SCD)
2:10a | 2:10a - Staples, MN (SPL)
3:06a | 3:06a - Detroit Lakes, MN (DLK)
4:13a | 4:13a - Fargo, ND (FAR)
5:34a | 5:34a - Grand Forks, ND (GFK)
6:59a | 6:59a - Devils Lake, ND (DVL)
7:53a | 7:53a - Rugby, ND (RUG)
9:06a | 9:51a - Minot, ND (MOT)
10:46a | 10:46a - Stanley, ND (STN)
11:59a | 11:59a - Williston, ND (WTN)
12:34p | 12:34p - Wolf Point, MT (WPT)
1:20p | 1:20p - Glasgow, MT (GGW)
2:20p | 2:20p - Malta, MT (MAL)
3:54p | 4:15p - Havre, MT (HAV)
6:13p | 6:21p - Shelby, MT (SBY)
6:51p | 6:51p - Cut Bank, MT (CUT)
7:48p | 7:48p - East Glacier Park, MT (GPK)
8:44p | 8:44p - Essex, MT (ESM)
9:27p | 9:27p - West Glacier, MT (WGL)
10:06p | 10:21p - Whitefish, MT (WFH)
12:05a | 12:05a - Libby, MT (LIB)
12:55a | 12:55a - Sandpoint, ID (SPT)
2:44a | 3:49a - Spokane, WA (SPK)
6:40a | 6:40a - Pasco, WA (PSC)
8:35a | 8:35a - Wishram, WA (WIH)
9:10a | 9:10a - Bingen-White Salmon, WA (BNG)
10:35a | 10:35a - Vancouver, WA (VAN)
Arrives Portland, OR (PDX) - 11:17a""",
    '11': """Departs Portland, OR (PDX) - 2:22p
3:36p | 3:39p - Salem, OR (SLM)
4:11p | 4:14p - Albany, OR (ALY)
5:08p | 5:15p - Eugene, OR (EUG)
8:13p | 8:13p - Chemult, OR (CMO)
9:58p | 10:08p - Klamath Falls, OR (KFS)
12:45a | 12:45a - Dunsmuir, CA (DUN)
2:31a | 2:31a - Redding, CA (RDD)
4:12a | 4:12a - Chico, CA (CIC)
6:28a | 6:48a - Sacramento, CA (SAC)
7:05a | 7:05a - Davis, CA (DAV)
7:54a | 7:54a - Martinez, CA (MTZ)
8:29a | 8:39a - Emeryville, CA (EMY)
8:54a | 9:09a - Oakland, CA (OKJ)
10:14a | 10:26a - San Jose, CA (SJC)
12:06p | 12:06p - Salinas, CA (SNS)
1:57p | 1:57p - Paso Robles, CA (PRB)
3:24p | 3:37p - San Luis Obispo, CA (SLO)
6:12p | 6:19p - Santa Barbara, CA (SBA)
7:20p | 7:20p - Oxnard, CA (OXN)
8:02p | 8:02p - Simi Valley, CA (SIM)
8:36p | 8:36p - Van Nuys, CA (VNC)
8:44p | 8:44p - Burbank, CA (BUR)
Arrives Los Angeles, CA (LAX) - 9:11p""",
    '422': """Departs Los Angeles, CA (LAX) - 10:00p
10:41p | 10:41p - Pomona, CA (POS)
10:54p | 10:54p - Ontario, CA (ONA)
12:36a | 12:36a - Palm Springs, CA (PSN)
2:47a | 2:47a - Yuma, AZ (YUM)
5:35a | 5:55a - Maricopa, AZ (MRC)
7:38a | 7:53a - Tucson, AZ (TUS)
8:53a | 8:53a - Benson, AZ (BEN)
11:53a | 11:53a - Lordsburg, NM (LDB)
12:48p | 12:48p - Deming, NM (DEM)
3:00p | 3:45p - El Paso, TX (ELP)
8:45p | 8:55p - Alpine, TX (ALP)
10:46p | 10:46p - Sanderson, TX (SND)
1:12a | 1:12a - Del Rio, TX (DRT)
5:00a | 6:48a - San Antonio, TX (SAS)
8:22a | 8:22a - San Marcos, TX (SMC)
9:16a | 9:26a - Austin, TX (AUS)
10:17a | 10:17a - Taylor, TX (TAY)
11:20a | 11:20a - Temple, TX (TPL)
11:47a | 11:47a - McGregor, TX (MCG)
12:59p | 12:59p - Cleburne, TX (CBR)
1:57p | 2:23p - Fort Worth, TX (FTW)
3:23p | 3:43p - Dallas, TX (DAL)
5:18p | 5:18p - Mineola, TX (MIN)
6:18p | 6:18p - Longview, TX (LVW)
7:04p | 7:29p - Marshall, TX (MHL)
8:36p | 8:41p - Texarkana, AR (TXA)
9:16p | 9:16p - Hope, AR (HOP)
10:02p | 10:02p - Arkadelphia, AR (ARK)
10:26p | 10:26p - Malvern, AR (MVN)
11:32p | 11:44p - Little Rock, AR (LRK)
1:46a | 1:46a - Walnut Ridge, AR (WNR)
2:49a | 2:49a - Poplar Bluff, MO (PBF)
4:24a | 4:24a - Arcadia, MO (ACD)
7:30a | 8:10a - St. Louis, MO (STL)
8:56a | 8:56a - Alton, IL (ALN)
9:23a | 9:23a - Carlinville, IL (CRV)
10:03a | 10:03a - Springfield, IL (SPI)
10:29a | 10:29a - Lincoln, IL (LCN)
11:08a | 11:08a - Bloomington-Normal, IL (BNL)
11:38a | 11:38a - Pontiac, IL (PON)
12:53p | 12:53p - Joliet, IL (JOL)
Arrives Chicago, IL (CHI) - 1:49p""",
}


def parse_timetable(text: str) -> list:
    """Parse published timetable text into list of {code, time, tz, kind, name}."""
    stations = []
    tz_map = {
        'IL': 'America/Chicago', 'MO': 'America/Chicago', 'KS': 'America/Chicago',
        'WI': 'America/Chicago', 'MN': 'America/Chicago', 'ND': 'America/Chicago',
        'IA': 'America/Chicago', 'AR': 'America/Chicago', 'TN': 'America/Chicago',
        'KY': 'America/Chicago', 'MS': 'America/Chicago', 'LA': 'America/Chicago',
        'CO': 'America/Denver', 'NM': 'America/Denver', 'MT': 'America/Denver',
        'AZ': 'America/Phoenix',
        'CA': 'America/Los_Angeles', 'OR': 'America/Los_Angeles',
        'WA': 'America/Los_Angeles', 'TX': 'America/Chicago',
        'ID': 'America/Los_Angeles',  # Sandpoint, northern ID = Pacific (missing → broke EB SPT→PDX)
    }
    overrides = {
        'ELP': 'America/Denver', 'SPK': 'America/Los_Angeles',
    }

    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        dep_m = re.match(r'Departs\s+(.+?)\s+\(([A-Z]{2,4})\)\s*-\s*(\d{1,2}:\d{2}[ap])', line, re.I)
        if dep_m:
            name, code, time_str = dep_m.groups()
            state = name.split(',')[-1].strip() if ',' in name else ''
            tz_str = overrides.get(code, tz_map.get(state, 'America/Chicago'))
            stations.append({'code': code, 'time': time_str, 'tz': tz_str, 'kind': 'departure', 'name': name})
            continue
        arr_m = re.match(r'Arrives\s+(.+?)\s+\(([A-Z]{2,4})\)\s*-\s*(\d{1,2}:\d{2}[ap])', line, re.I)
        if arr_m:
            name, code, time_str = arr_m.groups()
            state = name.split(',')[-1].strip() if ',' in name else ''
            tz_str = overrides.get(code, tz_map.get(state, 'America/Chicago'))
            stations.append({'code': code, 'time': time_str, 'tz': tz_str, 'kind': 'arrival', 'name': name})
            continue
        int_m = re.match(r'(\d{1,2}:\d{2}[ap])\s*\|\s*(\d{1,2}:\d{2}[ap])\s*-\s*(.+?)\s+\(([A-Z]{2,4})\)', line, re.I)
        if int_m:
            arr_time, _dep_time, name, code = int_m.groups()
            state = name.split(',')[-1].strip() if ',' in name else ''
            tz_str = overrides.get(code, tz_map.get(state, 'America/Chicago'))
            stations.append({'code': code, 'time': arr_time, 'tz': tz_str, 'kind': 'intermediate', 'name': name})
    return stations


# ── 5. ITINERARY ───────────────────────────────────────────────────

ITINERARY = [
    ('SW Chief 3', '3', '3', '2026-07-06', '1:30p'),
    ('Sunset Ltd 2', '2', '2', '2026-07-08', '10:00p'),
    ('CONO 58', '58', '58', '2026-07-11', '3:45p'),
    ('Empire Builder', '27', '7', '2026-07-12', '3:05p'),
    ('Coast Starlight', '11', '11', '2026-07-16', '2:22p'),
    ('TX Eagle 422', '422', '22', '2026-07-19', '10:00p'),
]


# ── 5b. MULTI-SOURCE LEG FRAMES ───────────────────────────────────
# Each itinerary leg is covered by one or more ASMAD trains, chained at a join
# station.  Empire Builder: train 7 (CHI→SPK) then train 27 (SPK→PDX).  Texas
# Eagle leg: the 422 through-cars ride Sunset Limited train 2 (LAX→SAS), then
# become train 22 (SAS→CHI).  Keyed by timetable key.
LEG_SOURCES = {
    '3':   [('3', 'CHI', 'LAX')],
    '2':   [('2', 'LAX', 'NOL')],
    '58':  [('58', 'NOL', 'CHI')],
    '27':  [('7', 'CHI', 'SPK'), ('27', 'SPK', 'PDX')],
    '11':  [('11', 'PDX', 'LAX')],
    '422': [('2', 'LAX', 'SAS'), ('22', 'SAS', 'CHI')],
}


def build_leg_frame(tt_key: str, sched: list, route_sched: dict) -> dict:
    """{code: {'utc','miles','lat','lon','city','state'}} for stations on OUR route.

    Schedule timestamps come from our timetable (tz-correct, monotonic).  Mileposts
    are chained across segments so the leg is one continuous milepost axis from the
    boarding point, even when two trains cover it."""
    by_code = {s['code']: s for s in sched}
    codes = [s['code'] for s in sched]
    frame = {}
    cum = 0.0  # leg-miles at the current segment's start station
    for train, start, end in LEG_SOURCES.get(tt_key, []):
        rs = route_sched.get(train, {})
        if start not in rs or rs[start].get('miles') is None:
            continue
        base_route_mi = rs[start]['miles']
        base_leg_mi = cum
        try:
            i0, i1 = codes.index(start), codes.index(end)
        except ValueError:
            continue
        for code in codes[i0:i1 + 1]:
            r = rs.get(code)
            s = by_code.get(code)
            if not r or r.get('miles') is None or not s or s.get('lat') is None:
                continue
            frame[code] = {
                'utc': s['utc'],
                'miles': base_leg_mi + (r['miles'] - base_route_mi),
                'lat': s['lat'], 'lon': s['lon'],
                'city': s.get('city', ''), 'state': s.get('state', ''),
            }
        if end in rs and rs[end].get('miles') is not None:
            cum = base_leg_mi + (rs[end]['miles'] - base_route_mi)
    return frame


# ── 6. QUERY ENGINE ────────────────────────────────────────────────

def _interp_y(points, x):
    """points = sorted [(x, y)]; linear-interpolate y at x, clamped to the endpoints."""
    if not points:
        return None
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        if x1 <= x <= x2:
            f = (x - x1) / (x2 - x1) if x2 != x1 else 0.0
            return y1 + f * (y2 - y1)
    return points[-1][1]


def _pos_at(pts, off):
    """pts = sorted [(off, miles, lat, lon)]; return (miles, lat, lon) at off, or None
    if off isn't bracketed by the run's reported span."""
    for i in range(len(pts) - 1):
        o1, m1, la1, lo1 = pts[i]
        o2, m2, la2, lo2 = pts[i + 1]
        if o1 <= off <= o2:
            f = (off - o1) / (o2 - o1) if o2 != o1 else 0.5
            f = max(0.0, min(1.0, f))
            return (m1 + f * (m2 - m1), la1 + f * (la2 - la1), lo1 + f * (lo2 - lo1))
    return None


def _off_at_mile(pts, mile):
    """pts = sorted [(off, miles, ...)]; return the offset at which the run reaches `mile`."""
    for i in range(len(pts) - 1):
        m1, m2 = pts[i][1], pts[i + 1][1]
        if (m1 <= mile <= m2) or (m2 <= mile <= m1):
            o1, o2 = pts[i][0], pts[i + 1][0]
            if m2 == m1:
                return o1
            return o1 + (mile - m1) / (m2 - m1) * (o2 - o1)
    return None


def _weighted_pick(items, p, key='miles'):
    """Return the item at weighted percentile p, ranking by item[key], weighting by item['w']."""
    s = sorted(items, key=lambda x: x[key])
    tot = sum(x['w'] for x in s)
    if tot <= 0:
        return s[min(len(s) - 1, max(0, int(len(s) * p)))]
    cum, target = 0.0, p * tot
    for x in s:
        cum += x['w']
        if cum >= target:
            return x
    return s[-1]


def _apply_weights(items, D0, sigma_init=25.0, ess_min=30, sigma_cap=240.0):
    """Set item['w'] from a Gaussian kernel on (item['dhist'] − D0); adaptively widen
    sigma until the effective sample size ≥ ess_min. D0 None → uniform weights.
    Returns (sigma_used, n_eff)."""
    if D0 is None:
        for x in items:
            x['w'] = 1.0
        return None, len(items)
    sigma = sigma_init
    while True:
        for x in items:
            dh = x.get('dhist')
            x['w'] = math.exp(-((dh - D0) ** 2) / (2 * sigma * sigma)) if dh is not None else 0.0
        sw = sum(x['w'] for x in items)
        sw2 = sum(x['w'] * x['w'] for x in items)
        ess = (sw * sw / sw2) if sw2 > 0 else 0.0
        if ess >= ess_min or sigma >= sigma_cap:
            return round(sigma, 1), round(ess, 1)
        sigma = min(sigma * 1.5, sigma_cap)


def _build_trajectories(tt_key, sched, all_runs, route_sched):
    """Return (anchor, anchor_utc, anchor_mi, frame, trajs) for a leg, or None.
    trajs: list of {'pts': sorted[(off,miles,lat,lon)], 'dprof': sorted[(miles,delay_min)]}."""
    frame = build_leg_frame(tt_key, sched, route_sched)
    if not frame:
        return None
    anchor = None
    for s in sched:
        if s['code'] in frame:
            anchor, anchor_utc, anchor_mi = s['code'], frame[s['code']]['utc'], frame[s['code']]['miles']
            break
    if anchor is None:
        return None
    src_trains = [seg[0] for seg in LEG_SOURCES.get(tt_key, [])]
    trajs = []
    for ti, train in enumerate(src_trains):
        for _origin_date, run in all_runs.get(train, []):
            pts, dprof = [], []
            for code, d in run.items():
                fr = frame.get(code)
                if not fr:
                    continue
                mi = fr['miles'] - anchor_mi
                pts.append(((fr['utc'] - anchor_utc) / 3600.0 + d['delay'] / 60.0, mi, fr['lat'], fr['lon']))
                dprof.append((mi, d['delay']))
            if pts and ti == 0:  # origin (mile-0, on-time) anchor — first-segment train only
                a = frame[anchor]
                pts.append((0.0, 0.0, a['lat'], a['lon']))
                dprof.append((0.0, 0.0))
            if len(pts) >= 2:
                pts.sort()
                dprof.sort()
                trajs.append({'pts': pts, 'dprof': dprof})
    return anchor, anchor_utc, anchor_mi, frame, trajs


def _resolve_M0(observed, frame, anchor_mi, leg_shapes, tt_key):
    """Anchor-relative milepost of the observation, from a station code, a mile, or lat/lon."""
    if observed is None:
        return None
    if 'mile' in observed:
        return observed['mile']
    if 'station' in observed:
        fr = frame.get(observed['station'])
        return (fr['miles'] - anchor_mi) if fr else None
    if 'latlon' in observed and leg_shapes and tt_key in leg_shapes:
        la, lo = observed['latlon']
        best = (None, 9e9)
        for m, plat, plon in leg_shapes[tt_key]:
            d = (plat - la) ** 2 + (plon - lo) ** 2
            if d < best[1]:
                best = (m, d)
        return best[0]
    return None


def query_position(
    query_date_str: str,
    query_time_str: str,
    all_runs: dict,
    all_schedules: dict,
    route_sched: dict,
    station_lookup: dict,
    leg_shapes: Optional[dict] = None,
    observed: Optional[dict] = None,
    sigma: float = 25.0,
) -> Optional[dict]:
    """Probable position (p10/p50/p90) at a date/time (ET).

    Offsets = scheduled-elapsed-from-anchor (our timetable) + measured delay, on one
    tz-correct clock; legs pool all their source trains through a chained-milepost frame.

    If `observed` is given ({'delay': min, and one of 'station'/'mile'/'latlon'}), each
    historical run is weighted by a Gaussian kernel on how close its delay at the observed
    milepost was to ours (CONDITIONED forecasting) — tightening the window and capturing
    recovery dynamics. With observed=None, weights are uniform → identical to the
    unconditioned engine."""
    qdt = datetime.strptime(f'{query_date_str} {query_time_str}', '%Y-%m-%d %I:%M %p')
    q_utc = int(_localize(qdt, 'US/Eastern').timestamp())

    for name, tt_key, _asm_train, dep_date_str, _dep_time_str in ITINERARY:
        sched = all_schedules.get(tt_key, [])
        if len(sched) < 2:
            continue
        our_dep_utc, our_last_utc = sched[0]['utc'], sched[-1]['utc']
        if q_utc < our_dep_utc - 7200 or q_utc > our_last_utc + 21600:
            continue
        built = _build_trajectories(tt_key, sched, all_runs, route_sched)
        if not built:
            continue
        anchor, anchor_utc, anchor_mi, frame, trajs = built
        our_offset_h = (q_utc - anchor_utc) / 3600.0

        obs_M0 = _resolve_M0(observed, frame, anchor_mi, leg_shapes, tt_key)
        obs_D0 = observed.get('delay') if (observed and obs_M0 is not None) else None

        positions = []
        for t in trajs:
            pr = _pos_at(t['pts'], our_offset_h)
            if pr is not None:
                dh = _interp_y(t['dprof'], obs_M0) if obs_M0 is not None else None
                positions.append({'miles': pr[0], 'lat': pr[1], 'lon': pr[2], 'dhist': dh})

        if len(positions) >= 5:
            sigma_used, n_eff = _apply_weights(positions, obs_D0, sigma)
            p10 = _weighted_pick(positions, 0.1)
            p50 = _weighted_pick(positions, 0.5)
            p90 = _weighted_pick(positions, 0.9)

            if leg_shapes and tt_key in leg_shapes:
                poly = leg_shapes[tt_key]
                for p in (p10, p50, p90):
                    ll = _milepost_latlon(poly, p['miles'])
                    if ll:
                        p['lat'], p['lon'] = ll

            route_stations = sorted(
                ((info['miles'] - anchor_mi, code) for code, info in frame.items()),
                key=lambda x: x[0])
            before = after = None
            for rel_mi, code in route_stations:
                if rel_mi <= p50['miles']:
                    before = code
                elif after is None:
                    after = code

            def _nm(code):
                if not code:
                    return '?'
                si = station_lookup.get(code, {})
                return f"{code} ({si.get('city', '')}, {si.get('state', '')})"

            return {
                'train': name,
                'hours_into_trip': round((q_utc - our_dep_utc) / 3600.0, 1),
                'anchor': anchor,
                'n_runs': len(positions),
                'conditioned': obs_D0 is not None,
                'obs_delay_min': obs_D0,
                'sigma_used': sigma_used,
                'n_eff': n_eff,
                'p10_lat': round(p10['lat'], 3), 'p10_lon': round(p10['lon'], 3),
                'p10_mi': round(p10['miles'], 1),
                'p50_lat': round(p50['lat'], 3), 'p50_lon': round(p50['lon'], 3),
                'p50_mi': round(p50['miles'], 1),
                'p90_lat': round(p90['lat'], 3), 'p90_lon': round(p90['lon'], 3),
                'p90_mi': round(p90['miles'], 1),
                'before': _nm(before),
                'after': _nm(after),
            }
    return None


def eta_to(ctx, station_code, leg_key=None, ref_utc=None, observed=None, sigma=25.0):
    """Weighted p10/p50/p90 clock-time ETA to station_code. Leg = `leg_key` if given
    (planning), else the leg active at ref_utc (default now). Conditioned on `observed`."""
    if ref_utc is None:
        ref_utc = int(datetime.now(_tz('US/Eastern')).timestamp())
    for name, tt_key, _a, _dd, _t in ITINERARY:
        sched = ctx['all_schedules'].get(tt_key, [])
        if len(sched) < 2:
            continue
        if leg_key is not None:
            if tt_key != leg_key:
                continue
        elif not (sched[0]['utc'] - 7200 <= ref_utc <= sched[-1]['utc'] + 21600):
            continue
        built = _build_trajectories(tt_key, sched, ctx['all_runs'], ctx['route_sched'])
        if not built:
            continue
        anchor, anchor_utc, anchor_mi, frame, trajs = built
        if station_code not in frame:
            return {'error': f"{station_code} is not on the current leg ({name})"}
        target_mi = frame[station_code]['miles'] - anchor_mi
        obs_M0 = _resolve_M0(observed, frame, anchor_mi, ctx.get('leg_shapes'), tt_key)
        obs_D0 = observed.get('delay') if (observed and obs_M0 is not None) else None
        rows = []
        for t in trajs:
            off = _off_at_mile(t['pts'], target_mi)
            if off is not None and off >= 0:
                dh = _interp_y(t['dprof'], obs_M0) if obs_M0 is not None else None
                rows.append({'off': off, 'dhist': dh})
        if len(rows) >= 5:
            sigma_used, n_eff = _apply_weights(rows, obs_D0, sigma)

            def clock(p):
                off = _weighted_pick(rows, p, key='off')['off']
                return datetime.fromtimestamp(anchor_utc + off * 3600, _tz('US/Eastern'))

            return {'train': name, 'station': station_code,
                    'conditioned': obs_D0 is not None, 'obs_delay_min': obs_D0, 'n_eff': n_eff,
                    'p10': clock(0.1), 'p50': clock(0.5), 'p90': clock(0.9)}
    return None


def eta_to_mile(ctx, leg_key, target_mi, ref_utc=None, observed=None, sigma=25.0):
    """Weighted P10/P50/P90 clock-time ETA to an anchor-relative milepost on leg_key.
    Same machinery as eta_to but targets a milepost (so route-guide features ETA precisely)."""
    for _name, tt_key, _a, _dd, _t in ITINERARY:
        if tt_key != leg_key:
            continue
        sched = ctx['all_schedules'].get(tt_key, [])
        if len(sched) < 2:
            return None
        built = _build_trajectories(tt_key, sched, ctx['all_runs'], ctx['route_sched'])
        if not built:
            return None
        anchor, anchor_utc, anchor_mi, frame, trajs = built
        obs_M0 = _resolve_M0(observed, frame, anchor_mi, ctx.get('leg_shapes'), tt_key)
        obs_D0 = observed.get('delay') if (observed and obs_M0 is not None) else None
        rows = []
        for t in trajs:
            off = _off_at_mile(t['pts'], target_mi)
            if off is not None and off >= 0:
                dh = _interp_y(t['dprof'], obs_M0) if obs_M0 is not None else None
                rows.append({'off': off, 'dhist': dh})
        if len(rows) < 5:
            return None
        sigma_used, n_eff = _apply_weights(rows, obs_D0, sigma)

        def clock(p):
            return datetime.fromtimestamp(anchor_utc + _weighted_pick(rows, p, key='off')['off'] * 3600,
                                          _tz('US/Eastern'))
        return {'p10': clock(0.1), 'p50': clock(0.5), 'p90': clock(0.9),
                'conditioned': obs_D0 is not None, 'n_eff': n_eff}
    return None


# ── 7. MAIN ────────────────────────────────────────────────────────

# ── 7. CLI ──────────────────────────────────────────────────────────

# Operating train numbers per leg (timetable key), used for the live feed.
LIVE_TRAINS = {
    '3': ['3'], '2': ['2'], '58': ['58'],
    '27': ['27', '7'], '11': ['11'], '422': ['422', '22'],
}

TESTS = [
    ('2026-07-06', '5:00 PM', 'SW Chief Day 1'),
    ('2026-07-07', '8:00 AM', 'SW Chief Day 2'),
    ('2026-07-08', '5:00 AM', 'SW Chief approaching LA'),
    ('2026-07-09', '3:00 PM', 'Sunset Ltd AZ/NM'),
    ('2026-07-10', '6:00 PM', 'Sunset Ltd approaching NOLA'),
    ('2026-07-11', '10:00 PM', 'CONO TN'),
    ('2026-07-12', '8:00 PM', 'Empire Builder WI/MN'),
    ('2026-07-13', '1:00 PM', 'Empire Builder MT'),
    ('2026-07-14', '12:00 PM', 'Empire Builder arriving PDX'),
    ('2026-07-16', '8:00 PM', 'Coast Starlight OR'),
    ('2026-07-17', '3:00 PM', 'Coast Starlight CA'),
    ('2026-07-20', '10:00 AM', 'TX Eagle AR'),
    ('2026-07-21', '6:00 PM', 'TX Eagle approaching CHI'),
]


def load_engine() -> dict:
    """Load all data once; return the context query_at()/query_position() need."""
    station_lookup = load_station_catalog()
    get_geo = build_station_geo(station_lookup, load_mileposts())
    timetables = {k: parse_timetable(v) for k, v in TIMETABLE_TEXT.items()}
    all_schedules = {tt: compute_schedule(tt, dep, timetables, get_geo)
                     for _n, tt, _a, dep, _t in ITINERARY}
    return {
        'all_runs': load_asmad_runs(),
        'station_lookup': station_lookup,
        'route_sched': build_route_sched(),
        'all_schedules': all_schedules,
        'leg_shapes': _load_leg_shapes(),
    }


def query_at(ctx, when_dt, observed=None, sigma=25.0):
    """when_dt: tz-aware datetime → predictor result dict (or None). Normalizes to ET."""
    et = when_dt.astimezone(_tz('US/Eastern'))
    return query_position(et.strftime('%Y-%m-%d'), et.strftime('%I:%M %p'),
                          ctx['all_runs'], ctx['all_schedules'],
                          ctx['route_sched'], ctx['station_lookup'], ctx.get('leg_shapes'),
                          observed=observed, sigma=sigma)


def _active_leg(ctx, when_utc):
    for name, tt_key, _a, _d, _t in ITINERARY:
        s = ctx['all_schedules'].get(tt_key, [])
        if len(s) >= 2 and s[0]['utc'] - 7200 <= when_utc <= s[-1]['utc'] + 21600:
            return name, tt_key
    return None, None


def _delay_phrase(d):
    return 'on time' if abs(d) < 5 else (f'{int(round(d))} min late' if d > 0 else f'{int(round(-d))} min early')


def _fmt_predicted(r, when_dt, label='PREDICTED'):
    if not r:
        return f"  [{label}] Not on a train at {when_dt:%Y-%m-%d %I:%M %p %Z}."
    tag = label
    if r.get('conditioned'):
        tag = (f"{label} · conditioned on {_delay_phrase(r['obs_delay_min'])} "
               f"(n_eff={r['n_eff']}, σ={r['sigma_used']}m)")
    return "\n".join([
        f"  [{tag}]  {r['train']}  ·  +{r['hours_into_trip']}h into the leg  ·  n={r['n_runs']} runs",
        f"  Most likely (P50): {r['p50_lat']}, {r['p50_lon']}  (~mile {r['p50_mi']})",
        f"  Between {r['before']}  and  {r['after']}",
        f"  Uncertainty P10–P90: mile {r['p10_mi']} → {r['p90_mi']} "
        f"({r['p10_lat']},{r['p10_lon']} → {r['p90_lat']},{r['p90_lon']})",
    ])


def _fmt_live(fix):
    src = fix.get('source')
    head = 'LIVE' if src == 'live' else 'CACHED LIVE'
    lines = [f"  [{head}]  {fix.get('route')} (#{fix.get('train_num')})  ·  {fix.get('state')}"]
    spd = (f"  ·  {fix['velocity_mph']} mph {fix.get('heading') or ''}".rstrip()
           if fix.get('velocity_mph') is not None else "")
    lines.append(f"  Now at: {fix.get('lat'):.4f}, {fix.get('lon'):.4f}{spd}")
    d = fix.get('delay_min')
    if d is not None:
        lines.append(f"  Running: {'on time' if abs(d) < 5 else (f'{d} min late' if d > 0 else f'{-d} min early')}")
    if fix.get('next_name'):
        eta = f", est. arrival {fix['next_eta']}" if fix.get('next_eta') else ""
        lines.append(f"  Next stop: {fix['next_name']} ({fix.get('next_code')}){eta}")
    if src == 'cache':
        try:
            from live import cache_age_minutes
            age = cache_age_minutes(fix)
            if age is not None:
                lines.append(f"  (offline — last live fix {age} min ago)")
        except Exception:
            pass
    return "\n".join(lines)


def _fmt_eta(e):
    if not e:
        return "  No active leg / no data for that ETA."
    if e.get('error'):
        return f"  {e['error']}"
    cond = (f"conditioned on {_delay_phrase(e['obs_delay_min'])}, n_eff={e['n_eff']}"
            if e.get('conditioned') else "unconditioned")
    return "\n".join([
        f"  ETA to {e['station']}  ({e['train']}, {cond})",
        f"  Likely (P50): {e['p50']:%a %I:%M %p %Z}",
        f"  Window P10–P90: {e['p10']:%I:%M %p} – {e['p90']:%I:%M %p}",
    ])


def _leg_of_station(ctx, code):
    """Timetable key of the leg whose route includes station `code`, or None."""
    for _n, tt_key, _a, _dd, _t in ITINERARY:
        sched = ctx['all_schedules'].get(tt_key, [])
        if len(sched) >= 2 and code in build_leg_frame(tt_key, sched, ctx['route_sched']):
            return tt_key
    return None


def _observation(ctx, args, tt_key):
    """Build the conditioning observation: manual --at/--delay overrides; else the live
    current position+delay for the leg's train; else None (→ unconditioned)."""
    if args.at or args.delay is not None:
        obs = {'delay': float(args.delay) if args.delay is not None else 0.0}
        if args.at:
            obs['station'] = args.at.upper()
        return obs
    if args.no_live or not tt_key:
        return None
    live = _load_live()
    if not live:
        return None
    data = live.fetch_all()
    for num in LIVE_TRAINS.get(tt_key, []):
        fix = live.live_position(num, data=data)
        if fix and fix.get('lat') is not None and fix.get('delay_min') is not None:
            return {'latlon': (fix['lat'], fix['lon']), 'delay': fix['delay_min']}
    return None


def _locate(ctx, args):
    """Resolve (leg, mile, ref_dt, observed) for the route-guide commands. A time given
    as the 2nd arg → predicted mile at that time; else live position now; else None."""
    timearg = args.station  # 2nd positional doubles as the time for around/lookahead/alerts
    if timearg:
        ref_dt = _parse_when(timearg, args.tz)
        if ref_dt is None:
            return None, None, None, None
        leg = _active_leg(ctx, int(ref_dt.timestamp()))[1]
        observed = _observation(ctx, args, leg)
        r = query_at(ctx, ref_dt, observed=observed)
        return leg, (r['p50_mi'] if r else None), ref_dt, observed
    now_dt = datetime.now(_tz('US/Eastern'))
    leg = _active_leg(ctx, int(now_dt.timestamp()))[1]
    if leg and not args.no_live:
        live = _load_live()
        data = live.fetch_all() if live else None
        for num in LIVE_TRAINS.get(leg, []):
            fix = live.live_position(num, data=data) if live else None
            if fix and fix.get('source') == 'live' and fix.get('lat') is not None:
                proj = project_to_leg(ctx['leg_shapes'][leg], fix['lat'], fix['lon'])
                return leg, proj[0], now_dt, {'latlon': (fix['lat'], fix['lon']), 'delay': fix['delay_min']}
    if leg:
        r = query_at(ctx, now_dt)
        return leg, (r['p50_mi'] if r else None), now_dt, None
    return None, None, now_dt, None


def _side_word(s):
    return {'left': '← left window', 'right': 'right window →',
            'both': 'both sides', 'ahead': 'straight ahead'}.get(s, s)


def _fmt_around(feats, context, mile):
    lines = [f"  Around you (~mile {mile:.0f}):"]
    if context:
        lines.append("  In: " + ", ".join(f"{f['name']} ({_side_word(f['side'])})" for f in context))
    nearby = [f for f in feats if not f['inside']][:8]
    for f in nearby:
        rel = f['rel_mi']
        where = f"{abs(rel):.0f} mi ahead" if rel > 0 else f"{abs(rel):.0f} mi back"
        kind = 'stop' if f['kind'] == 'station' else f['kind']
        b = f" — {f['blurb']}" if f.get('blurb') else ""
        lines.append(f"    {f['name']} [{kind}] ({where}, {_side_word(f['side'])}){b}")
    if not context and not nearby:
        lines.append("    (open country)")
    return "\n".join(lines)


def _fmt_lookahead(feats, mode):
    if not feats:
        return "  Nothing notable in that window."
    lines = [f"  {'Heads-up — coming soon:' if mode == 'alerts' else 'Coming up:'}"]
    for f in feats:
        b = f" — {f['blurb']}" if f.get('blurb') else ""
        lines.append(f"    +{f['mins_ahead']:>3} min (~{f['eta']['p50']:%I:%M %p}, {_side_word(f['side'])})  {f['name']}{b}")
    return "\n".join(lines)


def _fmt_guide(legdata, leg):
    lines = [f"  Route guide — {legdata.get('corridor', 'leg ' + leg)} ({legdata['leg_miles']:.0f} mi):"]
    for f in legdata['features']:
        if f['kind'] == 'station' or f['salience'] < 3:
            continue
        span = f"{f['from_mi']:.0f}-{f['to_mi']:.0f}" if f['from_mi'] < f['to_mi'] else f"mi {f['peak_mi']:.0f}"
        lines.append(f"    {span:>12} · {_side_word(f['side']):<15} {f['name']} — {f['blurb']}")
    gaps = legdata.get('coverage_gaps') or []
    if gaps:
        lines.append(f"  ({len(gaps)} sparse stretch(es) pending Phase B/C enrichment: "
                     + ", ".join(f'{int(a)}-{int(b)}mi' for a, b in gaps) + ")")
    return "\n".join(lines)


def _fmt_profile(area):
    if not area:
        return "  No area/demographic data here yet."
    s = area.get('stats', {})
    lines = [f"  {area['name']}"]
    if s.get('population') is not None:
        age = f", median age {s['median_age']}" if s.get('median_age') is not None else ""
        lines.append(f"    ~{s['population']:,} people{age}")
    if s.get('median_hh_income'):
        pov = f", poverty {s['poverty_pct']}%" if s.get('poverty_pct') is not None else ""
        lines.append(f"    median household income ~${s['median_hh_income']:,}{pov}")
    if s.get('ba_plus_pct') is not None:
        lines.append(f"    bachelor's degree or higher: {s['ba_plus_pct']}%")
    if s.get('top_industries'):
        lines.append("    main industries: " + ", ".join(s['top_industries']))
    if s.get('top_occupations'):
        lines.append("    top occupations: " + ", ".join(s['top_occupations']))
    if s.get('top_crops'):
        lines.append("    land use (crops): " + ", ".join(s['top_crops']))
    if s.get('land_cover'):
        top = list(s['land_cover'].items())[:3]
        lines.append("    land cover: " + ", ".join(f"{int(p * 100)}% {g}" for g, p in top))
    if s.get('source'):
        lines.append(f"    [{s['source']}]")
    return "\n".join(lines)


def run_tests(ctx):
    print('=== POSITION QUERIES (July 2026 itinerary) ===')
    for d, tm, desc in TESTS:
        r = query_position(d, tm, ctx['all_runs'], ctx['all_schedules'],
                           ctx['route_sched'], ctx['station_lookup'], ctx.get('leg_shapes'))
        print(f"\n{desc}  ({d} {tm} ET)")
        print(_fmt_predicted(r, datetime.now(_tz('UTC'))) if r else '  → NOT ON TRAIN')


def _parse_when(s, tzname):
    for fmt in ('%Y-%m-%d %I:%M %p', '%Y-%m-%d %H:%M', '%Y-%m-%d %I%p', '%m/%d/%Y %I:%M %p'):
        try:
            return _localize(datetime.strptime(s.strip(), fmt), tzname)
        except ValueError:
            continue
    return None


def _load_live():
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    try:
        import live
        return live
    except Exception:
        return None


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Amtrak position estimator (July 2026 trip)')
    ap.add_argument('when', nargs='?', default='now',
                    help='"now", a time, "eta", "around", "lookahead", "alerts", "profile", "guide", or "test"')
    ap.add_argument('station', nargs='?', help='station/leg code, or a time for around/lookahead/alerts')
    ap.add_argument('--horizon', type=int, help='lookahead horizon in minutes (default 120; alerts 30)')
    ap.add_argument('--tz', default='US/Eastern', help='timezone of the given time (default ET)')
    ap.add_argument('--no-live', action='store_true', help='skip the live feed (predict only)')
    ap.add_argument('--train', help='force a live lookup of this train number (debug)')
    ap.add_argument('--at', help='conditioning: station code you have just passed')
    ap.add_argument('--delay', type=float, help='conditioning: minutes late there (default 0)')
    ap.add_argument('--sigma', type=float, default=25.0, help='conditioning kernel bandwidth, min (default 25, auto-widens)')
    args = ap.parse_args()

    if args.train:  # pure live probe — works whenever a train of that number is running
        live = _load_live()
        # --no-live forces the cached-fix path (demonstrates offline failover)
        fix = live.live_position(args.train, data=({} if args.no_live else None)) if live else None
        print(_fmt_live(fix) if fix else f"  No live data for train {args.train} (and no cache).")
        return

    ctx = load_engine()
    if args.when == 'test':
        run_tests(ctx)
        return

    if args.when == 'eta':
        if not args.station:
            print('  usage: position_engine.py eta <STATION_CODE> [--at CODE --delay MIN]')
            return
        leg_key = _leg_of_station(ctx, args.at.upper()) if args.at else None
        if leg_key is None:
            _, leg_key = _active_leg(ctx, int(datetime.now(_tz('US/Eastern')).timestamp()))
        observed = _observation(ctx, args, leg_key)
        print(_fmt_eta(eta_to(ctx, args.station.upper(), leg_key=leg_key,
                              observed=observed, sigma=args.sigma)))
        return

    if args.when == 'profile':   # who lives here / what they do / land character
        import route_guide as RG
        guide = RG.load_guide()
        leg, mile, _ref, _obs = _locate(ctx, args)
        if not leg or mile is None:
            print('  Not on a leg now — give a time, e.g.  profile "2026-07-07 9:00 AM"')
            return
        print(_fmt_profile(RG.area_at(guide, leg, mile)))
        return

    if args.when == 'guide':
        import route_guide as RG
        guide = RG.load_guide()
        leg = args.station
        if not leg or leg not in guide:
            print(f"  usage: guide <leg>   (legs: {', '.join(guide) or 'none built'})")
            return
        print(_fmt_guide(guide[leg], leg))
        return

    if args.when in ('around', 'lookahead', 'alerts'):
        import route_guide as RG
        guide = RG.load_guide()
        if not guide:
            print("  No route guide built yet (run build_route_guide.py).")
            return
        leg, mile, ref_dt, observed = _locate(ctx, args)
        if not leg or mile is None:
            print('  Not on a trip leg now — give a time, e.g.  around "2026-07-13 1:30 PM"')
            return
        if args.when == 'around':
            print(_fmt_around(RG.around(guide, leg, mile, min_salience=1),
                              RG.current_context(guide, leg, mile), mile))
        else:
            horizon = args.horizon or (30 if args.when == 'alerts' else 120)
            min_sal = 4 if args.when == 'alerts' else 2
            feats = RG.lookahead(ctx, guide, leg, mile, ref_dt, observed=observed,
                                 horizon_min=horizon, min_salience=min_sal)
            print(_fmt_lookahead(feats, args.when))
        return

    if args.when == 'now':
        now_dt = datetime.now(_tz('US/Eastern'))
        name, tt_key = _active_leg(ctx, int(now_dt.timestamp()))
        if not args.no_live and tt_key:
            live = _load_live()
            data = live.fetch_all() if live else None
            for num in LIVE_TRAINS.get(tt_key, []):
                fix = live.live_position(num, data=data) if live else None
                if fix and fix.get('source') == 'live' and fix.get('state') == 'Active':
                    print(_fmt_live(fix))
                    return
        r = query_at(ctx, now_dt)
        print(_fmt_predicted(r, now_dt, 'PREDICTED (no live)') if r
              else f"  Not currently on a trip leg ({now_dt:%Y-%m-%d %I:%M %p %Z}).")
        return

    when_dt = _parse_when(args.when, args.tz)
    if when_dt is None:
        print('  Could not parse time. Try e.g. "2026-07-13 1:30 PM" or "2026-07-13 13:30".')
        return
    _, tt_key = _active_leg(ctx, int(when_dt.timestamp()))
    observed = _observation(ctx, args, tt_key)
    print(_fmt_predicted(query_at(ctx, when_dt, observed=observed, sigma=args.sigma), when_dt))


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == '--build':
        build_bundle(sys.argv[2] if len(sys.argv) > 2 else SRC_DIR)
    else:
        main()
