#!/usr/bin/env python3
"""
Amtrak Position Query Engine — July 2026 Trainstravaganza.

Answers: "Where will I be on July XX at HH:MM Eastern time?"
Uses atomic historical-vector sampling with time-since-departure normalization.

Dependencies: beautifulsoup4, pytz, requests

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
import pytz

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
    dt = pytz.timezone(tz_str).localize(dt)
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

def query_position(
    query_date_str: str,
    query_time_str: str,
    all_runs: dict,
    all_schedules: dict,
    route_sched: dict,
    station_lookup: dict,
) -> Optional[dict]:
    """Return probable position (p10/p50/p90) at a given date/time (ET).

    Offsets = scheduled-elapsed-from-anchor (our timetable) + measured delay, on
    one tz-correct clock.  Each leg pools historical runs from ALL its source
    trains (see LEG_SOURCES), mapped through a single chained-milepost frame, so
    multi-train legs (Empire Builder, Texas Eagle) are continuous.  An origin
    point (offset 0, mile 0) restores pre-first-report coverage; only stations on
    our route contribute."""
    qdt = datetime.strptime(f'{query_date_str} {query_time_str}', '%Y-%m-%d %I:%M %p')
    q_utc = int(pytz.timezone('US/Eastern').localize(qdt).timestamp())

    for name, tt_key, _asm_train, dep_date_str, _dep_time_str in ITINERARY:
        sched = all_schedules.get(tt_key, [])
        if len(sched) < 2:
            continue
        our_dep_utc = sched[0]['utc']
        our_last_utc = sched[-1]['utc']
        if q_utc < our_dep_utc - 7200:
            continue
        if q_utc > our_last_utc + 21600:
            continue

        frame = build_leg_frame(tt_key, sched, route_sched)
        if not frame:
            continue
        anchor = None
        for s in sched:
            if s['code'] in frame:
                anchor = s['code']
                anchor_utc = frame[anchor]['utc']
                anchor_mi = frame[anchor]['miles']
                break
        if anchor is None:
            continue

        our_offset_h = (q_utc - anchor_utc) / 3600.0
        src_trains = [seg[0] for seg in LEG_SOURCES.get(tt_key, [])]
        positions = []

        for ti, train in enumerate(src_trains):
            for _origin_date, run in all_runs.get(train, []):
                pts = []
                for code, d in run.items():
                    fr = frame.get(code)
                    if not fr:
                        continue
                    off = (fr['utc'] - anchor_utc) / 3600.0 + d['delay'] / 60.0
                    pts.append((off, fr['miles'] - anchor_mi, fr['lat'], fr['lon']))
                # Origin (mile-0) anchor only for the leg's FIRST-segment train — a
                # later segment (e.g. train 27 covering only SPK→PDX) didn't depart
                # the leg origin, so anchoring it there draws a bogus straight chord.
                if pts and ti == 0:
                    a = frame[anchor]
                    pts.append((0.0, 0.0, a['lat'], a['lon']))
                pts.sort()
                for i in range(len(pts) - 1):
                    o1, m1, la1, lo1 = pts[i]
                    o2, m2, la2, lo2 = pts[i + 1]
                    if o1 <= our_offset_h <= o2:
                        frac = (our_offset_h - o1) / (o2 - o1) if o2 != o1 else 0.5
                        frac = max(0.0, min(1.0, frac))
                        positions.append({
                            'lat': la1 + frac * (la2 - la1),
                            'lon': lo1 + frac * (lo2 - lo1),
                            'miles': m1 + frac * (m2 - m1),
                        })
                        break

        if len(positions) >= 5:
            ps = sorted(positions, key=lambda x: x['miles'])
            n = len(ps)
            p10 = ps[max(0, int(n * 0.1))]
            p50 = ps[int(n * 0.5)]
            p90 = ps[min(n - 1, int(n * 0.9))]

            route_stations = sorted(
                ((info['miles'] - anchor_mi, code) for code, info in frame.items()),
                key=lambda x: x[0],
            )
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
                'n_runs': n,
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


# ── 7. MAIN ────────────────────────────────────────────────────────

def main():
    print('Loading ASMAD historical data ...')
    all_runs = load_asmad_runs()
    for t, r in all_runs.items():
        print(f'  Train {t}: {len(r)} runs')

    print('Loading station geography ...')
    station_lookup = load_station_catalog()
    mileposts_raw = load_mileposts()
    get_geo = build_station_geo(station_lookup, mileposts_raw)
    route_sched = build_route_sched()

    print('Parsing timetables ...')
    timetables = {k: parse_timetable(v) for k, v in TIMETABLE_TEXT.items()}
    for k, v in timetables.items():
        print(f'  {k}: {len(v)} stations')

    print('Computing July 2026 schedules ...')
    all_schedules = {}
    for name, tt_key, _asm_train, dep_date_str, _ in ITINERARY:
        all_schedules[tt_key] = compute_schedule(tt_key, dep_date_str, timetables, get_geo)

    tests = [
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

    print('\n=== POSITION QUERIES ===')
    for dt, tm, desc in tests:
        r = query_position(dt, tm, all_runs, all_schedules, route_sched, station_lookup)
        if r:
            print(f'\n{desc}  ({dt} {tm} ET)')
            print(f'  Train: {r["train"]}  +{r["hours_into_trip"]}h  n={r["n_runs"]}')
            print(f'  P10: {r["p10_lat"]},{r["p10_lon"]}  ({r["p10_mi"]} mi)')
            print(f'  P50: {r["p50_lat"]},{r["p50_lon"]}  ({r["p50_mi"]} mi)')
            print(f'  P90: {r["p90_lat"]},{r["p90_lon"]}  ({r["p90_mi"]} mi)')
            print(f'  Near: {r["before"]}  →  {r["after"]}')
        else:
            print(f'\n{desc}  ({dt} {tm} ET)  →  NOT ON TRAIN')


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == '--build':
        build_bundle(sys.argv[2] if len(sys.argv) > 2 else SRC_DIR)
    else:
        main()
