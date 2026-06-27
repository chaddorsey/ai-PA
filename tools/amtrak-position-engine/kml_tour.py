#!/usr/bin/env python3
"""
Google Earth fly-ahead tour generator — a renderer on the route-guide contract,
with PREDICTED TIMES and SUN POSITION from the actual July-2026 leg schedules.

Reads data/leg_shapes.json (polyline) + data/route_guide.json (features), and uses
the engine (eta_to_mile / trajectories) to stamp each feature and tour camera with
the realistic clock time you'd be there, then computes the sun (elevation/azimuth,
which window) at that time/place. KML <TimeStamp>s also drive Google Earth's own
Sun/lighting as the tour plays — turn on "Sunlight across the landscape".

Usage:
  python3 kml_tour.py all            # all six legs -> kml/<corridor>.kml
  python3 kml_tour.py 11             # just the Coast Starlight
  python3 kml_tour.py 11 --min-salience 4
Stdlib + the engine (no network).
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import position_engine as E   # noqa: E402
import sun as SUN             # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'
OUTDIR = Path(__file__).resolve().parent / 'kml'

ICON = {
    'scenic': 'http://maps.google.com/mapfiles/kml/paddle/ylw-stars.png',
    'natural': 'http://maps.google.com/mapfiles/kml/paddle/grn-blank.png',
    'protected': 'http://maps.google.com/mapfiles/kml/paddle/grn-diamond.png',
    'engineering': 'http://maps.google.com/mapfiles/kml/shapes/triangle.png',
    'place': 'http://maps.google.com/mapfiles/kml/paddle/wht-circle.png',
    'station': 'http://maps.google.com/mapfiles/kml/shapes/rail.png',
}
TOUR_STEP_MI = 18.0
TOUR_ALT_M = 5500.0


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _bearing(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dl = lon2 - lon1
    x = math.sin(dl) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


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


def _heading_at(poly, mile):
    return _bearing(_latlon_at(poly, mile), _latlon_at(poly, min(mile + 5, poly[-1][0])))


def _interp(pts, x):
    if not pts:
        return None
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        if x1 <= x <= x2:
            f = (x - x1) / (x2 - x1) if x2 != x1 else 0.0
            return y1 + f * (y2 - y1)
    return pts[-1][1]


def _leg_clock(ctx, leg):
    """Build a fast per-leg ETA: eta(mile) -> realistic (median) ET datetime; plus a
    station→tz list for local-time display. Trajectories built once."""
    sched = ctx['all_schedules'].get(leg, [])
    built = E._build_trajectories(leg, sched, ctx['all_runs'], ctx['route_sched'])
    if not built:
        return None, None, None
    _anchor, anchor_utc, anchor_mi, frame, trajs = built
    sched_pts = sorted((frame[c]['miles'] - anchor_mi, frame[c]['utc']) for c in frame)
    cat = ctx['station_lookup']
    station_tz = [(frame[c]['lat'], frame[c]['lon'], cat.get(c, {}).get('timezone'))
                 for c in frame if cat.get(c, {}).get('timezone')]

    def eta(mile):
        offs = [o for o in (E._off_at_mile(t['pts'], mile) for t in trajs) if o is not None and o >= 0]
        if len(offs) >= 5:
            offs.sort()
            return datetime.fromtimestamp(anchor_utc + offs[len(offs) // 2] * 3600, E._tz('US/Eastern'))
        u = _interp(sched_pts, mile)
        return datetime.fromtimestamp(u, E._tz('US/Eastern')) if u is not None else None

    return eta, station_tz, sched_pts


def _local_tz(station_tz, lat, lon):
    best = (None, 9e9)
    for sla, slo, tz in station_tz:
        d = (sla - lat) ** 2 + (slo - lon) ** 2
        if d < best[1]:
            best = (tz, d)
    return best[0]


def _annotate(f, poly, eta, station_tz):
    """Return (when_utc_iso or None, extra_html) for a feature: predicted local time + sun."""
    dt = eta(f['peak_mi']) if eta else None
    if dt is None:
        return None, ''
    tz = _local_tz(station_tz, f['lat'], f['lon'])
    local = dt.astimezone(E._tz(tz)) if tz else dt
    heading = _heading_at(poly, f['peak_mi'])
    suntxt = SUN.describe(dt, f['lat'], f['lon'], heading)
    when_iso = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    extra = (f"<br/>~{local:%a %b %-d, %-I:%M %p %Z} (typical)<br/>Sun: {_esc(suntxt)}")
    return when_iso, extra


def _styles():
    out = ['<Style id="route"><LineStyle><color>ff1e90ff</color><width>4</width></LineStyle></Style>']
    for cls, url in ICON.items():
        scale = 1.2 if cls in ('scenic', 'protected') else 0.9
        out.append(f'<Style id="{cls}"><IconStyle><scale>{scale}</scale>'
                   f'<Icon><href>{url}</href></Icon></IconStyle></Style>')
    return '\n'.join(out)


def _placemarks(features, poly, eta, station_tz, min_salience):
    sights, stations = [], []
    for f in features:
        if f['salience'] < min_salience and f['class'] != 'station':
            continue
        side = {'left': 'left window', 'right': 'right window', 'both': 'both sides',
                'ahead': 'ahead'}.get(f['side'], f['side'])
        when, extra = _annotate(f, poly, eta, station_tz)
        desc = f"{_esc(f.get('blurb', ''))}<br/>mile {f['peak_mi']:.0f} · {side}{extra}"
        ts = f'<TimeStamp><when>{when}</when></TimeStamp>' if when else ''
        pm = (f'<Placemark><name>{_esc(f["name"])}</name>'
              f'<description><![CDATA[{desc}]]></description>{ts}'
              f'<styleUrl>#{f["class"]}</styleUrl>'
              f'<Point><coordinates>{f["lon"]},{f["lat"]},0</coordinates></Point></Placemark>')
        (stations if f['class'] == 'station' else sights).append(pm)
    return (f'<Folder><name>Sights ({len(sights)})</name>{"".join(sights)}</Folder>'
            f'<Folder><name>Stations ({len(stations)})</name><visibility>0</visibility>'
            f'{"".join(stations)}</Folder>')


def _tour(poly, features, eta):
    legmi = poly[-1][0]
    stops = sorted([f for f in features if f['salience'] >= 4 and f['class'] != 'station'],
                   key=lambda x: x['peak_mi'])
    items, si, mile = [], 0, 0.0
    while mile <= legmi:
        la, lo = _latlon_at(poly, mile)
        hdg = _heading_at(poly, mile)
        dt = eta(mile) if eta else None
        ts = (f'<gx:TimeStamp><when>{dt.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}</when></gx:TimeStamp>'
              if dt else '')
        items.append(
            f'<gx:FlyTo><gx:duration>1.6</gx:duration><gx:flyToMode>smooth</gx:flyToMode>'
            f'<Camera>{ts}<longitude>{lo:.5f}</longitude><latitude>{la:.5f}</latitude>'
            f'<altitude>{TOUR_ALT_M}</altitude><heading>{hdg:.1f}</heading><tilt>67</tilt>'
            f'<altitudeMode>relativeToGround</altitudeMode></Camera></gx:FlyTo>')
        while si < len(stops) and stops[si]['peak_mi'] <= mile:
            s = stops[si]
            sdt = eta(s['peak_mi']) if eta else None
            sts = (f'<gx:TimeStamp><when>{sdt.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}</when></gx:TimeStamp>'
                   if sdt else '')
            items.append(
                f'<gx:FlyTo><gx:duration>2.0</gx:duration><gx:flyToMode>smooth</gx:flyToMode>'
                f'<LookAt>{sts}<longitude>{s["lon"]:.5f}</longitude><latitude>{s["lat"]:.5f}</latitude>'
                f'<altitude>0</altitude><heading>{hdg:.1f}</heading><tilt>75</tilt>'
                f'<range>22000</range></LookAt></gx:FlyTo>'
                f'<gx:Wait><gx:duration>2.2</gx:duration></gx:Wait>')
            si += 1
        mile += TOUR_STEP_MI
    return f'<gx:Tour><name>Fly the route</name><gx:Playlist>{"".join(items)}</gx:Playlist></gx:Tour>'


def build_leg_kml(leg, corridor, poly, features, ctx, min_salience=3):
    eta, station_tz, _sched = _leg_clock(ctx, leg)
    coords = ' '.join(f'{lo:.5f},{la:.5f},0' for _m, la, lo in poly)
    route = (f'<Placemark><name>Route</name><styleUrl>#route</styleUrl>'
             f'<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString></Placemark>')
    note = ('Predicted (typical) times &amp; modeled sun for this leg. '
            'Tip: enable "Sunlight across the landscape" in Google Earth to see the sun as the tour plays.')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">\n'
        f'<Document><name>{_esc(corridor)} (leg {leg})</name><description><![CDATA[{note}]]></description>\n'
        f'{_styles()}\n{route}\n{_placemarks(features, poly, eta, station_tz, min_salience)}\n'
        f'{_tour(poly, features, eta)}\n</Document></kml>\n')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    min_sal = int(sys.argv[sys.argv.index('--min-salience') + 1]) if '--min-salience' in sys.argv else 3
    target = args[0] if args else 'all'
    shapes = json.loads((DATA / 'leg_shapes.json').read_text())
    guide = json.loads((DATA / 'route_guide.json').read_text())
    ctx = E.load_engine()
    OUTDIR.mkdir(exist_ok=True)
    for leg in (list(guide) if target == 'all' else [target]):
        if leg not in guide or leg not in shapes:
            print(f"  leg {leg}: no data")
            continue
        corridor = guide[leg].get('corridor', f'leg {leg}')
        slug = corridor.lower().replace(' ', '-')
        path = OUTDIR / f'{slug}.kml'
        path.write_text(build_leg_kml(leg, corridor, shapes[leg], guide[leg]['features'], ctx, min_sal))
        n = sum(1 for f in guide[leg]['features'] if f['salience'] >= min_sal and f['class'] != 'station')
        print(f"  leg {leg}: {path.name}  ({len(shapes[leg])} pts, {n} sights, times+sun)")
    print(f"Open kml/*.kml in Google Earth; enable Sunlight and press play.")


if __name__ == '__main__':
    main()
